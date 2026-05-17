"""subtitles.py — 字幕提取与格式转换（纯逻辑层）。

职责：
  - 从各 ASR 服务返回的 JSON 中提取标准化 cue 列表
  - 将 cue 列表序列化为 SRT / VTT / TXT 格式
  - 将 cue 列表渲染为字幕 HTML 页面（委托给 subtitle_template）

不包含任何 HTML/CSS/JS 字符串。
"""

# HTML 渲染委托给独立模块
from .subtitle_template import TEMPLATE_VERSION, make_result_html  # noqa: F401


# ── Cue 提取器 ────────────────────────────────────────────────────────────────

def extract_cues(volc_json: dict) -> list[dict]:
    """从火山引擎 ASR 结果中提取标准化 cue 列表。"""
    results = volc_json.get("result", volc_json)
    items = (
        [results] if isinstance(results, dict)
        else [x for x in results if isinstance(x, dict)] if isinstance(results, list)
        else []
    )
    cues = []
    for item in items:
        for utterance in item.get("utterances") or item.get("utterance") or []:
            if not isinstance(utterance, dict):
                continue
            text  = str(utterance.get("text") or "").strip()
            start = utterance.get("start_time")
            end   = utterance.get("end_time")
            if text and start is not None and end is not None:
                cues.append({"start": int(start) / 1000, "end": int(end) / 1000, "text": text})
    cues.sort(key=lambda x: (x["start"], x["end"]))
    return cues


def extract_cues_funasr(sentences: list) -> list[dict]:
    """从 Fun-ASR / Paraformer 的 sentences 列表中提取标准化 cue 列表。

    时间戳字段：begin_time / end_time，单位毫秒。
    """
    cues = []
    for sentence in sentences or []:
        if not isinstance(sentence, dict):
            continue
        text  = str(sentence.get("text") or "").strip()
        begin = sentence.get("begin_time")
        end   = sentence.get("end_time")
        if text and begin is not None and end is not None:
            cues.append({"start": int(begin) / 1000, "end": int(end) / 1000, "text": text})
    cues.sort(key=lambda x: (x["start"], x["end"]))
    return cues


def extract_cues_tencent(result_detail: list) -> list[dict]:
    """从腾讯云 DescribeTaskStatus ResultDetail 中提取标准化 cue 列表。

    字段：FinalSentence / StartMs / EndMs。
    """
    cues = []
    for item in result_detail or []:
        if not isinstance(item, dict):
            continue
        text     = str(item.get("FinalSentence") or "").strip()
        start_ms = item.get("StartMs")
        end_ms   = item.get("EndMs")
        if text and start_ms is not None and end_ms is not None:
            cues.append({"start": int(start_ms) / 1000, "end": int(end_ms) / 1000, "text": text})
    cues.sort(key=lambda x: (x["start"], x["end"]))
    return cues


# ── 时间格式化工具 ────────────────────────────────────────────────────────────

def format_srt(seconds: float) -> str:
    ms = int(round(seconds * 1000))
    hours, remainder = divmod(ms, 3_600_000)
    minutes, remainder = divmod(remainder, 60_000)
    secs, millis = divmod(remainder, 1000)
    return f"{hours:02}:{minutes:02}:{secs:02},{millis:03}"


def format_vtt(seconds: float) -> str:
    return format_srt(seconds).replace(",", ".")


def format_clock(seconds: float) -> str:
    total = int(seconds)
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02}:{secs:02}" if hours else f"{minutes}:{secs:02}"


# ── 字幕文件生成 ──────────────────────────────────────────────────────────────

def make_txt(cues: list[dict]) -> str:
    return "\n".join(
        f"[{format_clock(c['start'])}-{format_clock(c['end'])}] {c['text']}"
        for c in cues
    ) + "\n"


def make_srt(cues: list[dict]) -> str:
    return "\n".join(
        f"{i}\n{format_srt(c['start'])} --> {format_srt(c['end'])}\n{c['text']}\n"
        for i, c in enumerate(cues, 1)
    )


def make_vtt(cues: list[dict]) -> str:
    return "WEBVTT\n\n" + "\n".join(
        f"{format_vtt(c['start'])} --> {format_vtt(c['end'])}\n{c['text']}\n"
        for c in cues
    )
