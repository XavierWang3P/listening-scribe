"""阿里云 Fun-ASR (Paraformer) 异步录音文件识别适配器。

工作流程：
  1. fun_submit()  → 提交任务，返回 task_id
  2. fun_query()   → 轮询状态，任务完成后下载 transcription_url 并解析

Fun-ASR 返回句级时间戳（begin_time / end_time，单位 ms），可直接生成字幕。
"""
import json
from urllib import request
from urllib.error import HTTPError, URLError

from config import env

FUNASR_SUBMIT_URL = "https://dashscope.aliyuncs.com/api/v1/services/audio/asr/transcription"
FUNASR_QUERY_URL_TPL = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"

# 支持的模型（都走同一套 API）
FUNASR_MODEL_FUNASR = "fun-asr"
FUNASR_MODEL_PARAFORMER = "paraformer-v2"

# task_status 取值
STATUS_PENDING = "PENDING"
STATUS_RUNNING = "RUNNING"
STATUS_SUCCEEDED = "SUCCEEDED"
STATUS_FAILED = "FAILED"


def resolve_api_key(api_key: str = "") -> str:
    key = (api_key or "").strip() or env("DASHSCOPE_API_KEY")
    if not key:
        raise RuntimeError(
            "Missing DashScope API Key: configure DASHSCOPE_API_KEY in .env or enter it on the page."
        )
    return key


def _http_post(url: str, headers: dict, payload: dict | None = None) -> dict:
    """发送 POST 请求并返回解析后的 JSON。"""
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8") if payload else b""
    req = request.Request(url, data=data, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw.strip() else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"Fun-ASR HTTP {exc.code}: {raw}") from exc
    except URLError as exc:
        raise RuntimeError(f"Fun-ASR network error: {exc}") from exc


def _http_get(url: str, headers: dict) -> dict:
    """发送 GET 请求并返回解析后的 JSON。"""
    req = request.Request(url, headers=headers, method="GET")
    try:
        with request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw.strip() else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"Fun-ASR HTTP {exc.code}: {raw}") from exc
    except URLError as exc:
        raise RuntimeError(f"Fun-ASR network error: {exc}") from exc


def fun_submit(audio_url: str, api_key: str = "", model: str = FUNASR_MODEL_FUNASR) -> str:
    """提交 Fun-ASR / Paraformer 识别任务。

    Args:
        audio_url: 公网可访问的音频文件 URL。
        api_key:   可选，优先使用环境变量 DASHSCOPE_API_KEY。
        model:     模型名称，默认 fun-asr；传入 paraformer-v2 则调用 Paraformer。

    Returns:
        DashScope 任务 ID（task_id）。
    """
    key = resolve_api_key(api_key)
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "X-DashScope-Async": "enable",
    }
    payload = {
        "model": model,
        "input": {"file_urls": [audio_url]},
        "parameters": {"channel_id": [0]},
    }
    resp = _http_post(FUNASR_SUBMIT_URL, headers, payload)
    try:
        task_id = resp["output"]["task_id"]
    except (KeyError, TypeError) as exc:
        raise RuntimeError(f"Fun-ASR submit unexpected response: {resp}") from exc
    return str(task_id)


def fun_query(task_id: str, api_key: str = "") -> tuple[str, list | None]:
    """查询 Fun-ASR 任务状态。

    Returns:
        (status, result_json | None)
        - status: "PENDING" | "RUNNING" | "SUCCEEDED" | "FAILED"
        - result_json: 当 status == "SUCCEEDED" 时返回 transcription_url 的内容
    """
    key = resolve_api_key(api_key)
    headers = {"Authorization": f"Bearer {key}"}
    url = FUNASR_QUERY_URL_TPL.format(task_id=task_id)
    # Fun-ASR 查询接口使用 GET
    resp = _http_get(url, headers)
    output = resp.get("output") or resp
    status = str(output.get("task_status") or "").upper()

    if status != STATUS_SUCCEEDED:
        return status, None

    # 下载每个子任务的识别结果
    results = output.get("results") or []
    all_sentences = []
    for sub in results:
        if str(sub.get("subtask_status") or "").upper() != STATUS_SUCCEEDED:
            continue
        transcription_url = sub.get("transcription_url", "")
        if not transcription_url:
            continue
        try:
            transcript_json = _fetch_json(transcription_url)
            for transcript in transcript_json.get("transcripts") or []:
                all_sentences.extend(transcript.get("sentences") or [])
        except Exception:
            # 单个子任务失败不影响整体
            pass

    return status, all_sentences


def _fetch_json(url: str) -> dict:
    """从 URL 下载并解析 JSON 内容。"""
    req = request.Request(url, method="GET")
    try:
        with request.urlopen(req, timeout=120) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw.strip() else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"Fun-ASR result download HTTP {exc.code}: {raw}") from exc
    except URLError as exc:
        raise RuntimeError(f"Fun-ASR result download network error: {exc}") from exc
