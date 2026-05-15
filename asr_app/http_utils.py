import json
import mimetypes
from pathlib import Path

from .config import env


def api_error(message: str, status: str = "400 Bad Request", **extra):
    return status, {"ok": False, "error": message, **extra}


def json_response(start_response, status: str, body):
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = [
        ("Content-Type", "application/json; charset=utf-8"),
        ("Content-Length", str(len(data))),
        ("Access-Control-Allow-Origin", env("ALLOWED_ORIGIN", "*")),
        ("Access-Control-Allow-Methods", "GET,POST,OPTIONS"),
        ("Access-Control-Allow-Headers", "content-type"),
    ]
    start_response(status, headers)
    return [data]


def bytes_response(start_response, status: str, body: bytes, content_type: str):
    headers = [
        ("Content-Type", content_type),
        ("Content-Length", str(len(body))),
        ("Access-Control-Allow-Origin", env("ALLOWED_ORIGIN", "*")),
    ]
    start_response(status, headers)
    return [body]


def redirect_response(start_response, location: str):
    start_response("302 Found", [("Location", location), ("Content-Length", "0")])
    return [b""]


def read_json(environ) -> dict:
    length = int(environ.get("CONTENT_LENGTH") or 0)
    raw = environ["wsgi.input"].read(length) if length else b"{}"
    return json.loads(raw.decode("utf-8")) if raw else {}


def file_iter(path: Path, start: int, length: int):
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
    if not header or not header.startswith("bytes="):
        return None
    value = header[6:].split(",", 1)[0].strip()
    if "-" not in value:
        return None
    start_raw, end_raw = value.split("-", 1)
    if start_raw == "":
        suffix = int(end_raw or "0")
        if suffix <= 0:
            return None
        start = max(0, size - suffix)
        end = size - 1
    else:
        start = int(start_raw)
        end = int(end_raw) if end_raw else size - 1
    if start >= size or end < start:
        return "invalid"
    return start, min(end, size - 1)


def file_response(start_response, environ, path: Path, content_type: str | None = None):
    if not path.exists() or not path.is_file():
        return json_response(start_response, "404 Not Found", {"ok": False, "error": "file not found"})
    size = path.stat().st_size
    content_type = content_type or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    range_info = parse_range(environ.get("HTTP_RANGE", ""), size)
    headers = [
        ("Content-Type", content_type),
        ("Accept-Ranges", "bytes"),
        ("Access-Control-Allow-Origin", env("ALLOWED_ORIGIN", "*")),
    ]
    if range_info == "invalid":
        headers.extend([("Content-Range", f"bytes */{size}"), ("Content-Length", "0")])
        start_response("416 Range Not Satisfiable", headers)
        return [b""]
    if range_info:
        start, end = range_info
        length = end - start + 1
        headers.extend([
            ("Content-Range", f"bytes {start}-{end}/{size}"),
            ("Content-Length", str(length)),
        ])
        start_response("206 Partial Content", headers)
        return [] if environ["REQUEST_METHOD"] == "HEAD" else file_iter(path, start, length)
    headers.append(("Content-Length", str(size)))
    start_response("200 OK", headers)
    return [] if environ["REQUEST_METHOD"] == "HEAD" else file_iter(path, 0, size)


def request_base_url(environ) -> str:
    configured = env("PUBLIC_BASE_URL")
    if configured:
        return configured.rstrip("/")
    proto = environ.get("HTTP_X_FORWARDED_PROTO") or environ.get("wsgi.url_scheme") or "http"
    host = environ.get("HTTP_X_FORWARDED_HOST") or environ.get("HTTP_HOST") or f"127.0.0.1:{env('PORT', '8789')}"
    return f"{proto}://{host}".rstrip("/")


def absolute_url(environ, path: str) -> str:
    return f"{request_base_url(environ)}{path}"
