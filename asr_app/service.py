import json
import mimetypes
import time
import uuid
from pathlib import Path

from .http_utils import absolute_url
from .storage import (
    get_audio_meta,
    get_audio_meta_by_hash,
    manifest_path,
    read_json_file,
    result_dir,
    result_url,
    save_upload,
    task_path,
    delete_record,
    write_json,
    write_text,
)
from .subtitles import TEMPLATE_VERSION, extract_cues, make_result_html, make_srt, make_txt, make_vtt
from .utils import clean_name, safe_relative_path
from .volcengine import volc_query, volc_submit


PROCESSING_STATUSES = {"20000001", "20000002"}


def write_artifacts(task: dict, volc_json: dict):
    cues = extract_cues(volc_json)
    if not cues:
        raise RuntimeError("Volcengine result has no utterance timestamps.")
    record_id = task["record_id"]
    audio_hash = task["audio_hash"]
    title = clean_name(task.get("title") or Path(task.get("filename", "audio")).stem)
    meta = get_audio_meta(record_id)
    audio_src = meta["audio_url"]
    audio_type = meta.get("content_type") or mimetypes.guess_type(meta["filename"])[0] or "application/octet-stream"
    base = result_dir(record_id)
    keys = {
        "raw": ("raw", f"{title}.volcengine.json"),
        "txt": ("transcript", f"{title}.txt"),
        "srt": ("subtitles", f"{title}.srt"),
        "vtt": ("subtitles", f"{title}.vtt"),
        "html": ("", f"{title}_字幕跳转.html"),
    }
    write_json(base / keys["raw"][0] / keys["raw"][1], volc_json)
    write_text(base / keys["txt"][0] / keys["txt"][1], make_txt(cues))
    write_text(base / keys["srt"][0] / keys["srt"][1], make_srt(cues))
    write_text(base / keys["vtt"][0] / keys["vtt"][1], make_vtt(cues))
    write_text(base / keys["html"][1], make_result_html(title, cues, audio_src, audio_type))
    urls = {name: result_url(record_id, *[part for part in parts if part]) for name, parts in keys.items()}
    manifest = {
        "record_id": record_id,
        "audio_hash": audio_hash,
        "title": title,
        "filename": meta["filename"],
        "audio_url": audio_src,
        "audio_size": meta["size"],
        "cues": len(cues),
        "urls": urls,
        "template_version": TEMPLATE_VERSION,
        "created_at": int(time.time()),
    }
    write_json(manifest_path(record_id), manifest)
    return manifest


def result_file_from_url(record_id: str, url: str) -> Path | None:
    prefix = f"/results/{record_id}/"
    if not url.startswith(prefix):
        return None
    return result_dir(record_id) / safe_relative_path(url[len(prefix):])


def html_current(manifest: dict) -> bool:
    record_id = manifest.get("record_id")
    html_url = manifest.get("urls", {}).get("html", "")
    html_path = result_file_from_url(record_id, html_url) if record_id else None
    return bool(
        manifest.get("template_version") == TEMPLATE_VERSION
        and html_path
        and html_path.exists()
    )


def refresh_cached_manifest(record_id: str) -> dict:
    manifest = read_json_file(manifest_path(record_id))
    if html_current(manifest):
        return manifest

    raw_url = manifest.get("urls", {}).get("raw", "")
    raw_path = result_file_from_url(record_id, raw_url)
    if not raw_path or not raw_path.exists():
        return manifest
    return write_artifacts(
        {
            "record_id": record_id,
            "audio_hash": manifest["audio_hash"],
            "title": manifest.get("title") or Path(manifest.get("filename", "audio")).stem,
            "filename": manifest.get("filename", "audio"),
        },
        read_json_file(raw_path),
    )


def upload_audio(environ, query: dict):
    meta = save_upload(environ, query)
    response_body = {
        "ok": True,
        "record_id": meta["record_id"],
        "audio_hash": meta["audio_hash"],
        "filename": meta["filename"],
        "audio_url": meta["audio_url"],
        "size": meta["size"],
        "duplicate": bool(meta.get("duplicate")),
    }
    manifest = manifest_path(meta["record_id"])
    if manifest.exists():
        response_body["cached"] = True
        response_body["manifest"] = refresh_cached_manifest(meta["record_id"])
    return response_body


def submit_recognition(environ, payload: dict):
    record_id = str(payload.get("record_id") or "")
    audio_hash = str(payload.get("audio_hash") or "").lower()
    title = clean_name(payload.get("title") or payload.get("filename") or "audio")
    force = bool(payload.get("force"))
    if record_id:
        meta = get_audio_meta(record_id)
    else:
        meta = get_audio_meta_by_hash(audio_hash)
        if not meta:
            raise RuntimeError("audio file has not been uploaded")
        record_id = meta["record_id"]

    audio_hash = meta["audio_hash"]
    manifest = manifest_path(record_id)
    if manifest.exists() and not force:
        return {"ok": True, "status": "done", "cached": True, "manifest": refresh_cached_manifest(record_id)}

    volc_audio_url = absolute_url(environ, meta["audio_url"])
    volc_task_id, logid = volc_submit(volc_audio_url)
    task_id = str(uuid.uuid4())
    task = {
        "task_id": task_id,
        "status": "processing",
        "filename": meta["filename"],
        "title": title,
        "record_id": record_id,
        "audio_hash": audio_hash,
        "audio_url": meta["audio_url"],
        "volc_audio_url": volc_audio_url,
        "volc_task_id": volc_task_id,
        "volc_logid": logid,
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
    }
    write_json(task_path(task_id), task)
    return {"ok": True, "status": "processing", "task_id": task_id}


def poll_task(task_id: str):
    path = task_path(task_id)
    if not path.exists():
        return "404 Not Found", {"ok": False, "error": "task not found"}
    task = read_json_file(path)
    if task.get("status") == "done":
        return "200 OK", {"ok": True, "status": "done", "manifest": task.get("manifest")}
    if task.get("status") == "failed":
        return "200 OK", {"ok": True, "status": "failed", "error": task.get("error")}

    status, message, parsed, _ = volc_query(task["volc_task_id"], task["volc_logid"])
    task["updated_at"] = int(time.time())
    task["volc_status"] = status
    task["volc_message"] = message
    if status == "20000000":
        manifest = write_artifacts(task, parsed)
        task["status"] = "done"
        task["manifest"] = manifest
        write_json(path, task)
        return "200 OK", {"ok": True, "status": "done", "manifest": manifest}
    if status in PROCESSING_STATUSES:
        write_json(path, task)
        return "200 OK", {"ok": True, "status": "processing", "message": message}

    task["status"] = "failed"
    task["error"] = f"{status} {message}"
    write_json(path, task)
    return "200 OK", {"ok": True, "status": "failed", "error": task["error"]}


def delete_result(record_id: str):
    return delete_record(record_id)
