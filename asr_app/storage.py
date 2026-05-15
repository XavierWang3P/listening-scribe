import hashlib
import json
import re
import shutil
import time
import uuid
from pathlib import Path

from .config import AUDIO_DIR, DATA_DIR, HASH_DIR, RESULTS_DIR, TASKS_DIR, TMP_DIR, env
from .utils import audio_ext, clean_name, quote_path, safe_relative_path, valid_record_id


def write_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")


def read_json_file(path: Path) -> dict:
    return json.loads(path.read_text("utf-8"))


def write_text(path: Path, text: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")


def new_record_id() -> str:
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


def audio_folder(record_id: str) -> Path:
    return AUDIO_DIR / record_id


def audio_meta_path(record_id: str) -> Path:
    return audio_folder(record_id) / "meta.json"


def hash_index_path(audio_hash: str) -> Path:
    return HASH_DIR / f"{audio_hash}.json"


def result_dir(record_id: str) -> Path:
    return RESULTS_DIR / record_id


def manifest_path(record_id: str) -> Path:
    return result_dir(record_id) / "manifest.json"


def task_path(task_id: str) -> Path:
    return TASKS_DIR / f"{task_id}.json"


def audio_url(record_id: str, filename: str) -> str:
    return f"/media/audio/{record_id}/{quote_path(filename)}"


def result_url(record_id: str, *parts: str) -> str:
    return f"/results/{record_id}/{quote_path(*parts)}"


def save_upload(environ, query: dict):
    filename = clean_name((query.get("filename") or ["audio"])[0])
    content_type = (query.get("content_type") or [environ.get("CONTENT_TYPE") or "application/octet-stream"])[0]
    expected_hash = str((query.get("sha256") or [""])[0]).lower()
    if not re.fullmatch(r"[a-f0-9]{64}", expected_hash):
        raise RuntimeError("sha256 must be a 64-character hex string")

    length = int(environ.get("CONTENT_LENGTH") or 0)
    max_bytes = int(float(env("MAX_UPLOAD_MB", "500")) * 1024 * 1024)
    if length <= 0:
        raise RuntimeError("empty upload")
    if length > max_bytes:
        raise RuntimeError(f"file is larger than MAX_UPLOAD_MB={env('MAX_UPLOAD_MB', '500')}")

    filename = clean_name(Path(filename).stem) + audio_ext(filename, content_type)
    index_path = hash_index_path(expected_hash)
    existing_meta = get_audio_meta_by_hash(expected_hash)
    record_id = existing_meta["record_id"] if existing_meta else new_record_id()
    folder = audio_folder(record_id)
    folder.mkdir(parents=True, exist_ok=True)
    tmp_path = TMP_DIR / f"{expected_hash}-{uuid.uuid4().hex}.upload"
    final_path = folder / filename

    hasher = hashlib.sha256()
    remaining = length
    with tmp_path.open("wb") as handle:
        while remaining > 0:
            chunk = environ["wsgi.input"].read(min(1024 * 1024, remaining))
            if not chunk:
                break
            hasher.update(chunk)
            handle.write(chunk)
            remaining -= len(chunk)

    actual_hash = hasher.hexdigest()
    if actual_hash != expected_hash:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError(f"sha256 mismatch: {actual_hash}")

    if existing_meta:
        tmp_path.unlink(missing_ok=True)
        meta = dict(existing_meta)
        meta["duplicate"] = True
        meta["updated_at"] = int(time.time())
        return meta

    if final_path.exists():
        tmp_path.unlink(missing_ok=True)
    else:
        tmp_path.replace(final_path)

    meta = {
        "record_id": record_id,
        "audio_hash": expected_hash,
        "original_filename": filename,
        "filename": filename,
        "content_type": content_type,
        "size": final_path.stat().st_size,
        "path": str(final_path.relative_to(DATA_DIR)),
        "audio_url": audio_url(record_id, filename),
        "duplicate": False,
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
    }
    write_json(audio_meta_path(record_id), meta)
    write_json(index_path, {"record_id": record_id, "audio_hash": expected_hash, "created_at": meta["created_at"]})
    return meta


def get_audio_meta(record_id: str) -> dict:
    if not valid_record_id(record_id):
        raise RuntimeError("invalid audio record id")
    path = audio_meta_path(record_id)
    if not path.exists():
        raise RuntimeError("audio file has not been uploaded")
    meta = read_json_file(path)
    meta.setdefault("record_id", record_id)
    return meta


def get_audio_meta_by_hash(audio_hash: str) -> dict | None:
    if not re.fullmatch(r"[a-f0-9]{64}", audio_hash):
        raise RuntimeError("invalid audio hash")
    index_path = hash_index_path(audio_hash)
    if index_path.exists():
        index = read_json_file(index_path)
        return get_audio_meta(str(index["record_id"]))

    legacy_path = AUDIO_DIR / audio_hash / "meta.json"
    if legacy_path.exists():
        meta = read_json_file(legacy_path)
        meta.setdefault("record_id", audio_hash)
        return meta
    return None


def get_audio_path(meta: dict) -> Path:
    return DATA_DIR / safe_relative_path(meta["path"])


def remove_hash_indexes(record_id: str, audio_hash: str = "") -> int:
    removed = 0
    seen = set()

    def remove_if_matches(path: Path, trust_filename: bool = False):
        nonlocal removed
        if not path.exists() or path in seen:
            return
        seen.add(path)
        try:
            payload = read_json_file(path)
        except (OSError, json.JSONDecodeError):
            payload = {}
        if trust_filename or payload.get("record_id") == record_id:
            path.unlink(missing_ok=True)
            removed += 1

    if re.fullmatch(r"[a-f0-9]{64}", audio_hash or ""):
        remove_if_matches(hash_index_path(audio_hash), trust_filename=True)

    if HASH_DIR.exists():
        for index_path in HASH_DIR.glob("*.json"):
            remove_if_matches(index_path)
    return removed


def remove_task_files(record_id: str) -> int:
    removed = 0
    if not TASKS_DIR.exists():
        return removed
    for path in TASKS_DIR.glob("*.json"):
        try:
            task = read_json_file(path)
        except (OSError, json.JSONDecodeError):
            continue
        if task.get("record_id") == record_id:
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def delete_record(record_id: str) -> dict:
    if not valid_record_id(record_id):
        raise RuntimeError("invalid record id")

    audio_hash = ""
    meta_path = audio_meta_path(record_id)
    manifest = manifest_path(record_id)
    if meta_path.exists():
        try:
            audio_hash = read_json_file(meta_path).get("audio_hash", "")
        except (OSError, json.JSONDecodeError):
            audio_hash = ""
    if not audio_hash and manifest.exists():
        try:
            audio_hash = read_json_file(manifest).get("audio_hash", "")
        except (OSError, json.JSONDecodeError):
            audio_hash = ""

    audio_removed = False
    folder = audio_folder(record_id)
    if folder.exists():
        shutil.rmtree(folder)
        audio_removed = True

    result_removed = False
    results = result_dir(record_id)
    if results.exists():
        shutil.rmtree(results)
        result_removed = True

    return {
        "ok": True,
        "record_id": record_id,
        "audio_removed": audio_removed,
        "result_removed": result_removed,
        "hash_indexes_removed": remove_hash_indexes(record_id, audio_hash),
        "tasks_removed": remove_task_files(record_id),
    }
