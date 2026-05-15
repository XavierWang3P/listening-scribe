# Listening Scribe

> A self-hosted listening transcription tool that turns audio recordings into text, subtitles, and a seekable playback page.

English | [中文](README.md)

Listening Scribe is a server-hosted ASR tool for listening materials. Users upload audio through a web interface, the server submits the audio to Volcengine ASR, and the app generates plain text, SRT, VTT, raw JSON, and an HTML page with synchronized subtitle navigation.

It is designed for English listening exercises, class recordings, speaking-practice audio, exam listening tracks, and similar learning materials that need to be converted into readable text and subtitles.

## Features

- Upload audio from a web page and store files locally on the server.
- Submit audio to Volcengine ASR for speech recognition.
- Generate `.txt`, `.srt`, `.vtt`, `.json`, and a playable subtitle HTML page.
- Seekable subtitle page with audio playback, cue navigation, 3-second skip controls, and playback-speed selection.
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
Browser -> GET /api/status?task_id=...
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
- A Volcengine ASR API key
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

PORT=8789
PUBLIC_BASE_URL=https://asr.example.com
DATA_DIR=data
MAX_UPLOAD_MB=500
ALLOWED_ORIGIN=*
```

Key settings:

- `VOLCENGINE_API_KEY`: Volcengine ASR API key.
- `PUBLIC_BASE_URL`: Public service URL used by Volcengine to fetch the uploaded audio.
- `DATA_DIR`: Directory for audio, tasks, and generated results.
- `MAX_UPLOAD_MB`: Maximum accepted upload size.
- `ALLOWED_ORIGIN`: Allowed CORS origin.

## Local Run

```bash
python3 app.py
```

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

## Security Notes

- Do not commit `.env`; it contains your API key.
- Do not publish `data/`; it may contain user audio and recognition results.
- For public deployment, protect the service with Nginx, HTTPS, firewall rules, and access control as needed.

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
