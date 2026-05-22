(function () {
  const TEXT = window.ASR_TEXT || {};
  const audioInput = document.querySelector("#audio");
  const titleInput = document.querySelector("#title");
  const forceInput = document.querySelector("#force");
  const providerSelect = document.querySelector("#provider");
  const providerDropdownButton = document.querySelector("#providerDropdownButton");
  const providerDropdownMenu = document.querySelector("#providerDropdownMenu");
  const credentialKeyInput = document.querySelector("#credentialKey");
  const credentialSecretInput = document.querySelector("#credentialSecret");
  const adminTokenInput = document.querySelector("#adminToken");
  const credentialKeyLabel = document.querySelector("#credentialKeyLabel");
  const credentialSecretLabel = document.querySelector("#credentialSecretLabel");
  const credentialHint = document.querySelector("#credentialHint");
  const rememberCredentialsInput = document.querySelector("#rememberCredentials");
  const credentialSecretRows = document.querySelectorAll(".provider-secret-row");
  const providerGuideTitle = document.querySelector("#providerGuideTitle");
  const providerGuideMeta = document.querySelector("#providerGuideMeta");
  const providerGuideLink = document.querySelector("#providerGuideLink");
  const providerGuideList = document.querySelector("#providerGuideList");
  const liveToastButton = document.querySelector("#liveToastBtn");
  const providerGuideToast = document.querySelector("#providerGuideToast");
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
  const startSpinner = document.querySelector("#startSpinner");

  let progressValue = 0;
  let activeRecordId = "";
  let logHistory = [];
  let providerConfig = {
    default_provider: "volcengine",
    providers: [
      {
        id: "volcengine",
        label: "火山引擎 录音文件识别-标准版",
        product: "录音文件识别",
        doc_url: "https://www.volcengine.com/docs/6561/80820?lang=zh",
        supported: true,
        status_label: "已接入",
        auth_type: "API Key",
        server_configured: false,
        credential_fields: ["api_key"],
        env_keys: ["VOLCENGINE_API_KEY", "VOLCENGINE_RESOURCE_ID", "VOLCENGINE_MODEL_VERSION"],
        audio_source: "公网可访问的音频 URL",
        api_flow: ["submit", "query"],
        guide: []
      },
      {
        id: "aliyun",
        label: "阿里云",
        product: "录音文件识别",
        doc_url: "https://help.aliyun.com/zh/isi/developer-reference/api-reference-2",
        supported: false,
        status_label: "待接入",
        auth_type: "AccessKey",
        server_configured: false,
        credential_fields: ["access_key_id", "access_key_secret"],
        env_keys: ["ALIYUN_ACCESS_KEY_ID", "ALIYUN_ACCESS_KEY_SECRET", "ALIYUN_APP_KEY", "ALIYUN_REGION"],
        audio_source: "HTTP 可访问的音频文件 URL",
        api_flow: ["submit", "query"],
        guide: []
      },
      {
        id: "tencent",
        label: "腾讯云语音识别",
        product: "录音文件识别",
        doc_url: "https://cloud.tencent.com/document/product/647/131299",
        supported: false,
        status_label: "待接入",
        auth_type: "SecretId / SecretKey",
        server_configured: false,
        credential_fields: ["secret_id", "secret_key"],
        env_keys: ["TENCENT_SECRET_ID", "TENCENT_SECRET_KEY", "TENCENT_REGION"],
        audio_source: "URL 或本地文件数据",
        api_flow: ["CreateRecTask", "DescribeTaskStatus"],
        guide: []
      }
    ]
  };

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

  function providerMeta(providerId = providerSelect.value) {
    return providerConfig.providers.find(item => item.id === providerId) || providerConfig.providers[0];
  }

  function providerLabel(providerId = providerSelect.value) {
    const meta = providerMeta(providerId);
    // 静态文本映射（原有三个），其余直接用服务端返回的 label
    const textKey = {
      volcengine: "providerVolcengine",
      aliyun: "providerAliyun",
      tencent: "providerTencent"
    }[meta.id];
    return textKey ? t(textKey) : (meta.label || meta.id);
  }

  function cookieName(providerId, field) {
    return `asr_${providerId}_${field}`;
  }

  function setCookie(name, value, maxAgeDays = 180) {
    localStorage.setItem(name, value);
  }

  function getCookie(name) {
    return localStorage.getItem(name) || "";
  }

  function deleteCookie(name) {
    localStorage.removeItem(name);
  }

  function readCookie(name) {
    return getCookie(name);
  }

  function credentialShape(providerId = providerSelect.value) {
    if (providerId === "aliyun") {
      return {
        keyField: "access_key_id",
        keyLabel: t("credentialAccessKeyIdLabel"),
        keyPlaceholder: t("credentialAccessKeyIdPlaceholder"),
        secretField: "access_key_secret",
        secretLabel: t("credentialAccessKeySecretLabel"),
        secretPlaceholder: t("credentialAccessKeySecretPlaceholder")
      };
    }
    if (providerId === "tencent") {
      return {
        keyField: "secret_id",
        keyLabel: t("credentialSecretIdLabel"),
        keyPlaceholder: t("credentialSecretIdPlaceholder"),
        secretField: "secret_key",
        secretLabel: t("credentialSecretKeyLabel"),
        secretPlaceholder: t("credentialSecretKeyPlaceholder")
      };
    }
    return {
      keyField: "api_key",
      keyLabel: t("credentialApiKeyLabel"),
      keyPlaceholder: t("credentialApiKeyPlaceholder"),
      secretField: "",
      secretLabel: "",
      secretPlaceholder: ""
    };
  }

  function collectCredentials() {
    const providerId = providerSelect.value;
    const shape = credentialShape(providerId);
    const credentials = {};
    credentials[shape.keyField] = credentialKeyInput.value.trim();
    if (shape.secretField) {
      credentials[shape.secretField] = credentialSecretInput.value.trim();
    }
    return credentials;
  }

  function loadCredentialsFromCookies(providerId = providerSelect.value) {
    const shape = credentialShape(providerId);
    credentialKeyInput.value = readCookie(cookieName(providerId, shape.keyField));
    credentialSecretInput.value = shape.secretField ? readCookie(cookieName(providerId, shape.secretField)) : "";
    rememberCredentialsInput.checked = readCookie(cookieName(providerId, "remember")) === "1";
    adminTokenInput.value = readCookie("asr_admin_token");
  }

  function persistCredentials(providerId = providerSelect.value) {
    const shape = credentialShape(providerId);
    if (rememberCredentialsInput.checked) {
      setCookie(cookieName(providerId, shape.keyField), credentialKeyInput.value.trim());
      if (shape.secretField) {
        setCookie(cookieName(providerId, shape.secretField), credentialSecretInput.value.trim());
      }
      setCookie("asr_admin_token", adminTokenInput.value.trim());
      setCookie(cookieName(providerId, "remember"), "1");
      log(t("logCredentialSaved"));
      return;
    }
    deleteCookie(cookieName(providerId, shape.keyField));
    if (shape.secretField) {
      deleteCookie(cookieName(providerId, shape.secretField));
    }
    deleteCookie("asr_admin_token");
    deleteCookie(cookieName(providerId, "remember"));
    log(t("logCredentialCleared"));
  }

  function renderProviderOptions() {
    providerSelect.innerHTML = "";
    providerDropdownMenu.innerHTML = "";
    for (const provider of providerConfig.providers) {
      const option = document.createElement("option");
      option.value = provider.id;
      option.textContent = providerLabel(provider.id);
      providerSelect.append(option);

      const item = document.createElement("li");
      const button = document.createElement("button");
      button.className = "dropdown-item provider-dropdown-item";
      button.type = "button";
      button.dataset.providerId = provider.id;
      button.textContent = providerLabel(provider.id);
      button.addEventListener("click", () => {
        setProvider(provider.id, true);
      });
      item.append(button);
      providerDropdownMenu.append(item);
    }
    providerSelect.value = readCookie("asr_provider") || providerConfig.default_provider || "volcengine";
    if (!providerConfig.providers.some(provider => provider.id === providerSelect.value)) {
      providerSelect.value = providerConfig.default_provider || "volcengine";
    }
    syncProviderDropdown();
  }

  function syncProviderDropdown() {
    const selectedProvider = providerSelect.value;
    providerDropdownButton.textContent = providerLabel(selectedProvider);
    providerDropdownMenu.querySelectorAll(".provider-dropdown-item").forEach(button => {
      const isSelected = button.dataset.providerId === selectedProvider;
      button.classList.toggle("active", isSelected);
      button.setAttribute("aria-current", isSelected ? "true" : "false");
    });
  }

  function setProvider(providerId, loadSaved = true) {
    providerSelect.value = providerId;
    setCookie("asr_provider", providerId);
    syncProviderDropdown();
    updateCredentialFields(loadSaved);
  }

  function updateCredentialFields(loadSaved = false) {
    const providerId = providerSelect.value;
    const meta = providerMeta(providerId);
    const shape = credentialShape(providerId);
    renderProviderGuide(meta);
    credentialKeyLabel.textContent = shape.keyLabel;
    credentialKeyInput.placeholder = shape.keyPlaceholder;
    credentialSecretLabel.textContent = shape.secretLabel;
    credentialSecretInput.placeholder = shape.secretPlaceholder;
    credentialSecretRows.forEach(row => row.classList.toggle("is-hidden", !shape.secretField));
    if (loadSaved) {
      loadCredentialsFromCookies(providerId);
    }
    if (!meta.supported) {
      credentialHint.textContent = t("providerUnsupported", { provider: providerLabel(providerId) });
      credentialHint.classList.add("text-danger");
      return;
    }
    credentialHint.classList.remove("text-danger");
    credentialHint.textContent = meta.server_configured ? t("providerConfigured") : t("providerNeedsFrontendKey");
  }

  function renderProviderGuide(meta) {
    providerGuideTitle.textContent = t("providerGuideTitle", {
      provider: providerLabel(meta.id),
      product: meta.product || ""
    });
    providerGuideMeta.textContent = t("providerGuideMeta", {
      status: meta.status_label || (meta.supported ? "已接入" : "待接入"),
      auth: meta.auth_type || "",
      audio: meta.audio_source || ""
    });
    providerGuideLink.href = meta.doc_url || "#";
    providerGuideLink.textContent = t("providerDocButton");
    providerGuideLink.classList.toggle("disabled", !meta.doc_url);
    providerGuideList.innerHTML = "";

    const items = [
      t("providerApiFlow", { flow: (meta.api_flow || []).join(" -> ") }),
      t("providerEnvKeys", { keys: (meta.env_keys || []).join(", ") }),
      ...(meta.guide || [])
    ].filter(Boolean);

    for (const item of items) {
      const li = document.createElement("li");
      li.textContent = item;
      providerGuideList.append(li);
    }
  }

  function showProviderGuideToast() {
    renderProviderGuide(providerMeta());
    if (window.bootstrap && providerGuideToast) {
      window.bootstrap.Toast.getOrCreateInstance(providerGuideToast, { autohide: false }).show();
    }
  }

  async function loadProviderConfig() {
    try {
      const data = await jsonFetch(apiUrl("/api/providers"));
      providerConfig = data;
    } catch (error) {
      log(t("providerLoadFailed"));
    }
    renderProviderOptions();
    updateCredentialFields(true);
  }

  function apiUrl(path) {
    return path;
  }

  function titleFromFilename(name) {
    return name.replace(/\.[^.]+$/, "");
  }

  function log(message) {
    const time = new Date().toLocaleTimeString();
    const entry = `[${time}] ${message}`;
    logHistory.push(entry);
    logEl.textContent = logHistory.join("\n");
    logEl.scrollTop = logEl.scrollHeight;
  }

  function getFullLog() {
    return logHistory.join("\n");
  }

  function setStatus(message, kind = "") {
    statusEl.textContent = message;
    statusEl.className = "status-display" + (kind === "ok" ? " status-ok" : kind === "bad" ? " status-bad" : "");
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
    const token = adminTokenInput.value.trim();
    const headers = {
      "content-type": "application/json",
      ...(options.headers || {})
    };
    if (token) {
      headers["Authorization"] = `Bearer ${token}`;
    }
    const response = await fetch(url, {
      ...options,
      headers
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
      const token = adminTokenInput.value.trim();
      if (token) {
        xhr.setRequestHeader("Authorization", `Bearer ${token}`);
      }
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
      const data = await jsonFetch(apiUrl("/api/status"), {
        method: "POST",
        body: JSON.stringify({
          task_id: taskId,
          provider: providerSelect.value,
          credentials: collectCredentials()
        })
      });
      if (data.status === "processing") {
        setProgress(Math.min(95, progressValue + 3));
        log(data.message || t("processingMessage", { provider: providerLabel() }));
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
      title.className = "history-title d-flex align-items-start gap-2";
      const icon = document.createElement("span");
      icon.innerHTML = `<svg width="18" height="18" fill="currentColor" viewBox="0 0 16 16" style="margin-top:0.15rem;color:var(--asr-accent);"><path d="M14 4.5V14a2 2 0 0 1-2 2H4a2 2 0 0 1-2-2V2a2 2 0 0 1 2-2h5.5zm-3 0A1.5 1.5 0 0 1 9.5 3V1H4a1 1 0 0 0-1 1v12a1 1 0 0 0 1 1h8a1 1 0 0 0 1-1V4.5z"/></svg>`;
      const titleText = document.createElement("span");
      titleText.className = "text-break";
      titleText.textContent = item.title || item.filename || item.record_id;
      title.append(icon, titleText);

      const meta = document.createElement("div");
      meta.className = "history-meta";
      const cueText = item.cues ? t("cueCount", { count: item.cues }) : t("cueFallback");
      meta.textContent = `${cueText} · ${formatDate(item.created_at)}`;

      const actions = document.createElement("div");
      actions.className = "d-flex flex-wrap gap-2";

      const openLink = document.createElement("a");
      openLink.className = "btn btn-primary btn-sm";
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
    const selectedProvider = providerSelect.value;
    const selectedMeta = providerMeta(selectedProvider);
    if (!selectedMeta.supported) {
      setStatus(t("providerUnsupported", { provider: providerLabel(selectedProvider) }), "bad");
      return;
    }
    // 检查：所有 Provider 若未服务端配置，则必须在前端填写主 Key
    const needsKey = !selectedMeta.server_configured && selectedMeta.credential_fields.length > 0;
    if (needsKey && !credentialKeyInput.value.trim()) {
      setStatus(t("chooseProviderKeyWarning"), "bad");
      return;
    }

    startButton.disabled = true;
    if (startSpinner) startSpinner.classList.remove("d-none");
    clearResultLinks();
    setProgress(0);
    setStatus(t("preparingStatus"));

    try {
      setCookie("asr_provider", selectedProvider);
      persistCredentials(selectedProvider);
      log(t("logProvider", { provider: providerLabel(selectedProvider) }));
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
          provider: selectedProvider,
          credentials: collectCredentials(),
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

      setStatus(t("recognizingStatus", { provider: providerLabel(selectedProvider) }));
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
      if (startSpinner) startSpinner.classList.add("d-none");
    }
  }

  function bindEvents() {
    form.addEventListener("submit", handleSubmit);

    const dropzone = document.getElementById("dropzone");
    const dropzoneText = document.getElementById("dropzoneText");

    dropzone.addEventListener("click", () => audioInput.click());

    dropzone.addEventListener("dragover", (e) => {
      e.preventDefault();
      dropzone.style.backgroundColor = "var(--primary-100)";
      dropzone.style.borderColor = "var(--asr-accent) !important";
    });

    dropzone.addEventListener("dragleave", () => {
      dropzone.style.backgroundColor = "";
      dropzone.style.borderColor = "var(--asr-accent-soft) !important";
    });

    dropzone.addEventListener("drop", (e) => {
      e.preventDefault();
      dropzone.style.backgroundColor = "";
      dropzone.style.borderColor = "var(--asr-accent-soft) !important";
      if (e.dataTransfer.files && e.dataTransfer.files.length > 0) {
        audioInput.files = e.dataTransfer.files;
        audioInput.dispatchEvent(new Event('change'));
      }
    });

    audioInput.addEventListener("change", () => {
      const file = audioInput.files && audioInput.files[0];
      if (file) {
        titleInput.value = titleFromFilename(file.name);
        dropzoneText.textContent = `已选择: ${file.name}`;
        dropzoneText.classList.add("text-success");
      } else {
        dropzoneText.textContent = "点击上传音频文件 或 拖拽到此处";
        dropzoneText.classList.remove("text-success");
      }
    });

    providerSelect.addEventListener("change", () => {
      setProvider(providerSelect.value, true);
    });

    clearButton.addEventListener("click", () => {
      logHistory = [];
      logEl.textContent = "";
      clearResultLinks();
      setProgress(0);
      setStatus(t("waitingStatus"));
    });

    refreshHistoryButton.addEventListener("click", loadHistory);
    liveToastButton.addEventListener("click", showProviderGuideToast);

    document.querySelectorAll(".toggle-password").forEach(btn => {
      btn.addEventListener("click", () => {
        const targetId = btn.dataset.target;
        const input = document.getElementById(targetId);
        if (input.type === "password") {
          input.type = "text";
          btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" class="bi bi-eye-slash" viewBox="0 0 16 16"><path d="M13.359 11.238C15.06 9.72 16 8 16 8s-3-5.5-8-5.5a7.028 7.028 0 0 0-2.79.588l.77.771A5.944 5.944 0 0 1 8 3.5c2.12 0 3.879 1.168 5.168 2.457A13.134 13.134 0 0 1 14.828 8c-.058.087-.122.183-.195.288-.335.48-.83 1.12-1.465 1.755-.165.165-.337.328-.517.486l.708.709z"/><path d="M11.297 9.176a3.5 3.5 0 0 0-4.474-4.474l.823.823a2.5 2.5 0 0 1 2.829 2.829l.822.822zm-2.943 1.299.822.822a3.5 3.5 0 0 1-4.474-4.474l.823.823a2.5 2.5 0 0 0 2.829 2.829z"/><path d="M3.35 5.47c-.18.16-.353.322-.518.487A13.134 13.134 0 0 0 1.172 8l.195.288c.335.48.83 1.12 1.465 1.755C4.121 11.332 5.881 12.5 8 12.5c.716 0 1.39-.133 2.02-.36l.77.772A7.029 7.029 0 0 1 8 13.5C3 13.5 0 8 0 8s.939-1.721 2.641-3.238l.708.709zm10.296 8.884-12-12 .708-.708 12 12-.708.708z"/></svg>`;
        } else {
          input.type = "password";
          btn.innerHTML = `<svg xmlns="http://www.w3.org/2000/svg" width="18" height="18" fill="currentColor" class="bi bi-eye" viewBox="0 0 16 16"><path d="M16 8s-3-5.5-8-5.5S0 8 0 8s3 5.5 8 5.5S16 8 16 8zM1.173 8a13.133 13.133 0 0 1 1.66-2.043C4.12 4.668 5.88 3.5 8 3.5c2.12 0 3.879 1.168 5.168 2.457A13.133 13.133 0 0 1 14.828 8c-.058.087-.122.183-.195.288-.335.48-.83 1.12-1.465 1.755C11.879 11.332 10.119 12.5 8 12.5c-2.12 0-3.879-1.168-5.168-2.457A13.134 13.134 0 0 1 1.172 8z"/><path d="M8 5.5a2.5 2.5 0 1 0 0 5 2.5 2.5 0 0 0 0-5zM4.5 8a3.5 3.5 0 1 1 7 0 3.5 3.5 0 0 1-7 0z"/></svg>`;
        }
      });
    });
  }

  applyTexts();
  renderProviderOptions();
  updateCredentialFields(true);
  bindEvents();
  loadProviderConfig();
  loadHistory();
})();
