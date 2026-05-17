# Listening Scribe

> A self-hosted listening audio transcription tool that turns audio recordings into text, subtitles, and an interactive playback page with synchronized subtitle navigation.

English | [中文](README.md)

Listening Scribe is a self-hosted audio transcription tool. Users upload audio through a web UI, the server schedules cloud ASR providers, and automatically generates plain text, SRT, VTT, raw JSON, and a seekable HTML page with integrated audio playback and timestamp navigation.

It is designed for digitizing English listening exercises, class recordings, oral practice tracks, exam listening recordings, and other learning materials.

---

## 🏗️ System Architecture & Design

### 1. Architecture Flowchart

Below is the flowchart representing the core data flow and module interactions:

```mermaid
graph TD
    %% Frontend Layer
    subgraph Frontend [Frontend Web UI]
        UI[index.html / app.js] -->|1. Upload Audio / Trigger ASR| API[HTTP API]
        UI -->|5. Preview Results| SubHTML[Seekable Subtitle Page]
    end

    %% Routing Layer
    subgraph Control [Routing & Orchestration]
        API -->|Route dispatch| Routes[routes.py]
        Routes -->|Business orchestration| Service[service.py]
    end

    %% Providers Layer
    subgraph Adapters [ASR Cloud Service Adapters]
        Service -->|Dynamic call| Providers[providers.py]
        Service -->|Volcengine ASR| Volc[volcengine.py]
        Service -->|Tencent Cloud ASR| Tencent[tencent_asr.py]
        Service -->|Aliyun Paraformer| AliFun[aliyun_fun.py]
        Service -->|Aliyun Qwen Voice LLM| AliQwen[aliyun_qwen.py]
    end

    %% Storage & Output Layer
    subgraph Storage [Data Persistence & Compilation]
        Service -->|Read/Write Data| StorageMgr[storage.py]
        StorageMgr -->|Physical file IO| Disk[(data/ directory)]
        Service -->|Compile SRT/VTT/TXT| Subtitles[subtitles.py]
        Service -->|Assemble HTML Template| SubTmpl[subtitle_template.py]
        SubTmpl -->|Read template assets| TmplSrc[(templates/ result.html/css/js)]
    end

    classDef highlight fill:#e1f5fe,stroke:#0288d1,stroke-width:2px;
    class UI,SubHTML,Service,Disk highlight;
```

### 2. Core Modules Architecture

The codebase is built on a modular structure with clear separation of concerns:

