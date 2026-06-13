import json
import logging
import mimetypes
import re
from urllib import parse

from config import PUBLIC_DIR, RESULTS_DIR, ADMIN_TOKEN
from http_utils import api_error, bytes_response, file_response, json_response, read_json, redirect_response
from service import delete_result, get_provider_config, poll_task, submit_recognition, upload_audio
from storage import get_audio_meta, get_audio_path, manifest_path, read_json_file, result_dir
from utils import normalized_path, safe_relative_path

# RECORD_RE: 用于校验 Record ID / 哈希值的正则表达式 (支持时间戳命名规则以及 SHA256 哈希值规则)
RECORD_RE = r"[0-9]{8}-[0-9]{6}-[a-f0-9]{8}|[a-f0-9]{64}"
logger = logging.getLogger("server_asr.routes")


def check_auth(environ) -> bool:
    """
    检查请求的身份凭证校验：
    若服务端全局配置了 ADMIN_TOKEN，则检查请求头部中的 HTTP_AUTHORIZATION 是否包含匹配的 Bearer 令牌。
    """
    if not ADMIN_TOKEN:
        return True
    auth_header = environ.get("HTTP_AUTHORIZATION", "")
    return auth_header == f"Bearer {ADMIN_TOKEN}"


def handle_results():
    """
    获取所有转写历史结果记录：
    遍历 results 目录下每个记录文件夹中的 `manifest.json` 元数据配置索引，
    组装包含标题、文件名、字幕行数、创建时间及 HTML 成果页链接在内的列表，并按创建时间倒序排列返回。
    """
    items = []
    if RESULTS_DIR.exists():
        for manifest_file in RESULTS_DIR.glob("*/manifest.json"):
            try:
                manifest = read_json_file(manifest_file)
            except (OSError, json.JSONDecodeError):
                continue
            html_url = manifest.get("urls", {}).get("html")
            if not html_url:
                continue
            record_id = manifest.get("record_id") or manifest_file.parent.name
            created_at = int(manifest.get("created_at") or manifest_file.stat().st_mtime)
            items.append({
                "record_id": record_id,
                "title": manifest.get("title") or manifest.get("filename") or record_id,
                "filename": manifest.get("filename") or "",
                "cues": manifest.get("cues") or 0,
                "created_at": created_at,
                "html_url": html_url,
            })
    # 按创建时间从新到旧排序
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return "200 OK", {"ok": True, "items": items}


def handle_upload(environ, query: dict):
    """音频文件上传接口的路由处理器（委托给 service.upload_audio）。"""
    return "200 OK", upload_audio(environ, query)


def handle_recognize(environ, payload: dict):
    """提交 ASR 语音识别引擎转写任务的路由处理器（委托给 service.submit_recognition）。"""
    return "200 OK", submit_recognition(environ, payload)


def handle_status(query: dict, payload: dict | None = None):
    """
    轮询/查询 ASR 转写任务处理进度的路由处理器（委托给 service.poll_task）。
    兼容 GET 查询参数及 POST JSON 载荷两种方式传参获取 `task_id`。
    """
    payload = payload or {}
    task_id = str(payload.get("task_id") or (query.get("task_id") or [""])[0])
    if not task_id:
        return api_error("task_id is required")
    return poll_task(task_id, payload)


def handle_delete(payload: dict):
    """删除转写结果及关联音频等所有历史物理文件的路由处理器（委托给 service.delete_result）。"""
    record_id = str(payload.get("record_id") or "")
    if not record_id:
        return api_error("record_id is required")
    return "200 OK", delete_result(record_id)


def serve_audio(start_response, environ, path: str):
    """
    音频资源文件直通读取服务：
    路由匹配格式：`/media/audio/<record_id>/<filename>`。
    在校验 record_id 安全性后，读取配置的音频路径，利用 file_response 流式输出。
    """
    match = re.fullmatch(rf"/media/audio/({RECORD_RE})/(.+)", path)
    if not match:
        logger.warning(f"serve_audio: invalid path format '{path}'")
        return json_response(start_response, "404 Not Found", {"ok": False, "error": "not found"})
    record_id, _ = match.groups()
    meta = get_audio_meta(record_id)
    file_path = get_audio_path(meta)
    return file_response(start_response, environ, file_path, meta.get("content_type") or mimetypes.guess_type(file_path.name)[0])


def serve_result(start_response, environ, path: str):
    """
    转写成果及字幕网页静态资源托管服务：
    路由匹配格式：`/results/<record_id>/[relative_path]`。
    如果未指定后缀具体文件路径，且 `manifest.json` 存在，则自动重定向到该记录对应的 HTML 预览网页。
    """
    match = re.fullmatch(rf"/results/({RECORD_RE})(?:/(.*))?", path)
    if not match:
        logger.warning(f"serve_result: invalid path format '{path}'")
        return json_response(start_response, "404 Not Found", {"ok": False, "error": "not found"})
    record_id, rel = match.groups()
    manifest = manifest_path(record_id)
    # 不带具体文件路径时，执行重定向到成果网页
    if not rel:
        if manifest.exists():
            html_url = read_json_file(manifest).get("urls", {}).get("html")
            if html_url:
                logger.info(f"serve_result redirect record '{record_id}' -> {html_url}")
                return redirect_response(start_response, html_url)
        logger.warning(f"serve_result record '{record_id}' manifest not found")
        return json_response(start_response, "404 Not Found", {"ok": False, "error": "result not found"})
    
    # 拼接安全相对路径，输出对应物理资源文件
    rel_path = safe_relative_path(rel)
    file_path = result_dir(record_id) / rel_path
    return file_response(start_response, environ, file_path)


