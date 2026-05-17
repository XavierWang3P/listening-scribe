"""阿里云 Qwen-ASR (千问3-ASR-Flash) 同步识别适配器。

Qwen-ASR 通过 OpenAI 兼容接口实现同步调用，直接返回全文识别结果。
注意：该接口返回纯文本，不包含句级时间戳，因此无法生成字幕。
"""
import json
from urllib import request
from urllib.error import HTTPError, URLError

from config import env

QWEN_ASR_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"
QWEN_ASR_MODEL = "qwen3-asr-flash"


def resolve_api_key(api_key: str = "") -> str:
    key = (api_key or "").strip() or env("DASHSCOPE_API_KEY")
    if not key:
        raise RuntimeError(
            "Missing DashScope API Key: configure DASHSCOPE_API_KEY in .env or enter it on the page."
        )
    return key


def qwen_recognize(audio_url: str, api_key: str = "") -> str:
    """同步调用 Qwen-ASR，返回纯文本识别结果。

    Args:
        audio_url: 公网可访问的音频文件 URL。
        api_key:   可选，若未配置环境变量则从此处读取。

    Returns:
        识别出的纯文本字符串。

    Raises:
        RuntimeError: 鉴权失败或 API 返回错误时抛出。
    """
    key = resolve_api_key(api_key)
    payload = {
        "model": QWEN_ASR_MODEL,
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "input_audio",
                        "input_audio": {"data": audio_url},
                    }
                ],
            }
        ],
        "stream": False,
        "asr_options": {"enable_itn": False},
    }
    headers = {
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
    }
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = request.Request(QWEN_ASR_URL, data=data, headers=headers, method="POST")
    try:
        with request.urlopen(req, timeout=300) as resp:
            raw = resp.read().decode("utf-8", "replace")
            parsed = json.loads(raw) if raw.strip() else {}
    except HTTPError as exc:
        raw = exc.read().decode("utf-8", "replace")
        raise RuntimeError(f"Qwen-ASR HTTP {exc.code}: {raw}") from exc
    except URLError as exc:
        raise RuntimeError(f"Qwen-ASR network error: {exc}") from exc

    # 提取识别文本
    try:
        text = parsed["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError(f"Qwen-ASR unexpected response: {parsed}") from exc
    return str(text or "").strip()
