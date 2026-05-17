# Listening Scribe

> A self-hosted listening transcription tool that turns audio recordings into text, subtitles, and a seekable playback page.

English | [中文](README.md)

Listening Scribe is a server-hosted ASR tool for listening materials. Users upload audio through a web interface, the server submits the audio to Volcengine ASR, and the app generates plain text, SRT, VTT, raw JSON, and an HTML page with synchronized subtitle navigation.

It is designed for English listening exercises, class recordings, speaking-practice audio, exam listening tracks, and similar learning materials that need to be converted into readable text and subtitles.

## Features

- Upload audio from a web page and store files locally on the server.
- Submit audio to Volcengine ASR for speech recognition.
- Generate `.txt`, `.srt`, `.vtt`, `.json`, and a playable subtitle HTML page.
- Bootstrap 5 web UI with history, provider selection, credential input, progress status, and provider guide help.
- Custom Bootstrap subtitle player with sticky playback controls, seek bar, cue navigation, 3-second skip controls, playback-speed selection, and transcript visibility toggle.
- SHA256-based duplicate detection to avoid repeated uploads and repeated recognition.
- Optional force-recognition mode to ignore cached results.
- History sidebar for opening and deleting recognized files.
- No COS dependency. Audio and results are served from the same server.
- No third-party Python dependency.

## Flow

```text
Browser -> POST /api/upload -> data/audio/<record_id>/
Browser -> POST /api/recognize
Server  -> computes SHA256 and stores data/hashes/<sha256>.json
Server  -> submits a publicly reachable audio URL to Volcengine
Browser -> POST /api/status
Server  -> writes data/results/<record_id>/
Browser -> opens /results/<record_id>/<title>_字幕跳转.html
```

The generated subtitle page reads audio from `/media/audio/...`, which avoids COS ACL, CORS, signed URL expiration, and Range request issues.

## Project Structure

```text
listening-scribe/
├── app.py               # Server entrypoint
├── Dockerfile           # Docker image definition
├── docker-compose.yml   # Single-container deployment
├── config.example.env   # Environment variable template
├── requirements.txt     # Dependency notes
├── asr_app/
│   ├── config.py        # Environment and runtime paths
│   ├── http_utils.py    # JSON, redirect, and file responses
│   ├── providers.py     # Provider catalog and support status
│   ├── routes.py        # HTTP routing
│   ├── service.py       # Upload, cache, task, and result orchestration
│   ├── storage.py       # Local files, SHA256 index, and metadata
│   ├── subtitles.py     # TXT/SRT/VTT/HTML generation
│   ├── utils.py         # Path and filename helpers
│   └── volcengine.py    # Volcengine submit/query client
├── public/
│   ├── index.html       # Web UI
│   └── assets/
│       ├── css/app.css
│       ├── img/
│       └── js/
└── data/                # Runtime data, auto-created and ignored by Git
```

## Requirements

- Python 3.12 or later
- A Volcengine ASR API key, configured in `.env` or entered in a private web UI
- A public URL or domain that Volcengine can access

This project has no third-party Python dependency in `requirements.txt`.

## Configuration

Copy the example environment file:

```bash
cp config.example.env .env
```

Fill `.env`:

```bash
VOLCENGINE_API_KEY=your_volcengine_api_key
VOLCENGINE_RESOURCE_ID=volc.seedasr.auc
VOLCENGINE_MODEL_VERSION=400

# Aliyun DashScope (Paraformer-v2 / Fun-ASR / Qwen-ASR)
DASHSCOPE_API_KEY=

# Tencent Cloud ASR
TENCENT_SECRET_ID=
TENCENT_SECRET_KEY=
TENCENT_REGION=ap-guangzhou

PORT=8789
PUBLIC_BASE_URL=https://asr.example.com
DATA_DIR=data
MAX_UPLOAD_MB=500
ALLOWED_ORIGIN=*
```

Key settings:

- `VOLCENGINE_API_KEY`: Volcengine ASR API key. Private deployments may leave this empty and enter the key in the web UI; public deployments should keep it in `.env`.
- `PUBLIC_BASE_URL`: Public service URL used by Volcengine to fetch the uploaded audio.
- `DATA_DIR`: Directory for audio, tasks, and generated results.
- `MAX_UPLOAD_MB`: Maximum accepted upload size.
- `ALLOWED_ORIGIN`: Allowed CORS origin.

