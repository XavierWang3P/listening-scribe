"""腾讯云语音识别录音文件识别适配器。

使用 TC3-HMAC-SHA256 签名（仅依赖 Python 标准库）。
工作流程：
  1. tencent_submit()  → CreateRecTask，返回 task_id
  2. tencent_query()   → DescribeTaskStatus，轮询直到完成

文档：
  - 提交：https://cloud.tencent.com/document/product/1093/37823
  - 查询：https://cloud.tencent.com/document/product/1093/37822
  - 签名：https://cloud.tencent.com/document/api/1093/35640
"""
import datetime
import hashlib
import hmac
import json
import time
from urllib import request
from urllib.error import HTTPError, URLError

from config import env

TENCENT_ASR_HOST = "asr.tencentcloudapi.com"
TENCENT_ASR_URL = f"https://{TENCENT_ASR_HOST}/"
TENCENT_ASR_SERVICE = "asr"
TENCENT_ASR_VERSION = "2019-06-14"
TENCENT_DEFAULT_REGION = "ap-guangzhou"

# DescribeTaskStatus: Status 取值
STATUS_WAITING = 0
STATUS_PROCESSING = 1
STATUS_SUCCESS = 2
STATUS_FAILED = 3


def resolve_credentials(secret_id: str = "", secret_key: str = "") -> tuple[str, str]:
    sid = (secret_id or "").strip() or env("TENCENT_SECRET_ID")
    skey = (secret_key or "").strip() or env("TENCENT_SECRET_KEY")
    if not sid or not skey:
        raise RuntimeError(
            "Missing Tencent SecretId/SecretKey: configure TENCENT_SECRET_ID and TENCENT_SECRET_KEY "
            "in .env or enter them on the page."
        )
    return sid, skey


def resolve_region(region: str = "") -> str:
    return env("TENCENT_REGION") or (region or "").strip() or TENCENT_DEFAULT_REGION


# ── TC3-HMAC-SHA256 签名实现 ──────────────────────────────────────────────────

def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _tc3_headers(secret_id: str, secret_key: str, action: str, region: str, payload: dict) -> dict:
    """构造 TC3-HMAC-SHA256 鉴权头部。"""
    payload_str = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    timestamp = int(time.time())
    date = datetime.datetime.utcfromtimestamp(timestamp).strftime("%Y-%m-%d")

    # Step 1: 规范化请求
    canonical_headers = f"content-type:application/json; charset=utf-8\nhost:{TENCENT_ASR_HOST}\n"
    signed_headers = "content-type;host"
    hashed_payload = hashlib.sha256(payload_str.encode("utf-8")).hexdigest()
    canonical_request = "\n".join([
        "POST",
        "/",
        "",
        canonical_headers,
        signed_headers,
        hashed_payload,
    ])

    # Step 2: 待签字符串
    algorithm = "TC3-HMAC-SHA256"
    credential_scope = f"{date}/{TENCENT_ASR_SERVICE}/tc3_request"
    hashed_cr = hashlib.sha256(canonical_request.encode("utf-8")).hexdigest()
    string_to_sign = "\n".join([algorithm, str(timestamp), credential_scope, hashed_cr])

    # Step 3: 计算签名
    secret_date = _sign(("TC3" + secret_key).encode("utf-8"), date)
    secret_service = _sign(secret_date, TENCENT_ASR_SERVICE)
    secret_signing = _sign(secret_service, "tc3_request")
    signature = hmac.new(secret_signing, string_to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    # Step 4: 鉴权头
    authorization = (
        f"{algorithm} "
        f"Credential={secret_id}/{credential_scope}, "
        f"SignedHeaders={signed_headers}, "
        f"Signature={signature}"
    )

    return {
        "Authorization": authorization,
        "Content-Type": "application/json; charset=utf-8",
        "Host": TENCENT_ASR_HOST,
        "X-TC-Action": action,
        "X-TC-Timestamp": str(timestamp),
        "X-TC-Version": TENCENT_ASR_VERSION,
        "X-TC-Region": region,
    }


def _call(action: str, payload: dict, secret_id: str, secret_key: str, region: str) -> dict:
    """发送一次签名 POST 请求到腾讯云语音识别 ASR，返回解析后的 JSON。"""
    headers = _tc3_headers(secret_id, secret_key, action, region, payload)
    data = json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    req = request.Request(TENCENT_ASR_URL, data=data, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=60) as resp:
            raw = resp.read().decode("utf-8", "replace")
            return json.loads(raw) if raw.strip() else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"Tencent ASR HTTP {exc.code}: {raw}") from exc
    except URLError as exc:
        raise RuntimeError(f"Tencent ASR network error: {exc}") from exc


# ── 业务接口 ──────────────────────────────────────────────────────────────────

def tencent_submit(
    audio_url: str,
    secret_id: str = "",
    secret_key: str = "",
    region: str = "",
    engine_model: str = "16k_zh",
) -> int:
    """提交腾讯云语音识别录音识别任务。

    Returns:
        TaskId（整数）。
    """
    sid, skey = resolve_credentials(secret_id, secret_key)
    rgn = resolve_region(region)
    payload = {
        "EngineModelType": engine_model,
        "ChannelNum": 1,
        "ResTextFormat": 2,   # 含标点的词级详情
        "SourceType": 0,      # 使用音频 URL
        "Url": audio_url,
    }
    resp = _call("CreateRecTask", payload, sid, skey, rgn)
    try:
        task_id = resp["Response"]["Data"]["TaskId"]
    except (KeyError, TypeError) as exc:
        error = resp.get("Response", {}).get("Error", {})
        raise RuntimeError(
            f"Tencent ASR submit failed: {error.get('Code')} {error.get('Message')} | raw={resp}"
        ) from exc
    return int(task_id)


def tencent_query(
    task_id: int,
    secret_id: str = "",
    secret_key: str = "",
    region: str = "",
) -> tuple[str, list | None]:
    """查询腾讯云语音识别录音识别任务状态。

    Returns:
        (status_str, result_detail | None)
        - status_str: "waiting" | "doing" | "success" | "failed"
        - result_detail: 当 status_str == "success" 时返回 ResultDetail 列表
    """
    sid, skey = resolve_credentials(secret_id, secret_key)
    rgn = resolve_region(region)
    resp = _call("DescribeTaskStatus", {"TaskId": int(task_id)}, sid, skey, rgn)
    try:
        data = resp["Response"]["Data"]
    except (KeyError, TypeError) as exc:
        error = resp.get("Response", {}).get("Error", {})
        raise RuntimeError(
            f"Tencent ASR query failed: {error.get('Code')} {error.get('Message')} | raw={resp}"
        ) from exc

    status_int = data.get("Status", -1)
    status_str = data.get("StatusStr", "unknown")
    if status_int == STATUS_SUCCESS:
        return status_str, data.get("ResultDetail") or []
    if status_int == STATUS_FAILED:
        error_msg = data.get("ErrorMsg") or "unknown error"
        raise RuntimeError(f"Tencent ASR task failed: {error_msg}")
    # waiting (0) or doing (1)
    return status_str, None
