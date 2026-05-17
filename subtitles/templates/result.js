// result.js — 字幕网页交互逻辑
// 依赖全局变量（由 Python 模板注入）：
//   window.CUE_DATA   : Array<{start, end, text}>
//   window.AUDIO_SRC  : string

(function () {
  const cues = window.CUE_DATA || [];
  const audioSrc = window.AUDIO_SRC || "";

  const audio = document.querySelector("#audio");
  const audioError = document.querySelector("#audioError");
  const appHeaderEl = document.querySelector(".app-header");
  const playerBarEl = document.querySelector(".player-bar");
  const playToggle = document.querySelector("#playToggle");
  const playIcon = document.querySelector("#playIcon");
  const currentTimeEl = document.querySelector("#currentTime");
  const durationTimeEl = document.querySelector("#durationTime");
  const seek = document.querySelector("#seek");
  const back3 = document.querySelector("#back3");
  const forward3 = document.querySelector("#forward3");
  const rateButtons = Array.from(document.querySelectorAll(".rate-button"));
  const hideText = document.querySelector("#hideText");
  const cueButtons = Array.from(document.querySelectorAll(".cue"));
  let lastActiveIndex = -1;

  /* ── Helpers ── */
  function formatClock(s) {
    if (!Number.isFinite(s) || s < 0) return "0:00";
    const total = Math.floor(s);
    const secs = total % 60;
    const mins = Math.floor(total / 60) % 60;
    const hrs = Math.floor(total / 3600);
    return hrs
      ? `${hrs}:${String(mins).padStart(2, "0")}:${String(secs).padStart(2, "0")}`
      : `${mins}:${String(secs).padStart(2, "0")}`;
  }

  /* ── Scroll padding ── */
  function updateScrollPadding() {
    const hh = appHeaderEl ? appHeaderEl.offsetHeight : 64;
    const ph = playerBarEl ? playerBarEl.offsetHeight : 200;
    document.documentElement.style.setProperty("--app-header-height", hh + "px");
    document.documentElement.style.setProperty("--scroll-padding", (hh + ph + 16) + "px");
  }

  /* ── Playback UI sync ── */
  function syncPlayButton() {
    const playing = !audio.paused && !audio.ended;
    playIcon.textContent = playing ? "Ⅱ" : "▶";
    playToggle.setAttribute("aria-label", playing ? "暂停" : "播放");
    playToggle.setAttribute("aria-pressed", playing ? "true" : "false");
  }

  function syncProgress() {
    const dur = Number.isFinite(audio.duration) ? audio.duration : 0;
    const cur = Math.max(0, Math.min(dur || audio.currentTime || 0, audio.currentTime || 0));
    const ratio = dur ? cur / dur : 0;
    currentTimeEl.textContent = formatClock(cur);
    durationTimeEl.textContent = dur ? formatClock(dur) : "--:--";
    seek.value = String(Math.round(ratio * Number(seek.max)));
    seek.style.setProperty("--seek-progress", `${Math.max(0, Math.min(100, ratio * 100))}%`);
  }

  function seekBy(delta) {
    const dur = Number.isFinite(audio.duration) ? audio.duration : Infinity;
    audio.currentTime = Math.max(0, Math.min(dur, audio.currentTime + delta));
    syncProgress();
  }

  /* ── Active cue highlight ── */
  function updateActiveCue(shouldScroll = true) {
    const cur = audio.currentTime;
    let idx = -1;
    for (let i = 0; i < cues.length; i++) {
      if (cur >= cues[i].start && cur <= cues[i].end) { idx = i; break; }
      if (cues[i].start <= cur) idx = i;
    }
    if (idx === lastActiveIndex) return;
    lastActiveIndex = idx;
    cueButtons.forEach((btn, i) => btn.classList.toggle("active", i === idx));
    if (shouldScroll && idx >= 0) {
      cueButtons[idx].scrollIntoView({ block: "nearest", behavior: "smooth" });
    }
  }

  /* ── Audio error ── */
  function showAudioError() {
    const code = audio.error ? audio.error.code : "?";
    const labels = {
      1: "MEDIA_ERR_ABORTED",
      2: "MEDIA_ERR_NETWORK",
      3: "MEDIA_ERR_DECODE",
      4: "MEDIA_ERR_SRC_NOT_SUPPORTED"
    };
    audioError.classList.remove("d-none");
    audioError.textContent = "";
    audioError.append(`音频加载失败：${labels[code] || code}。`);
    audioError.append(document.createElement("br"));
    const link = document.createElement("a");
    link.href = audioSrc;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = "直接打开音频文件";
    audioError.append(link);
  }

  /* ── Init ── */
  updateScrollPadding();
  syncPlayButton();
  syncProgress();

  /* ── Event listeners ── */
  window.addEventListener("resize", updateScrollPadding);
  audio.addEventListener("loadedmetadata", () => { updateScrollPadding(); syncProgress(); });
  audio.addEventListener("durationchange", syncProgress);
  audio.addEventListener("play", syncPlayButton);
  audio.addEventListener("pause", syncPlayButton);
  audio.addEventListener("ended", syncPlayButton);
  audio.addEventListener("timeupdate", () => { syncProgress(); updateActiveCue(); });
  audio.addEventListener("error", showAudioError);

  playToggle.addEventListener("click", () => {
    if (audio.paused || audio.ended) audio.play().catch(() => {});
    else audio.pause();
  });

  seek.addEventListener("input", () => {
    const dur = Number.isFinite(audio.duration) ? audio.duration : 0;
    if (!dur) return;
    audio.currentTime = dur * (Number(seek.value) / Number(seek.max));
    syncProgress();
    updateActiveCue(false);
  });

  back3.addEventListener("click", () => seekBy(-3));
  forward3.addEventListener("click", () => seekBy(3));

  rateButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      audio.playbackRate = Number(btn.dataset.rate);
      rateButtons.forEach((b) => {
        const active = b === btn;
        b.classList.toggle("active", active);
        b.setAttribute("aria-pressed", active ? "true" : "false");
      });
    });
  });

  hideText.addEventListener("change", () => {
    document.body.classList.toggle("hide-transcript", hideText.checked);
  });

  cueButtons.forEach((btn) => {
    btn.addEventListener("click", () => {
      const cue = cues[Number(btn.dataset.index)];
      if (!cue) return;
      audio.currentTime = cue.start;
      syncProgress();
      audio.play().catch(() => {});
    });
  });
})();
