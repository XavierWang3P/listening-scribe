# Listening Scribe

> 听力转写助手：将听力录音转换为文本、字幕和可跳转播放页面。

[English](README.en.md) | 中文

Listening Scribe 是一个自托管的听力音频转写工具。用户可以在网页中上传音频，程序会调用火山引擎语音识别接口，生成纯文本、SRT、VTT、原始 JSON，以及一个带音频播放器和字幕跳转功能的 HTML 页面。

它适合处理英语听力材料、课程录音、口语练习音频、试卷听力录音等需要整理成文字和字幕的场景。

## 功能特点

- 网页上传音频，服务端本地保存文件。
- 调用火山引擎 ASR 识别音频内容。
- 自动生成 `.txt`、`.srt`、`.vtt`、`.json` 和可播放的字幕网页。
- 字幕网页支持音频播放、字幕跳转、3 秒快进/后退、播放速度切换。
- 使用 SHA256 检测重复音频，避免重复上传和重复识别。
- 可选择强制重新识别，忽略已有缓存结果。
- 左侧历史列表可查看、打开和删除已识别文件。
- 不依赖 COS，音频和识别结果都保存在当前服务器。
- 无第三方 Python 依赖，部署简单。

## 工作流程

```text
Browser -> POST /api/upload -> data/audio/<record_id>/
Browser -> POST /api/recognize
Server  -> 计算 SHA256，并保存 data/hashes/<sha256>.json
Server  -> 提交公开可访问的音频 URL 到火山引擎
Browser -> GET /api/status?task_id=...
Server  -> 写入 data/results/<record_id>/
Browser -> 打开 /results/<record_id>/<title>_字幕跳转.html
```

生成的字幕网页会从 `/media/audio/...` 读取音频，因此可以避免 COS 权限、CORS、签名 URL 过期和 Range 请求等问题。

## 项目结构

```text
listening-scribe/
├── app.py               # 服务入口
├── Dockerfile           # Docker 镜像配置
├── docker-compose.yml   # 单容器部署配置
├── config.example.env   # 环境变量示例
├── requirements.txt     # 依赖说明
├── asr_app/
│   ├── config.py        # 环境变量和运行目录
│   ├── http_utils.py    # JSON、重定向和文件响应
│   ├── routes.py        # HTTP 路由
│   ├── service.py       # 上传、缓存、任务和结果编排
│   ├── storage.py       # 本地文件、SHA256 索引和元数据
│   ├── subtitles.py     # TXT/SRT/VTT/HTML 生成
│   ├── utils.py         # 路径和文件名工具
│   └── volcengine.py    # 火山引擎提交和查询客户端
├── public/
│   ├── index.html       # Web 界面
│   └── assets/
│       ├── css/app.css
│       ├── img/
│       └── js/
└── data/                # 运行时数据，自动创建，不提交到 Git
```

## 环境要求

- Python 3.12 或更高版本
- 一个火山引擎语音识别 API Key
- 一个公网可访问的域名或地址

本项目的 `requirements.txt` 中没有第三方 Python 依赖。

## 配置

复制环境变量示例：

```bash
cp config.example.env .env
```

填写 `.env`：

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

关键配置说明：

- `VOLCENGINE_API_KEY`：火山引擎语音识别 API Key。
- `PUBLIC_BASE_URL`：外网可访问的服务地址，火山引擎需要通过它拉取音频。
- `DATA_DIR`：音频、任务和识别结果的保存目录。
- `MAX_UPLOAD_MB`：允许上传的最大音频体积。
- `ALLOWED_ORIGIN`：接口跨域来源。

## 本地运行

```bash
python3 app.py
```

打开：

```text
http://127.0.0.1:8789/
```

本地上传和播放可以直接工作。真实识别需要 `PUBLIC_BASE_URL` 指向火山引擎可以访问的公网地址。

## Docker 部署

```bash
cp config.example.env .env
docker compose up -d --build
```

服务默认监听：

```text
http://127.0.0.1:8789/
```

## 服务器部署建议

推荐架构：

```text
Nginx 80/443 -> http://127.0.0.1:8789 -> Listening Scribe
```

Nginx 示例：

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

请确保 `.env` 中的 `PUBLIC_BASE_URL` 与外部访问域名一致。

## 输出文件

识别完成后，每条记录会生成：

- `transcript/<title>.txt`
- `subtitles/<title>.srt`
- `subtitles/<title>.vtt`
- `raw/<title>.volcengine.json`
- `<title>_字幕跳转.html`
- `manifest.json`

运行时数据默认保存在 `data/`，该目录已被 `.gitignore` 排除。

## 安全提示

- 不要提交 `.env`，其中包含 API Key。
- 不要把 `data/` 作为公开仓库内容上传，里面可能包含用户音频和识别结果。
- 如果部署到公网，建议通过 Nginx、HTTPS、防火墙和访问控制保护服务。

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
