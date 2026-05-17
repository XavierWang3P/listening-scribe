import json
import logging
import mimetypes
import time
import uuid
from pathlib import Path

logger = logging.getLogger("server_asr.service")

from config import env
from http_utils import absolute_url
from providers.providers import PROVIDERS, ensure_provider_supported, normalize_provider, provider_catalog
from storage import (
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
from subtitles.subtitles import (
    TEMPLATE_VERSION,
    extract_cues,
    extract_cues_funasr,
    extract_cues_tencent,
    make_result_html,
    make_srt,
    make_txt,
    make_vtt,
)
from utils import clean_name, safe_relative_path
from providers.volcengine import volc_query, volc_submit


# ── 辅助：Provider 认证参数提取 ──────────────────────────────────────────────

def _get_credential(credentials: dict, *keys: str) -> str:
    """从 credentials 字典中按优先顺序取第一个非空值。"""
    for k in keys:
        v = (credentials.get(k) or "").strip()
        if v:
            return v
    return ""


# ── 写入识别结果文件 ──────────────────────────────────────────────────────────

def write_artifacts(task: dict, cues: list[dict], raw_data: object = None):
    """将识别结果写入文件系统并返回 manifest。

    Args:
        task:     任务信息字典（含 record_id, title 等字段）
        cues:     标准字幕列表 [{start, end, text}, ...]
        raw_data: 原始 API 响应（用于保存 raw JSON）
    """
    record_id = task["record_id"]
    audio_hash = task["audio_hash"]
    title = clean_name(task.get("title") or Path(task.get("filename", "audio")).stem)
    provider = task.get("provider", "volcengine")
    meta = get_audio_meta(record_id)
    audio_src = meta["audio_url"]
    audio_type = meta.get("content_type") or mimetypes.guess_type(meta["filename"])[0] or "application/octet-stream"
    base = result_dir(record_id)
    has_timestamps = bool(cues) and PROVIDERS.get(provider, {}).get("has_timestamps", True)

    # raw JSON（各 provider 格式不同）
    raw_filename = f"{title}.{provider}.json"
    raw_dir = "raw"
    write_json(base / raw_dir / raw_filename, raw_data if raw_data is not None else {})
    raw_url = result_url(record_id, raw_dir, raw_filename)

    urls: dict[str, str] = {"raw": raw_url}

    # txt 所有 provider 都生成
    txt_filename = f"{title}.txt"
    write_text(base / "transcript" / txt_filename, make_txt(cues) if cues else (task.get("plain_text") or "") + "\n")
    urls["txt"] = result_url(record_id, "transcript", txt_filename)

    if has_timestamps:
        srt_filename = f"{title}.srt"
        vtt_filename = f"{title}.vtt"
        write_text(base / "subtitles" / srt_filename, make_srt(cues))
        write_text(base / "subtitles" / vtt_filename, make_vtt(cues))
        write_text(base / "index.html", make_result_html(title, cues, audio_src, audio_type))
        urls["srt"] = result_url(record_id, "subtitles", srt_filename)
        urls["vtt"] = result_url(record_id, "subtitles", vtt_filename)
        urls["html"] = result_url(record_id, "index.html")

    manifest = {
        "record_id": record_id,
        "audio_hash": audio_hash,
        "title": title,
        "filename": meta["filename"],
        "audio_url": audio_src,
        "audio_size": meta["size"],
        "provider": provider,
        "cues": len(cues),
        "has_timestamps": has_timestamps,
        "urls": urls,
        "template_version": TEMPLATE_VERSION,
        "created_at": int(time.time()),
    }
    write_json(manifest_path(record_id), manifest)
    return manifest


def write_artifacts_volc(task: dict, volc_json: dict):
    """兼容旧有火山引擎调用路径的封装。"""
    cues = extract_cues(volc_json)
    if not cues:
        raise RuntimeError("Volcengine result has no utterance timestamps.")
    return write_artifacts(task, cues, raw_data=volc_json)


# ── 缓存刷新 ──────────────────────────────────────────────────────────────────

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
    # Qwen-ASR（无时间戳）结果无 HTML，无需刷新 HTML
    if not manifest.get("has_timestamps", True):
        return manifest
    if html_current(manifest):
        return manifest

    raw_url = manifest.get("urls", {}).get("raw", "")
    raw_path = result_file_from_url(record_id, raw_url)
    if not raw_path or not raw_path.exists():
        return manifest

    provider = manifest.get("provider", "volcengine")
    raw_json = read_json_file(raw_path)
    task_stub = {
        "record_id": record_id,
        "audio_hash": manifest["audio_hash"],
        "title": manifest.get("title") or Path(manifest.get("filename", "audio")).stem,
        "filename": manifest.get("filename", "audio"),
        "provider": provider,
    }

    if provider == "volcengine":
        cues = extract_cues(raw_json)
    elif provider == "aliyun_fun":
        # raw_json 存储的是 sentences 列表
        cues = extract_cues_funasr(raw_json if isinstance(raw_json, list) else [])
    elif provider == "tencent":
        cues = extract_cues_tencent(raw_json if isinstance(raw_json, list) else [])
    else:
        return manifest  # 其他 provider 暂不支持重新生成

    return write_artifacts(task_stub, cues, raw_data=raw_json)


# ── 上传音频 ──────────────────────────────────────────────────────────────────

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
    logger.info(f"Audio file uploaded: record_id={meta['record_id']}, duplicate={meta.get('duplicate')}, cached={response_body.get('cached', False)}")
    return response_body


# ── 提交识别 ──────────────────────────────────────────────────────────────────

def submit_recognition(environ, payload: dict):
    record_id = str(payload.get("record_id") or "")
    audio_hash = str(payload.get("audio_hash") or "").lower()
    title = clean_name(payload.get("title") or payload.get("filename") or "audio")
    force = bool(payload.get("force"))
    provider = normalize_provider(str(payload.get("provider") or "volcengine"))
    credentials = payload.get("credentials") if isinstance(payload.get("credentials"), dict) else {}

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
        logger.debug(f"ASR recognition cache hit: record_id={record_id}")
        return {"ok": True, "status": "done", "cached": True, "manifest": refresh_cached_manifest(record_id)}

    ensure_provider_supported(provider)
    logger.info(f"Submitting ASR recognition task: record_id={record_id}, provider={provider}, force={force}")

    # ── 检测是否启用云存储上传（COS / OSS），优先使用云存储以支持零内网穿透本地部署 ──
    from cloud_storage import is_cloud_storage_enabled, cos_upload, oss_upload
    from storage import audio_folder

    audio_url = absolute_url(environ, meta["audio_url"])
    cloud_key = None
    cloud_provider = None

    if is_cloud_storage_enabled():
        local_path = audio_folder(record_id) / meta["filename"]
        if local_path.exists():
            provider_type = (env("UPLOAD_PROVIDER") or "").lower().strip()
            cloud_provider = provider_type
            cloud_key = f"listening-scribe/{record_id}/{meta['filename']}"
            if provider_type == "cos":
                audio_url = cos_upload(local_path, cloud_key)
            elif provider_type == "oss":
                audio_url = oss_upload(local_path, cloud_key)

    task_id = str(uuid.uuid4())
    task = {
        "task_id": task_id,
        "status": "processing",
        "provider": provider,
        "filename": meta["filename"],
        "title": title,
        "record_id": record_id,
        "audio_hash": audio_hash,
        "audio_url": meta["audio_url"],
        "provider_audio_url": audio_url,
        "cloud_key": cloud_key,
        "cloud_provider": cloud_provider,
        "created_at": int(time.time()),
        "updated_at": int(time.time()),
    }

    # ── Qwen-ASR：启动后台线程执行同步识别并返回 ──────────────────────────────
    # 原因：Qwen-ASR 为同步 API 调用，单次耗时达数十秒，在单线程 WSGI 服务下会阻塞整个服务，
    # 且极易触发 Nginx / 反向代理的 60 秒 read timeout。因此采用后台线程异步执行。
    if provider == "aliyun_qwen":
        import threading
        api_key = _get_credential(credentials, "api_key")
        task["credential_source"] = "env" if env("DASHSCOPE_API_KEY") else "frontend"
        task["api_key_snapshot"] = api_key
        write_json(task_path(task_id), task)

        def run_qwen_async():
            try:
                from providers.aliyun_qwen import qwen_recognize
                plain_text = qwen_recognize(task["provider_audio_url"], api_key=api_key)
                task["plain_text"] = plain_text
                manifest = write_artifacts(task, cues=[], raw_data={"text": plain_text})
                task["status"] = "done"
                task["manifest"] = manifest
            except Exception as exc:
                task["status"] = "failed"
                err_msg = str(exc)
                if "The audio is too long" in err_msg:
                    task["error"] = "阿里通义千问 Qwen-ASR 限制单次识别的音频时长需在 3 分钟以内（文件小于 10MB）。对于较长的音频文件，请在服务商中选择「阿里 Fun-ASR」或「阿里 Paraformer」（它们与 Qwen-ASR 共享相同的 API Key），不仅支持长音频转译，而且能生成带时间戳的完整字幕页面！"
                else:
                    task["error"] = err_msg
            finally:
                _cleanup_cloud_storage(task)
                write_json(task_path(task_id), task)

        threading.Thread(target=run_qwen_async, daemon=True).start()
        return {"ok": True, "status": "processing", "task_id": task_id}

    # ── Fun-ASR：异步提交 ──────────────────────────────────────────────────────
    elif provider == "aliyun_fun":
        from providers.aliyun_fun_asr import fun_submit, FUNASR_MODEL_FUNASR
        api_key = _get_credential(credentials, "api_key")
        task["credential_source"] = "env" if env("DASHSCOPE_API_KEY") else "frontend"
        provider_task_id = fun_submit(audio_url, api_key=api_key, model=FUNASR_MODEL_FUNASR)
        task["provider_task_id"] = provider_task_id

    # ── Paraformer：异步提交（与 Fun-ASR 相同 API，仅 model 不同） ──────────────────
    elif provider == "aliyun_paraformer":
        from providers.aliyun_fun_asr import fun_submit, FUNASR_MODEL_PARAFORMER
        api_key = _get_credential(credentials, "api_key")
        task["credential_source"] = "env" if env("DASHSCOPE_API_KEY") else "frontend"
        provider_task_id = fun_submit(audio_url, api_key=api_key, model=FUNASR_MODEL_PARAFORMER)
        task["provider_task_id"] = provider_task_id

    # ── 腾讯云语音识别：异步提交 ──────────────────────────────────────────────────────
    elif provider == "tencent":
        from providers.tencent_asr import tencent_submit
        secret_id = _get_credential(credentials, "secret_id")
        secret_key = _get_credential(credentials, "secret_key")
        task["credential_source"] = "env" if env("TENCENT_SECRET_ID") else "frontend"
        provider_task_id = tencent_submit(audio_url, secret_id=secret_id, secret_key=secret_key)
        task["provider_task_id"] = provider_task_id

    # ── 火山引擎：异步提交 ────────────────────────────────────────────────────
    elif provider == "volcengine":
        api_key = _get_credential(credentials, "api_key")
        task["credential_source"] = "env" if env("VOLCENGINE_API_KEY") else "frontend"
        volc_task_id, logid = volc_submit(audio_url, api_key=api_key)
        task["provider_task_id"] = volc_task_id
        task["volc_task_id"] = volc_task_id   # 向后兼容
        task["volc_logid"] = logid
        task["volc_audio_url"] = audio_url

    else:
        raise RuntimeError(f"unsupported ASR provider: {provider}")

    write_json(task_path(task_id), task)
    return {"ok": True, "status": "processing", "task_id": task_id}


# ── 轮询任务 ──────────────────────────────────────────────────────────────────

def _cleanup_cloud_storage(task: dict):
    cloud_provider = task.get("cloud_provider")
    cloud_key = task.get("cloud_key")
    if cloud_provider and cloud_key:
        from cloud_storage import cos_delete, oss_delete
        if cloud_provider == "cos":
            cos_delete(cloud_key)
        elif cloud_provider == "oss":
            oss_delete(cloud_key)


def poll_task(task_id: str, payload: dict | None = None):
    path = task_path(task_id)
    if not path.exists():
        logger.warning(f"Polling failed: task_id={task_id} not found")
        return "404 Not Found", {"ok": False, "error": "task not found"}
    task = read_json_file(path)
    logger.debug(f"Polling task status: task_id={task_id}, status={task.get('status')}")

    if task.get("status") == "done":
        return "200 OK", {"ok": True, "status": "done", "manifest": task.get("manifest")}
    if task.get("status") == "failed":
        return "200 OK", {"ok": True, "status": "failed", "error": task.get("error")}

    provider = ensure_provider_supported(task.get("provider") or "volcengine")
    payload = payload or {}
    credentials = payload.get("credentials") if isinstance(payload.get("credentials"), dict) else {}

    task["updated_at"] = int(time.time())

    # ── Qwen-ASR：后台线程异步执行中，此处仅需直接返回当前轮询状态 ──────────
    if provider == "aliyun_qwen":
        return "200 OK", {"ok": True, "status": "processing", "message": "Qwen-ASR 正在后台转译中..."}

    # ── Fun-ASR / Paraformer ──────────────────────────────────────────────────
    elif provider in {"aliyun_fun", "aliyun_paraformer"}:

        from providers.aliyun_fun_asr import fun_query
        api_key = _get_credential(credentials, "api_key")
        status, sentences = fun_query(task["provider_task_id"], api_key=api_key)
        if status == "SUCCEEDED":
            cues = extract_cues_funasr(sentences or [])
            manifest = write_artifacts(task, cues, raw_data=sentences)
            task["status"] = "done"
            task["manifest"] = manifest
            _cleanup_cloud_storage(task)
            write_json(path, task)
            return "200 OK", {"ok": True, "status": "done", "manifest": manifest}
        if status == "FAILED":
            task["status"] = "failed"
            task["error"] = "Fun-ASR task failed"
            _cleanup_cloud_storage(task)
            write_json(path, task)
            return "200 OK", {"ok": True, "status": "failed", "error": task["error"]}
        # PENDING / RUNNING
        write_json(path, task)
        return "200 OK", {"ok": True, "status": "processing", "message": status}

    # ── 腾讯云语音识别 ───────────────────────────────────────────────────────────────
    elif provider == "tencent":
        from providers.tencent_asr import tencent_query
        secret_id = _get_credential(credentials, "secret_id")
        secret_key = _get_credential(credentials, "secret_key")
        try:
            status_str, result_detail = tencent_query(
                task["provider_task_id"], secret_id=secret_id, secret_key=secret_key
            )
        except Exception as exc:
            task["status"] = "failed"
            task["error"] = str(exc)
            _cleanup_cloud_storage(task)
            write_json(path, task)
            return "200 OK", {"ok": True, "status": "failed", "error": task["error"]}

        if status_str == "success":
            cues = extract_cues_tencent(result_detail or [])
            manifest = write_artifacts(task, cues, raw_data=result_detail)
            task["status"] = "done"
            task["manifest"] = manifest
            _cleanup_cloud_storage(task)
            write_json(path, task)
            return "200 OK", {"ok": True, "status": "done", "manifest": manifest}
        # waiting / doing
        write_json(path, task)
        return "200 OK", {"ok": True, "status": "processing", "message": status_str}

    # ── 火山引擎 ─────────────────────────────────────────────────────────────
    elif provider == "volcengine":
        api_key = _get_credential(credentials, "api_key")
        volc_task_id = task.get("provider_task_id") or task.get("volc_task_id", "")
        volc_logid = task.get("volc_logid", "")
        status, message, parsed, _ = volc_query(volc_task_id, volc_logid, api_key=api_key)
        task["volc_status"] = status
        task["volc_message"] = message
        if status == "20000000":
            cues = extract_cues(parsed)
            manifest = write_artifacts_volc(task, parsed)
            task["status"] = "done"
            task["manifest"] = manifest
            _cleanup_cloud_storage(task)
            write_json(path, task)
            return "200 OK", {"ok": True, "status": "done", "manifest": manifest}
        if status in {"20000001", "20000002"}:
            write_json(path, task)
            return "200 OK", {"ok": True, "status": "processing", "message": message}
        task["status"] = "failed"
        task["error"] = f"{status} {message}"
        _cleanup_cloud_storage(task)
        write_json(path, task)
        return "200 OK", {"ok": True, "status": "failed", "error": task["error"]}

    else:
        raise RuntimeError(f"unsupported ASR provider: {provider}")


# ── 其他操作 ──────────────────────────────────────────────────────────────────

def delete_result(record_id: str):
    return delete_record(record_id)


def get_provider_config():
    return provider_catalog()
