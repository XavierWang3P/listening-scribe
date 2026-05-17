import json
import uuid
from pathlib import Path
from urllib import request
from urllib.error import HTTPError, URLError

from config import env


VOLC_SUBMIT_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/submit"
VOLC_QUERY_URL = "https://openspeech.bytedance.com/api/v3/auc/bigmodel/query"


def resolve_api_key(api_key: str = "") -> str:
    key = (api_key or "").strip() or env("VOLCENGINE_API_KEY")
    if not key:
        raise RuntimeError("Missing Volcengine API Key: configure VOLCENGINE_API_KEY in .env or enter it on the page.")
    return key


def volc_headers(task_id: str, logid: str = "", sequence: bool = True, api_key: str = "") -> dict:
    headers = {
        "Content-Type": "application/json",
        "X-Api-Resource-Id": env("VOLCENGINE_RESOURCE_ID", "volc.seedasr.auc"),
        "X-Api-Request-Id": task_id,
        "X-Api-Key": resolve_api_key(api_key),
    }
    if sequence:
        headers["X-Api-Sequence"] = "-1"
    if logid:
        headers["X-Tt-Logid"] = logid
    return headers


def post_json(url: str, headers: dict, payload: dict):
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(url, data=data, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", "replace")
            parsed = json.loads(raw) if raw.strip() else {}
            return dict(resp.headers.items()), parsed, raw
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"HTTP {exc.code}: {raw}") from exc
    except URLError as exc:
        raise RuntimeError(f"Network error: {exc}") from exc


def volc_payload(audio_url_for_asr: str) -> dict:
    request_payload = {
        "model_name": "bigmodel",
        "enable_itn": True,
        "enable_punc": True,
        "enable_ddc": False,
        "show_utterances": True,
    }
    model_version = env("VOLCENGINE_MODEL_VERSION", "400")
    if model_version:
        request_payload["model_version"] = model_version
    audio_format = Path(audio_url_for_asr.split("?", 1)[0]).suffix.lower().lstrip(".")
    audio = {"url": audio_url_for_asr}
    if audio_format:
        audio["format"] = "ogg_opus" if audio_format == "opus" else audio_format
    return {"user": {"uid": "server-asr"}, "audio": audio, "request": request_payload}


def volc_submit(audio_url_for_asr: str, api_key: str = ""):
    task_id = str(uuid.uuid4())
    headers, _, _ = post_json(VOLC_SUBMIT_URL, volc_headers(task_id, api_key=api_key), volc_payload(audio_url_for_asr))
    status = headers.get("X-Api-Status-Code", "")
    message = headers.get("X-Api-Message", "")
    logid = headers.get("X-Tt-Logid", "")
    if status != "20000000":
        raise RuntimeError(f"Volcengine submit failed: {status} {message} logid={logid}")
    return task_id, logid


def volc_query(task_id: str, logid: str, api_key: str = ""):
    headers, parsed, raw = post_json(VOLC_QUERY_URL, volc_headers(task_id, logid, sequence=False, api_key=api_key), {})
    status = headers.get("X-Api-Status-Code", "")
    message = headers.get("X-Api-Message", "")
    return status, message, parsed, raw