def serve_public_asset(start_response, environ, path: str):
    """
    主控制台公用前端静态资源托管服务：
    路由匹配格式：`/assets/<relative_path>`，托管 `/public/assets` 目录下的 CSS、JS 及图片文件。
    安全限制：禁止请求任何包含以 `.` 开头的文件路径以防遍历攻击。
    """
    match = re.fullmatch(r"/assets/(.+)", path)
    if not match:
        logger.warning(f"serve_public_asset: invalid format '{path}'")
        return json_response(start_response, "404 Not Found", {"ok": False, "error": "not found"})
    rel_path = safe_relative_path(match.group(1))
    if any(part.startswith(".") for part in rel_path.parts):
        logger.warning(f"serve_public_asset: dotfile path blocked '{path}'")
        return json_response(start_response, "404 Not Found", {"ok": False, "error": "not found"})
    return file_response(start_response, environ, PUBLIC_DIR / "assets" / rel_path)


def application(environ, start_response):
    """
    WSGI 核心应用程序入口方法：
    1. 提供跨域预检请求（OPTIONS）的 204 无内容响应支持。
    2. 对 `/api/` 路由进行安全凭证身份令牌验证。
    3. 解析路径及请求方法，分发执行对应的路由控制层逻辑。
    4. 兜底捕获 HTTP 404 (Not Found) 与 HTTP 500 (Internal Server Error) 系统异常并规范输出。
    """
    method = environ["REQUEST_METHOD"]
    path = normalized_path(environ)
    parsed_query = parse.parse_qs(environ.get("QUERY_STRING", ""))

    logger.debug(f"Request: {method} {path} (query: {parsed_query})")

    # 1. CORS 跨域请求预检
    if method == "OPTIONS":
        return bytes_response(start_response, "204 No Content", b"", "text/plain")
    
    # 2. 安全鉴权校验
    if path.startswith("/api/") and not check_auth(environ):
        return json_response(start_response, "401 Unauthorized", {"ok": False, "error": "Unauthorized: Invalid or missing admin token"})

    try:
        # 3. 路由分发逻辑
        # 主页控制台
        if path == "/" and method == "GET":
            logger.info("Serving main index.html page")
            return file_response(start_response, environ, PUBLIC_DIR / "index.html", "text/html; charset=utf-8")
        # 静态资源
        if path.startswith("/assets/") and method in {"GET", "HEAD"}:
            logger.debug(f"Serving public asset '{path}'")
            return serve_public_asset(start_response, environ, path)
        # 健康检查
        if path == "/healthz" and method == "GET":
            return json_response(start_response, "200 OK", {"ok": True})
        # ASR 服务商支持目录列表查询
        if path == "/api/providers" and method == "GET":
            logger.debug("API hit: /api/providers")
            return json_response(start_response, "200 OK", get_provider_config())
        # 音频上传
        if path == "/api/upload" and method == "POST":
            logger.info("API hit: /api/upload")
            status, body = handle_upload(environ, parsed_query)
            logger.info(f"API upload completed: {status}")
            return json_response(start_response, status, body)
        # 提交识别
        if path == "/api/recognize" and method == "POST":
            logger.info("API hit: /api/recognize")
            status, body = handle_recognize(environ, read_json(environ))
            logger.info(f"API recognize status: {status}")
            return json_response(start_response, status, body)
        # 轮询状态 (支持 GET)
        if path == "/api/status" and method == "GET":
            logger.debug("API hit: /api/status (GET)")
            status, body = handle_status(parsed_query)
            return json_response(start_response, status, body)
        # 轮询状态 (支持 POST)
        if path == "/api/status" and method == "POST":
            logger.debug("API hit: /api/status (POST)")
            status, body = handle_status(parsed_query, read_json(environ))
            return json_response(start_response, status, body)
        # 获取转写记录历史列表
        if path == "/api/results" and method == "GET":
            logger.debug("API hit: /api/results")
            status, body = handle_results()
            return json_response(start_response, status, body)
        # 删除转写记录历史
        if path == "/api/delete" and method == "POST":
            logger.info("API hit: /api/delete")
            status, body = handle_delete(read_json(environ))
            logger.info(f"API delete result: {status}")
            return json_response(start_response, status, body)
        # 音频直通流媒体分片读取
        if path.startswith("/media/audio/") and method in {"GET", "HEAD"}:
            logger.debug(f"Serving media audio '{path}'")
            return serve_audio(start_response, environ, path)
        # 转写成果页面及字幕静态资源读取
        if path.startswith("/results/") and method in {"GET", "HEAD"}:
            logger.debug(f"Serving ASR result asset '{path}'")
            return serve_result(start_response, environ, path)
        
        # 兜底 404
        logger.warning(f"Path not found: {method} {path}")
        return json_response(start_response, "404 Not Found", {"ok": False, "error": "not found"})
    except Exception as exc:
        # 兜底 500
        logger.error(f"Internal server error in request {method} {path}: {exc}", exc_info=True)
        return json_response(start_response, "500 Internal Server Error", {"ok": False, "error": "Internal Server Error. Please check server logs."})