The home page supports provider selection, credential input, and a Bootstrap toast guide from the help button beside the provider picker. The recognition flow fully supports Volcengine, Tencent Cloud ASR, Aliyun Paraformer, Aliyun Fun-ASR, and Aliyun Qwen-ASR. If the respective backend environment variables are configured in `.env`, the backend uses them first and the frontend key can be left empty. If not configured, the frontend key provided by the user is sent with recognition and polling requests. When "remember credentials" is enabled, credentials are stored securely in the browser cookies.

## Providers and Models

Currently, the system has fully integrated the following five ASR transcription services:

| Provider | Applicable Models/Products | Current Status | Credentials Type | Audio Pull Requirement | Subtitle Page Support | Features |
| --- | --- | --- | --- | --- | --- | --- |
| **Volcengine** | Audio file recognition | **Supported** | API Key | Requires publicly reachable audio URL | **Yes** (with timestamps) | General English/Chinese, highly accurate |
| **Aliyun Bailian** | Fun-ASR Paraformer | **Supported** | DashScope API Key | Requires publicly reachable audio URL | **Yes** (with timestamps) | Sentence-level timestamps, highly cost-effective |
| **Aliyun Bailian** | Paraformer-v2 | **Supported** | DashScope API Key | Requires publicly reachable audio URL | **Yes** (with timestamps) | Optimized for Chinese, low latency and cost |
| **Aliyun Bailian** | Qwen3-ASR-Flash | **Supported** | DashScope API Key | Requires publicly reachable audio URL | No (Plain text only) | Large voice model, synchronous instant response |
| **Tencent Cloud** | Audio file recognition | **Supported** | SecretId / SecretKey | Requires publicly reachable audio URL | **Yes** (with timestamps) | High accuracy for Chinese and dialects |

Provider entries are maintained dynamically in [providers.py](file:///Users/xw/Documents/Codex/2026-05-13/files-mentioned-by-the-user-txt/server_asr/asr_app/providers.py). All five providers support cookie persistence and are fully tested and functional.

## Local Run

```bash
python3 app.py
```

For development, use auto-reload mode:

```bash
python3 app.py --reload
```

In this mode, changes to `app.py` or `asr_app/*.py` automatically restart the server. Changes under `public/` only require a browser refresh. Auto-reload mode also adds `Cache-Control: no-store` to static files to reduce browser-cache confusion.

Open:

```text
http://127.0.0.1:8789/
```

Local upload and playback work immediately. Real recognition requires `PUBLIC_BASE_URL` to point to a public address reachable by Volcengine.

## Docker Deployment

```bash
cp config.example.env .env
docker compose up -d --build
```

The service listens on:

```text
http://127.0.0.1:8789/
```

## Server Deployment

Recommended architecture:

```text
Nginx 80/443 -> http://127.0.0.1:8789 -> Listening Scribe
```

Example Nginx config:

```nginx
server {
    listen 80;
    server_name asr.example.com;

    client_max_body_size 500m;

    location / {
        proxy_pass http://127.0.0.1:8789;
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Forwarded-Host $host;
    }
}
```

Make sure `PUBLIC_BASE_URL` in `.env` matches the public domain.

## Generated Files

After recognition, each record generates:

- `transcript/<title>.txt`
- `subtitles/<title>.srt`
- `subtitles/<title>.vtt`
- `raw/<title>.volcengine.json`
- `<title>_字幕跳转.html`
- `manifest.json`

Runtime data is stored in `data/` by default. The directory is excluded by `.gitignore`.

## API

- `GET /api/providers`
- `POST /api/upload?filename=...&content_type=...&sha256=...`
- `POST /api/recognize`
- `GET /api/status?task_id=...`
- `POST /api/status`
- `GET /api/results`
- `POST /api/delete`
- `GET /media/audio/<record_id>/<filename>`
- `GET /results/<record_id>/`

## Security Notes

- Do not commit `.env`; it contains your API key.
- Do not publish `data/`; it may contain user audio and recognition results.
- For public deployment, protect the service with Nginx, HTTPS, firewall rules, and access control as needed.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
