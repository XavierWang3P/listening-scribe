import html
import json
import time


TEMPLATE_VERSION = 2


def extract_cues(volc_json: dict) -> list[dict]:
    results = volc_json.get("result", volc_json)
    items = [results] if isinstance(results, dict) else [x for x in results if isinstance(x, dict)] if isinstance(results, list) else []
    cues = []
    for item in items:
        for utterance in item.get("utterances") or item.get("utterance") or []:
            if not isinstance(utterance, dict):
                continue
            text = str(utterance.get("text") or "").strip()
            start = utterance.get("start_time")
            end = utterance.get("end_time")
            if text and start is not None and end is not None:
                cues.append({"start": int(start) / 1000, "end": int(end) / 1000, "text": text})
    cues.sort(key=lambda x: (x["start"], x["end"]))
    return cues


def format_srt(seconds: float) -> str:
    milliseconds = int(round(seconds * 1000))
    hours, remainder = divmod(milliseconds, 3_600_000)
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


def make_txt(cues: list[dict]) -> str:
    return "\n".join(f"[{format_clock(c['start'])}-{format_clock(c['end'])}] {c['text']}" for c in cues) + "\n"


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


def make_result_html(title: str, cues: list[dict], audio_src: str, audio_type: str) -> str:
    safe_title = html.escape(title)
    if "?" not in audio_src:
        audio_src = f"{audio_src}?v={int(time.time())}"
    cue_buttons = "\n".join(
        f'<button class="cue" type="button" data-index="{i}"><span>{html.escape(format_clock(c["start"]))}</span><b>{html.escape(c["text"])}</b></button>'
        for i, c in enumerate(cues)
    )
    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <link rel="icon" href="data:,">
  <title>{safe_title}</title>
  <style>
    body {{ margin: 0; font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #f6f7fb; color: #202532; }}
    header {{ position: sticky; top: 0; background: #fff; border-bottom: 1px solid #d9dee8; padding: 16px 22px 12px; }}
    h1 {{ margin: 0 0 12px; font-size: 20px; line-height: 1.3; letter-spacing: 0; }}
    audio {{ width: 100%; }}
    .controls {{ display: flex; flex-wrap: wrap; align-items: center; gap: 8px; margin-top: 10px; }}
    .controls button, .controls select, .toggle-text {{ min-height: 34px; border: 1px solid #cbd5e1; border-radius: 6px; background: #fff; color: #202532; font: inherit; }}
    .controls button {{ padding: 0 12px; cursor: pointer; }}
    .controls button:hover {{ border-color: #2563eb; color: #2563eb; }}
    .controls select {{ padding: 0 8px; }}
    .control-label {{ color: #667085; font-size: 14px; }}
    .toggle-text {{ display: inline-flex; align-items: center; gap: 6px; padding: 0 10px; cursor: pointer; }}
    .audio-error {{ display: none; margin: 10px 0 0; color: #b42318; font-size: 14px; line-height: 1.5; overflow-wrap: anywhere; }}
    main {{ max-width: 1080px; margin: 0 auto; padding: 18px 22px 34px; }}
    .cue {{ display: grid; grid-template-columns: 86px 1fr; gap: 12px; width: 100%; padding: 10px 12px; margin: 0 0 6px; border: 1px solid transparent; border-radius: 6px; background: #fff; text-align: left; cursor: pointer; line-height: 1.45; }}
    .cue span {{ color: #2563eb; font-variant-numeric: tabular-nums; }}
    .cue b {{ font-weight: 400; overflow-wrap: anywhere; }}
    .cue:hover {{ border-color: #2563eb; background: #e8f0ff; }}
    .cue.active {{ border-color: #d6b656; background: #fff5cc; }}
    .hide-transcript .cue {{ grid-template-columns: 86px; }}
    .hide-transcript .cue b {{ display: none; }}
  </style>
</head>
<body>
  <header>
    <h1>{safe_title}</h1>
    <audio id="audio" controls preload="metadata">
      <source src="{html.escape(audio_src)}" type="{html.escape(audio_type)}">
    </audio>
    <div class="controls">
      <button id="back3" type="button" title="后退 3 秒">-3s</button>
      <button id="forward3" type="button" title="前进 3 秒">+3s</button>
      <span class="control-label">倍速</span>
      <select id="rate" aria-label="倍速">
        <option value="0.75">0.75x</option>
        <option value="1" selected>1x</option>
        <option value="1.25">1.25x</option>
        <option value="1.5">1.5x</option>
        <option value="2">2x</option>
      </select>
      <label class="toggle-text"><input id="hideText" type="checkbox">隐藏转译文本</label>
    </div>
    <p id="audioError" class="audio-error"></p>
  </header>
  <main>{cue_buttons}</main>
  <script>
    const cues = {json.dumps(cues, ensure_ascii=False)};
    const audio = document.querySelector("#audio");
    const audioError = document.querySelector("#audioError");
    const audioSrc = {json.dumps(audio_src, ensure_ascii=False)};
    const back3 = document.querySelector("#back3");
    const forward3 = document.querySelector("#forward3");
    const rate = document.querySelector("#rate");
    const hideText = document.querySelector("#hideText");
    const buttons = Array.from(document.querySelectorAll(".cue"));
    function seekBy(delta) {{
      const duration = Number.isFinite(audio.duration) ? audio.duration : Number.POSITIVE_INFINITY;
      audio.currentTime = Math.max(0, Math.min(duration, audio.currentTime + delta));
    }}
    back3.addEventListener("click", () => seekBy(-3));
    forward3.addEventListener("click", () => seekBy(3));
    rate.addEventListener("change", () => {{
      audio.playbackRate = Number(rate.value);
    }});
    hideText.addEventListener("change", () => {{
      document.body.classList.toggle("hide-transcript", hideText.checked);
    }});
    audio.addEventListener("error", () => {{
      const code = audio.error ? audio.error.code : "unknown";
      const labels = {{
        1: "MEDIA_ERR_ABORTED",
        2: "MEDIA_ERR_NETWORK",
        3: "MEDIA_ERR_DECODE",
        4: "MEDIA_ERR_SRC_NOT_SUPPORTED"
      }};
      audioError.style.display = "block";
      audioError.innerHTML = `音频加载失败：${{labels[code] || code}}。<br><a href="${{audioSrc}}" target="_blank" rel="noopener">直接打开音频文件</a><br>${{audioSrc}}`;
    }});
    buttons.forEach((button) => {{
      button.addEventListener("click", () => {{
        const cue = cues[Number(button.dataset.index)];
        audio.currentTime = cue.start;
        audio.play().catch(() => {{}});
      }});
    }});
    audio.addEventListener("timeupdate", () => {{
      const current = audio.currentTime;
      let activeIndex = -1;
      for (let i = 0; i < cues.length; i += 1) {{
        if (current >= cues[i].start && current <= cues[i].end) {{ activeIndex = i; break; }}
        if (cues[i].start <= current) activeIndex = i;
      }}
      buttons.forEach((button, index) => button.classList.toggle("active", index === activeIndex));
      if (activeIndex >= 0) buttons[activeIndex].scrollIntoView({{ block: "nearest", behavior: "smooth" }});
    }});
  </script>
</body>
</html>
"""
