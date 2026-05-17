"""subtitle_template.py — 字幕 HTML 渲染层。

职责：
  - 读取 templates/result.html / result.css / result.js
  - 将动态数据（title、cues、audio）填充进模板
  - 返回最终 HTML 字符串

本模块只做字符串拼装，不包含任何 ASR 解析逻辑。
"""

from __future__ import annotations

import html as _html
import json
import pathlib
import time

# 模板目录（与本文件同级）
_TMPL_DIR = pathlib.Path(__file__).parent / "templates"

# 模板版本号：只要模板文件内容变化，递增此值即可触发已缓存 HTML 的自动重建。
# 该常量由 service.py 中的 refresh_cached_manifest 机制读取。
TEMPLATE_VERSION = 16


# ── 模板文件加载（启动时读取一次，热重载友好）─────────────────────────────────

def _load_templates() -> tuple[str, str, str]:
    """读取 HTML / CSS / JS 模板文件，返回 (html_tpl, css, js)。"""
    html_tpl = (_TMPL_DIR / "result.html").read_text(encoding="utf-8")
    css      = (_TMPL_DIR / "result.css").read_text(encoding="utf-8")
    js       = (_TMPL_DIR / "result.js").read_text(encoding="utf-8")
    return html_tpl, css, js


# ── Cue HTML 片段生成 ─────────────────────────────────────────────────────────

def _format_clock(seconds: float) -> str:
    total = int(seconds)
    minutes, secs = divmod(total, 60)
    hours, minutes = divmod(minutes, 60)
    return f"{hours}:{minutes:02}:{secs:02}" if hours else f"{minutes}:{secs:02}"


def _build_cue_items(cues: list[dict]) -> str:
    """将 cues 列表渲染为一组 <button> 元素字符串。"""
    if not cues:
        return '<div class="list-group-item empty-state">暂无字幕</div>'
    parts = []
    for i, c in enumerate(cues):
        time_label = _html.escape(_format_clock(c["start"]))
        text       = _html.escape(c["text"])
        parts.append(
            f'<button class="cue list-group-item list-group-item-action d-grid align-items-start" '
            f'type="button" data-index="{i}">'
            f'<span class="cue-time badge fw-semibold">{time_label}</span>'
            f'<span class="cue-text">{text}</span>'
            f'</button>'
        )
    return "\n".join(parts)


# ── 公开渲染函数 ──────────────────────────────────────────────────────────────

def make_result_html(
    title: str,
    cues: list[dict],
    audio_src: str,
    audio_type: str,
) -> str:
    """生成字幕结果 HTML 页面。

    Args:
        title:      页面标题（未转义）。
        cues:       标准化 cue 列表，每项含 start/end/text。
        audio_src:  音频文件 URL（可含查询参数）。
        audio_type: MIME 类型，如 "audio/mpeg"。

    Returns:
        完整 HTML 字符串。
    """
    # 确保 audio URL 带缓存破坏参数
    if "?" not in audio_src:
        audio_src = f"{audio_src}?v={int(time.time())}"

    html_tpl, css, js = _load_templates()

    return html_tpl.format(
        title        = _html.escape(title),
        css          = css,
        js           = js,
        audio_src    = _html.escape(audio_src),
        audio_type   = _html.escape(audio_type),
        cue_count    = len(cues),
        cue_items    = _build_cue_items(cues),
        cue_data_json = json.dumps(cues, ensure_ascii=False),
        audio_src_json = json.dumps(audio_src, ensure_ascii=False),
        year         = time.strftime("%Y"),
    )