| Module/File | Responsibility | Technical Details |
| --- | --- | --- |
| [`app.py`](file:///Users/xw/Documents/Codex/2026-05-13/files-mentioned-by-the-user-txt/server_asr/app.py) | Entrypoint | Based on Python's built-in `http.server`. Supports static assets routing, API dispatch, and a development `--reload` mode. |
| [`asr_app/config.py`](file:///Users/xw/Documents/Codex/2026-05-13/files-mentioned-by-the-user-txt/server_asr/asr_app/config.py) | Configuration | Loads the `.env` configuration file, initializes the `data/` data directories, and provides clean environment utilities. |
| [`asr_app/routes.py`](file:///Users/xw/Documents/Codex/2026-05-13/files-mentioned-by-the-user-txt/server_asr/asr_app/routes.py) | Router | Parses HTTP request headers, paths, and query arguments, forwarding calls to `service.py` with robust CORS handling. |
| [`asr_app/http_utils.py`](file:///Users/xw/Documents/Codex/2026-05-13/files-mentioned-by-the-user-txt/server_asr/asr_app/http_utils.py) | HTTP Utilities | Encapsulates standardized JSON responses, redirection schemes, Range requests (for audio dragging), and audio stream piping. |
| [`asr_app/storage.py`](file:///Users/xw/Documents/Codex/2026-05-13/files-mentioned-by-the-user-txt/server_asr/asr_app/storage.py) | Storage Management | Manages `manifest.json` indexing and computes SHA256 hashes to map uploaded audio files, preventing duplicate charging. |
| [`asr_app/service.py`](file:///Users/xw/Documents/Codex/2026-05-13/files-mentioned-by-the-user-txt/server_asr/asr_app/service.py) | Business Logic | Orchestrates the entire transcription lifecycle: Upload ➔ Hash Deduplication ➔ Task Submission ➔ Polling/Sync ➔ Compilation ➔ Deletion. |
| [`asr_app/providers.py`](file:///Users/xw/Documents/Codex/2026-05-13/files-mentioned-by-the-user-txt/server_asr/asr_app/providers.py) | Providers metadata | Declares the properties, guidelines, credential requirements, and support status of the five integrated ASR services. |
| [`asr_app/volcengine.py`](file:///Users/xw/Documents/Codex/2026-05-13/files-mentioned-by-the-user-txt/server_asr/asr_app/volcengine.py) | Volcengine Client | Implements the submit-and-poll lifecycle for Volcengine ASR. |
| [`asr_app/tencent_asr.py`](file:///Users/xw/Documents/Codex/2026-05-13/files-mentioned-by-the-user-txt/server_asr/asr_app/tencent_asr.py) | Tencent Client | Built with native Tencent Cloud API 3.0 signing mechanisms (`CreateRecTask` / `DescribeTaskStatus`), eliminating SDK overhead. |
| [`asr_app/aliyun_fun.py`](file:///Users/xw/Documents/Codex/2026-05-13/files-mentioned-by-the-user-txt/server_asr/asr_app/aliyun_fun.py) | Aliyun Paraformer Client | Integrates DashScope REST API for Paraformer-v2 and Fun-ASR models with multilingual sentence-level timestamp extraction. |
| [`asr_app/aliyun_qwen.py`](file:///Users/xw/Documents/Codex/2026-05-13/files-mentioned-by-the-user-txt/server_asr/asr_app/aliyun_qwen.py) | Aliyun Qwen Client | Integrates Aliyun's Qwen3-ASR-Flash voice LLM. Returns synchronous text transcripts without polling (no timestamps). |
| [`asr_app/subtitles.py`](file:///Users/xw/Documents/Codex/2026-05-13/files-mentioned-by-the-user-txt/server_asr/asr_app/subtitles.py) | Subtitle Generation | Parses the standardized cues and compiles them into `.txt`, `.srt`, `.vtt`, and raw `.json` formatted files. |
| [`asr_app/subtitle_template.py`](file:///Users/xw/Documents/Codex/2026-05-13/files-mentioned-by-the-user-txt/server_asr/asr_app/subtitle_template.py) | Page Compilation | Hydrates static template pages with dynamic parameters, utilizing `TEMPLATE_VERSION` caching to manage immediate cache invalidation. |
| [`asr_app/templates/`](file:///Users/xw/Documents/Codex/2026-05-13/files-mentioned-by-the-user-txt/server_asr/asr_app/templates) | Player Templates | Frontend templates (HTML/CSS/JS) featuring custom control panels, precise seek mechanisms, and high-contrast synchronizations. |

---

## 🌟 Key Features

1. Multiple ASR Providers: Supports Volcengine ASR, Tencent Cloud ASR, Aliyun Paraformer-v2, Fun-ASR, and Qwen-ASR.
2. Single-Page UI: Bootstrap 5 web UI with history management, provider selection, real-time logging, and credential cookie settings.
3. Dual Credential Mode:
   * Supports server-side `.env` configuration to keep credentials completely hidden from clients.
   * Supports frontend temporary inputs (with "Remember credentials" options). Frontend inputs carry absolute priority, avoiding env-key overrides.
4. SHA256-Based Deduplication: Computes audio file hashes to check against existing manifests, yielding instant cache hits, zero repeated uploads, and zero repeated cloud costs.
5. No Cloud Object Storage (COS) Dependency: Audio and transcription files are fully hosted on the local server, preventing CORS limits, expired links, and Range requests dragging issues.
6. No Third-Party Python Dependencies: Built entirely on native Python standard libraries.

---

## 🛠️ Installation & Getting Started

### 1. Requirements for Publicly Reachable URL

Because cloud ASR engines (Volcengine, Aliyun, Tencent Cloud) pull audio files asynchronously, their servers must be able to fetch the audio file from your server over the internet.

Therefore, the app requires a publicly reachable URL:
* Cloud Server (VPS) Deployment: If deploying on a public VPS, simply set your domain or public IP.
* Local Machine / LAN Deployment: If running locally (e.g. localhost / 127.0.0.1), you must use an intranet penetration / tunneling tool (e.g. frp, ngrok, cloudflare tunnel) to expose the local port (default 8789) to the internet. Otherwise, cloud platforms will fail to fetch the audio, resulting in failed transcription tasks.

### 2. Configure Environment

```bash
cp config.example.env .env
```

Edit your `.env` to configure your keys and the public base URL:

```env
# Volcengine (Seed-ASR)
VOLCENGINE_API_KEY=your_volcengine_api_key
VOLCENGINE_RESOURCE_ID=volc.seedasr.auc
VOLCENGINE_MODEL_VERSION=400

# Aliyun DashScope (DashScope API Key)
DASHSCOPE_API_KEY=your_dashscope_api_key

# Tencent Cloud ASR
TENCENT_SECRET_ID=your_tencent_secret_id
TENCENT_SECRET_KEY=your_tencent_secret_key
TENCENT_REGION=ap-guangzhou

# Server Configurations
PORT=8789
PUBLIC_BASE_URL=https://your-public-domain-or-tunnel.com  # Must be reachable by cloud providers
DATA_DIR=data
MAX_UPLOAD_MB=500
ALLOWED_ORIGIN=*
```

### 3. Run the App

#### Method A: Physical Host
Requires Python 3.12 or newer. No pip installations required.

```bash
# Production Run
python3 app.py

# Development Mode (hot reload enabled, static assets browser caching disabled)
python3 app.py --reload
```

#### Method B: Docker Deployment
Run using our lightweight Alpine-Python Docker Compose stack:

```bash
docker compose up -d --build
```

---

## ⚙️ Nginx Reverse Proxy Recommendation

We recommend hosting your deployment behind Nginx with SSL enabled:

```nginx
server {
    listen 80;
    listen 443 ssl http2;
    server_name your-public-domain-or-tunnel.com;

    ssl_certificate /path/to/fullchain.pem;
    ssl_certificate_key /path/to/privkey.pem;
    
    client_max_body_size 500m;

    location / {
        proxy_pass http://127.0.0.1:8789;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # Disable buffering to ensure real-time upload progress and streaming logs
        proxy_buffering off;
    }
}
```

---

## 💾 Outputs Structure

Upon successful transcription, files are arranged in the `data/results/<record_id>/` directory:

```text
├── <filename>                    # Original audio file
├── transcript/
│   └── <filename>.txt            # Plain text transcript
├── subtitles/
│   ├── <filename>.srt            # SRT subtitle file
│   └── <filename>.vtt            # WebVTT subtitle file
├── raw/
│   └── <filename>.<provider>.json # Full raw ASR JSON response
├── <filename>_字幕跳转.html        # Interactive HTML page with synchronized navigation
└── manifest.json                 # Transcript record metadata index
```

---

## 🔒 Security Practices

1. Credential Protection: Never commit your `.env` containing live secrets to a public Git repository.
2. Access Control: For deployments open to the public web, configure Basic Auth in Nginx or firewall limits to prevent unauthorized resource utilization.
3. Data Safety: The local `data/` runtime directories are ignored in `.gitignore`, keeping your uploaded audio assets fully secured.

---

## 📄 License

This project is licensed under the [MIT License](LICENSE).
