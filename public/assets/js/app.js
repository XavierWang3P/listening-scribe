(function () {
  const TEXT = window.ASR_TEXT || {};
  const audioInput = document.querySelector("#audio");
  const titleInput = document.querySelector("#title");
  const forceInput = document.querySelector("#force");
  const form = document.querySelector("#uploadForm");
  const startButton = document.querySelector("#start");
  const clearButton = document.querySelector("#clear");
  const statusEl = document.querySelector("#status");
  const progressBar = document.querySelector("#progressBar");
  const logEl = document.querySelector("#log");
  const linksEl = document.querySelector("#links");
  const historyList = document.querySelector("#historyList");
  const historyCount = document.querySelector("#historyCount");
  const refreshHistoryButton = document.querySelector("#refreshHistory");

  let progressValue = 0;
  let activeRecordId = "";

  function t(key, values = {}) {
    const template = TEXT[key] || key;
    return template.replace(/\{(\w+)\}/g, (_, name) => (
      Object.prototype.hasOwnProperty.call(values, name) ? String(values[name]) : ""
    ));
  }

  function applyTexts() {
    document.title = t("documentTitle");
    document.querySelectorAll("[data-text]").forEach(node => {
      node.textContent = t(node.dataset.text);
    });
    document.querySelectorAll("[data-placeholder]").forEach(node => {
      node.setAttribute("placeholder", t(node.dataset.placeholder));
    });
    document.querySelectorAll("[data-aria-label]").forEach(node => {
      node.setAttribute("aria-label", t(node.dataset.ariaLabel));
    });
  }

  function apiUrl(path) {
    return path;
  }

  function titleFromFilename(name) {
    return name.replace(/\.[^.]+$/, "");
  }

  function log(message) {
    const time = new Date().toLocaleTimeString();
    logEl.textContent += `[${time}] ${message}\n`;
    logEl.scrollTop = logEl.scrollHeight;
  }

  function setStatus(message, kind = "") {
    const classes = {
      ok: "alert-success",
      bad: "alert-danger",
      warn: "alert-warning"
    };
    statusEl.textContent = message;
    statusEl.className = `alert ${classes[kind] || "alert-secondary"} py-2 mb-3`;
  }

  function setProgress(value) {
    progressValue = Math.max(0, Math.min(100, Math.round(value)));
    progressBar.style.width = `${progressValue}%`;
    progressBar.setAttribute("aria-valuenow", String(progressValue));
  }

  function formatDate(seconds) {
    if (!seconds) return "";
    return new Date(seconds * 1000).toLocaleString();
  }

  async function jsonFetch(url, options = {}) {
    const response = await fetch(url, {
      ...options,
      headers: {
        "content-type": "application/json",
        ...(options.headers || {})
      }
    });
    const data = await response.json();
    if (!response.ok || !data.ok) {
      throw new Error(data.error || `HTTP ${response.status}`);
    }
    return data;
  }

  async function sha256(file) {
    const buffer = await file.arrayBuffer();
    const digest = await crypto.subtle.digest("SHA-256", buffer);
    return Array.from(new Uint8Array(digest))
      .map(byte => byte.toString(16).padStart(2, "0"))
      .join("");
  }

  function uploadToServer(file, hash) {
    return new Promise((resolve, reject) => {
      const params = new URLSearchParams({
        filename: file.name,
        content_type: file.type || "application/octet-stream",
        sha256: hash
      });
      const xhr = new XMLHttpRequest();
      xhr.open("POST", apiUrl(`/api/upload?${params.toString()}`));
      xhr.setRequestHeader("content-type", file.type || "application/octet-stream");
      xhr.upload.onprogress = event => {
        if (event.lengthComputable) {
          setProgress(Math.round((event.loaded / event.total) * 45) + 20);
        }
      };
      xhr.onload = () => {
        let data = {};
        try {
          data = JSON.parse(xhr.responseText || "{}");
        } catch {
          reject(new Error(t("uploadFailed", { status: xhr.status })));
          return;
        }
        if (xhr.status >= 200 && xhr.status < 300 && data.ok) resolve(data);
        else reject(new Error(data.error || t("uploadFailed", { status: xhr.status })));
      };
      xhr.onerror = () => reject(new Error(t("uploadNetworkError")));
      xhr.send(file);
    });
  }

  async function poll(taskId) {
    for (;;) {
      await new Promise(resolve => setTimeout(resolve, 5000));
      const data = await jsonFetch(apiUrl(`/api/status?task_id=${encodeURIComponent(taskId)}`));
      if (data.status === "processing") {
        setProgress(Math.min(95, progressValue + 3));
        log(data.message || t("processingMessage"));
        continue;
      }
      if (data.status === "failed") {
        throw new Error(data.error || t("recognitionFailed"));
      }
      if (data.status === "done") {
        setProgress(100);
        return data.manifest;
      }
    }
  }

  function clearResultLinks() {
    activeRecordId = "";
    linksEl.innerHTML = "";
  }

  function renderLinks(manifest) {
    activeRecordId = manifest.record_id || "";
    linksEl.innerHTML = "";
    const items = [
      [t("linkHtml"), manifest.urls.html, "btn-primary"],
      [t("linkSrt"), manifest.urls.srt, "btn-soft"],
      [t("linkVtt"), manifest.urls.vtt, "btn-soft"],
      [t("linkTxt"), manifest.urls.txt, "btn-soft"],
      [t("linkRaw"), manifest.urls.raw, "btn-soft"],
      [t("linkAudio"), manifest.audio_url, "btn-soft"]
    ];
    for (const [label, url, variant] of items) {
      if (!url) continue;
      const link = document.createElement("a");
      link.className = `btn ${variant}`;
      link.href = apiUrl(url);
      link.target = "_blank";
      link.rel = "noopener";
      link.textContent = label;
      linksEl.append(link);
    }
  }

  function renderHistory(items) {
    historyList.innerHTML = "";
    historyCount.textContent = items.length ? t("historyCount", { count: items.length }) : t("noFiles");
    if (!items.length) {
      const empty = document.createElement("div");
      empty.className = "empty-state";
      empty.textContent = t("historyEmpty");
      historyList.append(empty);
      return;
    }
    for (const item of items) {
      const card = document.createElement("div");
      card.className = "history-card";

      const title = document.createElement("div");
      title.className = "history-title";
      title.textContent = item.title || item.filename || item.record_id;

      const meta = document.createElement("div");
      meta.className = "history-meta";
      const cueText = item.cues ? t("cueCount", { count: item.cues }) : t("cueFallback");
      meta.textContent = `${cueText} · ${formatDate(item.created_at)}`;

      const actions = document.createElement("div");
      actions.className = "d-flex flex-wrap gap-2";

      const openLink = document.createElement("a");
      openLink.className = "btn btn-soft btn-sm";
      openLink.href = apiUrl(item.html_url);
      openLink.target = "_blank";
      openLink.rel = "noopener";
      openLink.textContent = t("openButton");

      const deleteButton = document.createElement("button");
      deleteButton.className = "btn btn-outline-danger btn-sm";
      deleteButton.type = "button";
      deleteButton.textContent = t("deleteButton");
      deleteButton.addEventListener("click", () => deleteHistoryItem(item, deleteButton));

      actions.append(openLink, deleteButton);
      card.append(title, meta, actions);
      historyList.append(card);
    }
  }

  async function loadHistory() {
    historyCount.textContent = t("loading");
    historyList.innerHTML = "";
    const loading = document.createElement("div");
    loading.className = "empty-state";
    loading.textContent = t("loadingEllipsis");
    historyList.append(loading);
    try {
      const data = await jsonFetch(apiUrl("/api/results"));
      renderHistory(data.items || []);
    } catch (error) {
      historyCount.textContent = t("historyLoadFailed");
      historyList.innerHTML = "";
      const empty = document.createElement("div");
      empty.className = "empty-state text-danger";
      empty.textContent = t("historyLoadFailedWithError", { message: error.message });
      historyList.append(empty);
    }
  }

  async function deleteHistoryItem(item, button) {
    const label = item.title || item.filename || item.record_id;
    if (!window.confirm(t("deleteConfirm", { label }))) {
      return;
    }
    button.disabled = true;
    try {
      const data = await jsonFetch(apiUrl("/api/delete"), {
        method: "POST",
        body: JSON.stringify({ record_id: item.record_id })
      });
      log(t("logDeleted", { label }));
      log(t("logDeleteDetail", {
        audio: data.audio_removed ? t("deleteAudioRemoved") : t("deleteNotFound"),
        result: data.result_removed ? t("deleteResultRemoved") : t("deleteNotFound"),
        count: data.hash_indexes_removed
      }));
      if (activeRecordId === item.record_id) {
        clearResultLinks();
        setProgress(0);
        setStatus(t("deletedCurrentStatus"), "warn");
      }
      await loadHistory();
    } catch (error) {
      button.disabled = false;
      setStatus(error.message, "bad");
      log(t("logDeleteFailed", { message: error.message }));
    }
  }

  async function handleSubmit(event) {
    event.preventDefault();
    const file = audioInput.files && audioInput.files[0];
    if (!file) {
      setStatus(t("chooseAudioWarning"), "bad");
      return;
    }

    startButton.disabled = true;
    clearResultLinks();
    setProgress(0);
    setStatus(t("preparingStatus"));

    try {
      log(t("logFile", { name: file.name, size: file.size }));
      const hash = await sha256(file);
      setProgress(15);
      log(t("logHash", { hash }));

      setStatus(t("uploadingStatus"));
      const upload = await uploadToServer(file, hash);
      setProgress(68);
      log(t("logServerSaved", { url: upload.audio_url }));
      if (upload.duplicate) {
        log(t("logDuplicate"));
      }

      if (upload.cached && upload.manifest && !forceInput.checked) {
        log(t("logCacheHit"));
        renderLinks(upload.manifest);
        await loadHistory();
        setStatus(t("doneStatus"), "ok");
        setProgress(100);
        return;
      }
      if (upload.cached && forceInput.checked) {
        log(t("logForce"));
      }

      const submit = await jsonFetch(apiUrl("/api/recognize"), {
        method: "POST",
        body: JSON.stringify({
          filename: file.name,
          title: titleInput.value.trim() || titleFromFilename(file.name),
          record_id: upload.record_id,
          audio_hash: upload.audio_hash,
          force: forceInput.checked
        })
      });

      if (submit.status === "done") {
        log(t("logCacheHit"));
        renderLinks(submit.manifest);
        await loadHistory();
        setStatus(t("doneStatus"), "ok");
        setProgress(100);
        return;
      }

      setStatus(t("recognizingStatus"));
      log(t("logTaskId", { taskId: submit.task_id }));
      const manifest = await poll(submit.task_id);
      renderLinks(manifest);
      await loadHistory();
      setStatus(t("doneStatus"), "ok");
      log(t("logGenerated"));
    } catch (error) {
      setStatus(error.message, "bad");
      log(t("logError", { message: error.message }));
    } finally {
      startButton.disabled = false;
    }
  }

  function bindEvents() {
    audioInput.addEventListener("change", () => {
      const file = audioInput.files && audioInput.files[0];
      if (file) titleInput.value = titleFromFilename(file.name);
    });

    form.addEventListener("submit", handleSubmit);

    clearButton.addEventListener("click", () => {
      logEl.textContent = "";
      clearResultLinks();
      setProgress(0);
      setStatus(t("waitingStatus"));
    });

    refreshHistoryButton.addEventListener("click", loadHistory);
  }

  applyTexts();
  bindEvents();
  loadHistory();
})();
