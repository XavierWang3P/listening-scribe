import json
import mimetypes
import re
from urllib import parse

from .config import PUBLIC_DIR, RESULTS_DIR
from .http_utils import api_error, bytes_response, file_response, json_response, read_json, redirect_response
from .service import delete_result, get_provider_config, poll_task, submit_recognition, upload_audio
from .storage import get_audio_meta, get_audio_path, manifest_path, read_json_file, result_dir
from .utils import normalized_path, safe_relative_path


RECORD_RE = r"[0-9]{8}-[0-9]{6}-[a-f0-9]{8}|[a-f0-9]{64}"


def handle_results():
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
    items.sort(key=lambda item: item["created_at"], reverse=True)
    return "200 OK", {"ok": True, "items": items}


def handle_upload(environ, query: dict):
    return "200 OK", upload_audio(environ, query)


def handle_recognize(environ, payload: dict):
    return "200 OK", submit_recognition(environ, payload)


def handle_status(query: dict, payload: dict | None = None):
    payload = payload or {}
    task_id = str(payload.get("task_id") or (query.get("task_id") or [""])[0])
    if not task_id:
        return api_error("task_id is required")
    return poll_task(task_id, payload)


def handle_delete(payload: dict):
    record_id = str(payload.get("record_id") or "")
    if not record_id:
        return api_error("record_id is required")
    return "200 OK", delete_result(record_id)


def serve_audio(start_response, environ, path: str):
    match = re.fullmatch(rf"/media/audio/({RECORD_RE})/(.+)", path)
    if not match:
        return json_response(start_response, "404 Not Found", {"ok": False, "error": "not found"})
    record_id, _ = match.groups()
    meta = get_audio_meta(record_id)
    file_path = get_audio_path(meta)
    return file_response(start_response, environ, file_path, meta.get("content_type") or mimetypes.guess_type(file_path.name)[0])


def serve_result(start_response, environ, path: str):
    match = re.fullmatch(rf"/results/({RECORD_RE})(?:/(.*))?", path)
    if not match:
        return json_response(start_response, "404 Not Found", {"ok": False, "error": "not found"})
    record_id, rel = match.groups()
    manifest = manifest_path(record_id)
    if not rel:
        if manifest.exists():
            html_url = read_json_file(manifest).get("urls", {}).get("html")
            if html_url:
                return redirect_response(start_response, html_url)
        return json_response(start_response, "404 Not Found", {"ok": False, "error": "result not found"})
    rel_path = safe_relative_path(rel)
    file_path = result_dir(record_id) / rel_path
    return file_response(start_response, environ, file_path)


def serve_public_asset(start_response, environ, path: str):
    match = re.fullmatch(r"/assets/(.+)", path)
    if not match:
        return json_response(start_response, "404 Not Found", {"ok": False, "error": "not found"})
    rel_path = safe_relative_path(match.group(1))
    if any(part.startswith(".") for part in rel_path.parts):
        return json_response(start_response, "404 Not Found", {"ok": False, "error": "not found"})
    return file_response(start_response, environ, PUBLIC_DIR / "assets" / rel_path)


def application(environ, start_response):
    method = environ["REQUEST_METHOD"]
    path = normalized_path(environ)
    parsed_query = parse.parse_qs(environ.get("QUERY_STRING", ""))

    if method == "OPTIONS":
        return bytes_response(start_response, "204 No Content", b"", "text/plain")
    try:
        if path == "/" and method == "GET":
            return file_response(start_response, environ, PUBLIC_DIR / "index.html", "text/html; charset=utf-8")
        if path.startswith("/assets/") and method in {"GET", "HEAD"}:
            return serve_public_asset(start_response, environ, path)
        if path == "/healthz" and method == "GET":
            return json_response(start_response, "200 OK", {"ok": True})
        if path == "/api/providers" and method == "GET":
            return json_response(start_response, "200 OK", get_provider_config())
        if path == "/api/upload" and method == "POST":
            status, body = handle_upload(environ, parsed_query)
            return json_response(start_response, status, body)
        if path == "/api/recognize" and method == "POST":
            status, body = handle_recognize(environ, read_json(environ))
            return json_response(start_response, status, body)
        if path == "/api/status" and method == "GET":
            status, body = handle_status(parsed_query)
            return json_response(start_response, status, body)
        if path == "/api/status" and method == "POST":
            status, body = handle_status(parsed_query, read_json(environ))
            return json_response(start_response, status, body)
        if path == "/api/results" and method == "GET":
            status, body = handle_results()
            return json_response(start_response, status, body)
        if path == "/api/delete" and method == "POST":
            status, body = handle_delete(read_json(environ))
            return json_response(start_response, status, body)
        if path.startswith("/media/audio/") and method in {"GET", "HEAD"}:
            return serve_audio(start_response, environ, path)
        if path.startswith("/results/") and method in {"GET", "HEAD"}:
            return serve_result(start_response, environ, path)
        return json_response(start_response, "404 Not Found", {"ok": False, "error": "not found"})
    except Exception as exc:
        return json_response(start_response, "500 Internal Server Error", {"ok": False, "error": str(exc)})
