import hashlib
import json
import re
import shutil
import time
import uuid
from pathlib import Path

from config import AUDIO_DIR, DATA_DIR, HASH_DIR, RESULTS_DIR, TASKS_DIR, TMP_DIR, env
from utils import audio_ext, clean_name, quote_path, safe_relative_path, valid_record_id


def write_json(path: Path, payload: dict):
    """辅助函数：自动创建父目录，并将字典以格式化的 JSON 字符串写入指定路径（UTF-8 编码）。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")


def read_json_file(path: Path) -> dict:
    """辅助函数：读取并解析指定路径下的 JSON 文件，返回 Python 字典对象。"""
    return json.loads(path.read_text("utf-8"))


def write_text(path: Path, text: str):
    """辅助函数：自动创建父目录，并将文本内容以 UTF-8 编码写入文件。"""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, "utf-8")


def new_record_id() -> str:
    """
    生成全局唯一的转写记录 ID (Record ID)。
    格式：`YYYYMMDD-HHMMSS-8位UUID哈希值`，便于人工阅读并防碰撞。
    """
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{uuid.uuid4().hex[:8]}"


# ── 各文件/目录物理路径映射工具 ───────────────────────────────────────────────

def audio_folder(record_id: str) -> Path:
    """获取指定记录的音频目录。"""
    return AUDIO_DIR / record_id


def audio_meta_path(record_id: str) -> Path:
    """获取指定记录的音频元数据文件 (meta.json) 的存放路径。"""
    return audio_folder(record_id) / "meta.json"


def hash_index_path(audio_hash: str) -> Path:
    """获取指定音频 SHA256 哈希值去重索引 JSON 文件的存放路径。"""
    return HASH_DIR / f"{audio_hash}.json"


def result_dir(record_id: str) -> Path:
    """获取指定记录转写成果物理目录的存放路径。"""
    return RESULTS_DIR / record_id


def manifest_path(record_id: str) -> Path:
    """获取指定记录转写结果元配置索引文件 (manifest.json) 的存放路径。"""
    return result_dir(record_id) / "manifest.json"


def task_path(task_id: str) -> Path:
    """获取指定 ASR 异步转写任务进度缓存文件 (task_id.json) 的存放路径。"""
    return TASKS_DIR / f"{task_id}.json"


# ── 各资源 URL 前缀组装工具 ───────────────────────────────────────────────

def audio_url(record_id: str, filename: str) -> str:
    """根据记录 ID 与文件名，生成用于直通流媒体播放的 URL 路径，自动转义特殊字符。"""
    return f"/media/audio/{record_id}/{quote_path(filename)}"


def result_url(record_id: str, *parts: str) -> str:
    """根据记录 ID 与相对路径，生成用于成果物读取下载的 URL 路径，自动转义特殊字符。"""
    return f"/results/{record_id}/{quote_path(*parts)}"


# ── 数据持久化操作 ────────────────────────────────────────────────────────────

def save_upload(environ, query: dict):
    """
    分块保存上传音频的业务逻辑核心：
    1. 提取并校验客户端参数：原始文件名、Content-Type、以及前端对音频计算好的 SHA256 唯一哈希值。
    2. 上传体积合法性校验（防溢出）。
    3. 去重拦截校验：
       根据 SHA256 哈希匹配 `HASH_DIR` 中的映射索引，若存在完全相同的音频历史，直接拦截写入并复用历史，
       同时在返回字典中标记 `duplicate=True`。秒级极速命中，极大降低了重复 ASR 扣费的概率。
    4. 分块写入临时文件 (`TMP_DIR`)，防写入中断污染。同时在服务端独立计算 SHA256 并与客户端提供的哈希强制校验比对。
    5. 校验通过后，将临时文件重命名并剪切到正式的物理存放目录 (`AUDIO_DIR`) 下。
    6. 保存音频的基本参数文件 (meta.json) 并创建全局哈希到 Record ID 的对应映射文件，以备下次匹配去重。
    """
    filename = clean_name((query.get("filename") or ["audio"])[0])
    content_type = (query.get("content_type") or [environ.get("CONTENT_TYPE") or "application/octet-stream"])[0]
    expected_hash = str((query.get("sha256") or [""])[0]).lower()
    
    # 严格校验哈希值必须是 64 字符的 16 进制字符串
    if not re.fullmatch(r"[a-f0-9]{64}", expected_hash):
        raise RuntimeError("sha256 must be a 64-character hex string")

    length = int(environ.get("CONTENT_LENGTH") or 0)
    max_bytes = int(float(env("MAX_UPLOAD_MB", "500")) * 1024 * 1024)
    if length <= 0:
        raise RuntimeError("empty upload")
    if length > max_bytes:
        raise RuntimeError(f"file is larger than MAX_UPLOAD_MB={env('MAX_UPLOAD_MB', '500')}")

    # 重构文件名，保证后缀与实际 Content-Type 匹配
    filename = clean_name(Path(filename).stem) + audio_ext(filename, content_type)
    
    # 查找历史哈希索引，判断文件是否已被上传过
    index_path = hash_index_path(expected_hash)
    existing_meta = get_audio_meta_by_hash(expected_hash)
    
    # 若存在，直接使用历史的 record_id，否则生成新纪录
    record_id = existing_meta["record_id"] if existing_meta else new_record_id()
    folder = audio_folder(record_id)
    folder.mkdir(parents=True, exist_ok=True)
    
    # 创建临时上传中文件路径，防止多个并发上传时相互影响
    tmp_path = TMP_DIR / f"{expected_hash}-{uuid.uuid4().hex}.upload"
    final_path = folder / filename

    hasher = hashlib.sha256()
    remaining = length
    
    # 流式读取 input 缓冲区，以最大 1MB 的块写入磁盘并计算哈希，优化大内存开销
    with tmp_path.open("wb") as handle:
        while remaining > 0:
            chunk = environ["wsgi.input"].read(min(1024 * 1024, remaining))
            if not chunk:
                break
            hasher.update(chunk)
            handle.write(chunk)
            remaining -= len(chunk)

    # 严密比对：在服务端计算的哈希值与客户端计算的哈希值是否一致，防止文件上传损坏或恶意篡改
    actual_hash = hasher.hexdigest()
    if actual_hash != expected_hash:
        tmp_path.unlink(missing_ok=True)
        raise RuntimeError(f"sha256 mismatch: {actual_hash}")

    # 若是去重命中，清理临时文件，直接返回历史音频配置
    if existing_meta:
        tmp_path.unlink(missing_ok=True)
        meta = dict(existing_meta)
        meta["duplicate"] = True
        meta["updated_at"] = int(time.time())
        return meta

    # 移动文件到最终音频文件物理位置
    if final_path.exists():
        tmp_path.unlink(missing_ok=True)
    else:
        tmp_path.replace(final_path)

    # 封装 meta 数据结构并持久化
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
    # 写入去重哈希索引关系映射，确保下次相同的上传秒级秒开
    write_json(index_path, {"record_id": record_id, "audio_hash": expected_hash, "created_at": meta["created_at"]})
    return meta


def get_audio_meta(record_id: str) -> dict:
    """获取指定记录 ID 的音频元数据 (meta.json)；若不存在，抛出异常。"""
    if not valid_record_id(record_id):
        raise RuntimeError("invalid audio record id")
    path = audio_meta_path(record_id)
    if not path.exists():
        raise RuntimeError("audio file has not been uploaded")
    meta = read_json_file(path)
    meta.setdefault("record_id", record_id)
    return meta


def get_audio_meta_by_hash(audio_hash: str) -> dict | None:
    """
    根据 SHA256 哈希值反查已注册的音频元数据。
    支持全新的哈希目录检索，并兼容历史版本中以 `audio_hash` 直接作为 record_id 命名的老目录数据。
    """
    if not re.fullmatch(r"[a-f0-9]{64}", audio_hash):
        raise RuntimeError("invalid audio hash")
    index_path = hash_index_path(audio_hash)
    if index_path.exists():
        index = read_json_file(index_path)
        return get_audio_meta(str(index["record_id"]))

    # 兼容低版本物理目录回退方案
    legacy_path = AUDIO_DIR / audio_hash / "meta.json"
    if legacy_path.exists():
        meta = read_json_file(legacy_path)
        meta.setdefault("record_id", audio_hash)
        return meta
    return None


def get_audio_path(meta: dict) -> Path:
    """将元数据中记录的音频相对路径解析为物理磁盘绝对路径。"""
    return DATA_DIR / safe_relative_path(meta["path"])


def remove_hash_indexes(record_id: str, audio_hash: str = "") -> int:
    """
    清理无用的哈希映射关系索引：
    在删除某条转写记录时，必须将对应的哈希去重索引一同清除，以防未来新上传的同名同哈希音频发生空悬引用。
    """
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
        # 只要索引内映射的 record_id 与被删记录匹配，则移除
        if trust_filename or payload.get("record_id") == record_id:
            path.unlink(missing_ok=True)
            removed += 1

    # 直接移除指定哈希匹配的文件
    if re.fullmatch(r"[a-f0-9]{64}", audio_hash or ""):
        remove_if_matches(hash_index_path(audio_hash), trust_filename=True)

    # 兜底遍历 hashes/ 目录，确保清理彻底
    if HASH_DIR.exists():
        for index_path in HASH_DIR.glob("*.json"):
            remove_if_matches(index_path)
    return removed


def remove_task_files(record_id: str) -> int:
    """清除任务目录中，与要被删除的 record_id 关联的所有异步任务 JSON 状态缓存文件。"""
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
    """
    彻底物理删除一条转写记录所有资源的一站式接口：
    1. 校验 ID 合法性。
    2. 获取对应的音频哈希指纹。
    3. 物理删除音频物理目录 (`AUDIO_DIR/<record_id>`) 及其下的音频实体。
    4. 物理删除识别生成物目录 (`RESULTS_DIR/<record_id>`)（包含文本、字幕、HTML 等全部生成网页）。
    5. 清除与该记录相关联的去重哈希索引文件。
    6. 清除关联的任务 JSON 临时缓存文件。
    """
    if not valid_record_id(record_id):
        raise RuntimeError("invalid record id")

    audio_hash = ""
    meta_path = audio_meta_path(record_id)
    manifest = manifest_path(record_id)
    # 多层提取哈希指纹以防 meta.json 损坏时从成果物 manifest 中读取
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

    # 删除音频实体目录
    audio_removed = False
    folder = audio_folder(record_id)
    if folder.exists():
        shutil.rmtree(folder)
        audio_removed = True

    # 删除转毕成果物目录
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
