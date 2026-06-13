import json
import mimetypes
from pathlib import Path

from config import env


def api_error(message: str, status: str = "400 Bad Request", **extra):
    """
    统一格式的 API 异常响应辅助函数。
    返回 HTTP 状态码及相应的错误描述字典。
    """
    return status, {"ok": False, "error": message, **extra}


def json_response(start_response, status: str, body):
    """
    将字典或列表序列化为 JSON 格式字节流，并生成完整的 HTTP 响应。
    包含基本的 Content-Type、Content-Length 以及 CORS (跨域) 头部信息。
    """
    # 确保中文不被转义为 \uXXXX
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(data))),
        ("Access-Control-Allow-Methods", "GET,POST,OPTIONS"),
        ("Access-Control-Allow-Headers", "content-type, authorization"),
    ]
    # 如果配置了允许跨域的 Origin，则添加 CORS 响应头
    allowed = env("ALLOWED_ORIGIN")
    if allowed:
        headers.append(("Access-Control-Allow-Origin", allowed))
        
    start_response(status, headers)
    return [data]


def bytes_response(start_response, status: str, body: bytes, content_type: str):
    """
    返回原始二进制字节流数据的 HTTP 响应。
    通常用于返回纯文本、图片或其他非 JSON 的二进制媒体资源。
    """
    headers = [
        ("Content-Type", content_type),
        ("Content-Length", str(len(body))),
    ]
    allowed = env("ALLOWED_ORIGIN")
    if allowed:
        headers.append(("Access-Control-Allow-Origin", allowed))
        
    start_response(status, headers)
    return [body]


def redirect_response(start_response, location: str):
    """
    生成 302 Found 重定向响应，导向指定的 URL 地址。
    """
    start_response("302 Found", [("Location", location), ("Content-Length", "0")])
    return [b""]


def read_json(environ) -> dict:
    """
    从 WSGI 服务的输入流中读取并解析 HTTP 请求体中的 JSON 载荷数据。
    """
    length = int(environ.get("CONTENT_LENGTH") or 0)
    # 仅在长度大于 0 时读取输入流，防止无请求体时挂起阻塞
    raw = environ["wsgi.input"].read(length) if length else b"{}"
    return json.loads(raw.decode("utf-8")) if raw else {}


def file_iter(path: Path, start: int, length: int):
    """
    分块读取文件的迭代器生成器。
    按每次最大 1MB 的块大小读取并 yield，避免一次性加载大文件到内存中导致 OOM。
    """
    with path.open("rb") as handle:
        handle.seek(start)
        remaining = length
        while remaining > 0:
            chunk = handle.read(min(1024 * 1024, remaining))
            if not chunk:
                break
            remaining -= len(chunk)
            yield chunk


def parse_range(header: str, size: int):
    """
    解析 HTTP 协议中的 Range 请求头部 (例如 `bytes=100-200` 或 `bytes=-500`)。
    支持音频拖动进度条时的高效分片传输。
    
    返回:
        None: 不是 Range 请求。
        "invalid": Range 范围格式无效或越界。
        (start, end): 有效的分片区间起止字节位置。
    """
    if not header or not header.startswith("bytes="):
        return None
    # 仅提取第一个 Range 分片区间
    value = header[6:].split(",", 1)[0].strip()
    if "-" not in value:
        return None
    start_raw, end_raw = value.split("-", 1)
    
    # 情况 1: `bytes=-500` (请求文件末尾的 500 个字节)
    if start_raw == "":
        suffix = int(end_raw or "0")
        if suffix <= 0:
            return None
        start = max(0, size - suffix)
        end = size - 1
    # 情况 2: `bytes=100-` (从偏移量 100 到文件末尾) 或 `bytes=100-200` (指定范围)
    else:
        start = int(start_raw)
        end = int(end_raw) if end_raw else size - 1
        
    # 区间合法性校验
    if start >= size or end < start:
        return "invalid"
    return start, min(end, size - 1)


def file_response(start_response, environ, path: Path, content_type: str | None = None):
    """
    处理文件的 HTTP 响应，完美支持：
    1. 200 OK 完整文件传输。
    2. 206 Partial Content 断点续传/分片传输（拖动进度条必需）。
    3. HEAD 请求支持（仅返回 Headers 头部而不读取发送内容实体）。
    """
    if not path.exists() or not path.is_file():
        return json_response(start_response, "404 Not Found", {"ok": False, "error": "file not found"})
        
    size = path.stat().st_size
    # 自动推导 MIME 类型
    content_type = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    
    # 尝试解析 Range 头
    range_info = parse_range(environ.get("HTTP_RANGE", ""), size)
    
    headers = [
        ("Content-Type", content_type),
        ("Accept-Ranges", "bytes"),
    ]
    
    allowed = env("ALLOWED_ORIGIN")
    if allowed:
        headers.append(("Access-Control-Allow-Origin", allowed))
    # 若在开发热重载模式下，强制对文件资源禁用浏览器缓存
    if env("ASR_NO_CACHE") == "1":
        headers.append(("Cache-Control", "no-store"))
        
    # 处理不合法的 Range 边界 (返回 416)
    if range_info == "invalid":
        headers.extend([("Content-Range", f"bytes */{size}"), ("Content-Length", "0")])
        start_response("416 Range Not Satisfiable", headers)
        return [b""]
        
    # 处理 206 Partial Content 分片响应
    if range_info:
        start, end = range_info
        length = end - start + 1
        headers.extend([
            ("Content-Range", f"bytes {start}-{end}/{size}"),
            ("Content-Length", str(length)),
        ])
        start_response("206 Partial Content", headers)
        return [] if environ["REQUEST_METHOD"] == "HEAD" else file_iter(path, start, length)
        
    # 处理 200 OK 完整文件响应
    headers.append(("Content-Length", str(size)))
    start_response("200 OK", headers)
    return [] if environ["REQUEST_METHOD"] == "HEAD" else file_iter(path, 0, size)


def request_base_url(environ) -> str:
    """
    解析获取当前请求的协议与域名基础前缀 URL (例如 `https://example.com`)。
    优先采用全局配置文件 `.env` 中指定的 `PUBLIC_BASE_URL`。
    如果未配置，则从请求头部信息（支持 X-Forwarded 反向代理头部）中进行动态自适应推导。
    """
    configured = env("PUBLIC_BASE_URL")
    if configured:
        return configured.rstrip("/")
    # 获取协议 (如 http 或 https)
    proto = environ.get("HTTP_X_FORWARDED_PROTO") or environ.get("wsgi.url_scheme") or "http"
    # 获取 Host 域名及端口号
    host = environ.get("HTTP_X_FORWARDED_HOST") or environ.get("HTTP_HOST") or f"127.0.0.1:{env('PORT', '8789')}"
    return f"{proto}://{host}".rstrip("/")


def absolute_url(environ, path: str) -> str:
    """
    根据给定的相对路径，拼装并返回一个完整的绝对路径公网可访问 URL 地址。
    """
    return f"{request_base_url(environ)}{path}"
