from config import env


PROVIDERS = {
    "volcengine": {
        "label": "火山引擎 录音文件识别-标准版",
        "product": "录音文件识别",
        "doc_url": "https://www.volcengine.com/docs/6561/80820?lang=zh",
        "supported": True,
        "status_label": "已接入",
        "auth_type": "API Key",
        "credential_fields": ["api_key"],
        "env_keys": ["VOLCENGINE_API_KEY", "VOLCENGINE_RESOURCE_ID", "VOLCENGINE_MODEL_VERSION"],
        "audio_source": "公网可访问的音频 URL",
        "api_flow": ["submit", "query"],
        "has_timestamps": True,
        "guide": [
            "在火山引擎控制台开通录音文件识别，并准备 API Key。",
            "推荐在服务器 .env 中填写 VOLCENGINE_API_KEY；私有部署也可以在网页中临时填写。",
            "PUBLIC_BASE_URL 必须是火山引擎可以访问的公网地址，本工具会把本地音频发布为 /media/audio/... URL。",
        ],
    },
    "aliyun_qwen": {
        "label": "阿里云 Qwen-ASR",
        "product": "千问3-ASR-Flash",
        "doc_url": "https://help.aliyun.com/zh/model-studio/qwen-asr-api-reference",
        "supported": True,
        "status_label": "已接入（仅文本）",
        "auth_type": "API Key (DashScope)",
        "credential_fields": ["api_key"],
        "env_keys": ["DASHSCOPE_API_KEY"],
        "audio_source": "公网可访问的音频 URL",
        "api_flow": ["同步调用"],
        "has_timestamps": False,
        "guide": [
            "在阿里云百炼控制台获取 DashScope API Key（DASHSCOPE_API_KEY）。",
            "Qwen-ASR 为同步接口，无需轮询，通常秒级返回。",
            "注意：Qwen-ASR 返回纯文本，不含时间戳，因此不支持字幕跳转页面，仅生成 .txt 文本文件。",
        ],
    },
    "aliyun_fun": {
        "label": "阿里云 Fun-ASR",
        "product": "Paraformer 录音文件识别",
        "doc_url": "https://help.aliyun.com/zh/model-studio/fun-asr-recorded-speech-recognition-restful-api",
        "supported": True,
        "status_label": "已接入",
        "auth_type": "API Key (DashScope)",
        "credential_fields": ["api_key"],
        "env_keys": ["DASHSCOPE_API_KEY"],
        "audio_source": "公网可访问的音频 URL",
        "api_flow": ["submit", "query"],
        "has_timestamps": True,
        "guide": [
            "在阿里云百炼控制台获取 DashScope API Key（DASHSCOPE_API_KEY）。",
            "Fun-ASR 支持中文、英文及多种语言，返回句级时间戳，可生成字幕跳转页面。",
            "PUBLIC_BASE_URL 必须是阿里云可以访问的公网地址，本工具会把本地音频发布为 /media/audio/... URL。",
        ],
    },
    "aliyun_paraformer": {
        "label": "阿里云 Paraformer",
        "product": "Paraformer-v2 录音文件识别",
        "doc_url": "https://help.aliyun.com/zh/model-studio/recording-file-recognition",
        "supported": True,
        "status_label": "已接入",
        "auth_type": "API Key (DashScope)",
        "credential_fields": ["api_key"],
        "env_keys": ["DASHSCOPE_API_KEY"],
        "audio_source": "公网可访问的音频 URL",
        "api_flow": ["submit", "query"],
        "has_timestamps": True,
        "guide": [
            "在阿里云百炼控制台获取 DashScope API Key（DASHSCOPE_API_KEY）。",
            "Paraformer-v2 支持中文普通话、粤语、英语、日语、韩语等多语言，返回句级时间戳，可生成字幕跳转页面。",
            "Paraformer 价格比 Fun-ASR 低（0.00008 元/秒 vs 0.00022 元/秒），适合普通话为主的场景。",
            "PUBLIC_BASE_URL 必须是阿里云可以访问的公网地址。",
        ],

    },
    "tencent": {
        "label": "腾讯云语音识别",
        "product": "录音文件识别",
        "doc_url": "https://cloud.tencent.com/document/product/1093/37823",
        "supported": True,
        "status_label": "已接入",
        "auth_type": "SecretId / SecretKey",
        "credential_fields": ["secret_id", "secret_key"],
        "env_keys": ["TENCENT_SECRET_ID", "TENCENT_SECRET_KEY", "TENCENT_REGION"],
        "audio_source": "公网可访问的音频 URL",
        "api_flow": ["CreateRecTask", "DescribeTaskStatus"],
        "has_timestamps": True,
        "guide": [
            "在腾讯云语音识别 CAM 控制台获取 SecretId 和 SecretKey，并开通语音识别服务。",
            "默认使用 16k_zh 引擎（中文普通话），返回句级时间戳，可生成字幕跳转页面。",
            "PUBLIC_BASE_URL 必须是腾讯云语音识别可以访问的公网地址，本工具会把本地音频发布为 /media/audio/... URL。",
        ],
    },
}


SERVER_CONFIG_KEYS = {
    "volcengine": ["VOLCENGINE_API_KEY"],
    "aliyun_qwen": ["DASHSCOPE_API_KEY"],
    "aliyun_fun": ["DASHSCOPE_API_KEY"],
    "aliyun_paraformer": ["DASHSCOPE_API_KEY"],
    "tencent": ["TENCENT_SECRET_ID", "TENCENT_SECRET_KEY"],
}


def normalize_provider(value: str) -> str:
    provider = (value or "volcengine").strip().lower()
    if provider not in PROVIDERS:
        raise RuntimeError(f"unsupported ASR provider: {provider}")
    return provider


def provider_catalog() -> dict:
    providers = []
    for provider_id, meta in PROVIDERS.items():
        providers.append({
            "id": provider_id,
            "label": meta["label"],
            "product": meta["product"],
            "doc_url": meta["doc_url"],
            "supported": meta["supported"],
            "status_label": meta["status_label"],
            "auth_type": meta["auth_type"],
            "credential_fields": meta["credential_fields"],
            "env_keys": meta["env_keys"],
            "audio_source": meta["audio_source"],
            "api_flow": meta["api_flow"],
            "has_timestamps": meta.get("has_timestamps", True),
            "guide": meta["guide"],
            "server_configured": all(env(key) for key in SERVER_CONFIG_KEYS[provider_id]),
        })
    return {"ok": True, "default_provider": "volcengine", "providers": providers}


def ensure_provider_supported(provider: str):
    provider = normalize_provider(provider)
    if not PROVIDERS[provider]["supported"]:
        raise RuntimeError(f"{PROVIDERS[provider]['label']}入口已预留，识别逻辑尚未接入。")
    return provider
