# Listening Scribe

> 听力转写助手：将听力录音转换为文本、字幕和可跳转播放页面。

[English](README.en.md) | 中文

Listening Scribe 是一个自托管的听力音频转写工具。用户可以在网页中上传音频，程序会调用火山引擎语音识别接口，生成纯文本、SRT、VTT、原始 JSON，以及一个带音频播放器和字幕跳转功能的 HTML 页面。

它适合处理英语听力材料、课程录音、口语练习音频、试卷听力录音等需要整理成文字和字幕的场景。

## 功能特点

- 网页上传音频，服务端本地保存文件。
- 调用火山引擎 ASR 识别音频内容。
- 自动生成 `.txt`、`.srt`、`.vtt`、`.json` 和可播放的字幕网页。
- 首页使用 Bootstrap 5 构建，支持历史记录、服务商选择、密钥输入、进度状态和服务商接入指引。
- 字幕网页使用自定义 Bootstrap 播放器，支持置顶播放控制、进度拖动、字幕跳转、3 秒快进/后退、播放速度切换和字幕显示开关。
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
Browser -> POST /api/status
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
│   ├── providers.py     # 服务商入口和支持状态
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
- 一个火山引擎语音识别 API Key，可写入 `.env`，也可在私有 Web 界面中输入
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

ALIYUN_ACCESS_KEY_ID=
ALIYUN_ACCESS_KEY_SECRET=
ALIYUN_APP_KEY=
ALIYUN_REGION=cn-shanghai

TENCENT_SECRET_ID=
TENCENT_SECRET_KEY=
TENCENT_REGION=ap-guangzhou

PORT=8789
PUBLIC_BASE_URL=https://asr.example.com
DATA_DIR=data
MAX_UPLOAD_MB=500
ALLOWED_ORIGIN=*
```

关键配置说明：

- `VOLCENGINE_API_KEY`：火山引擎语音识别 API Key。私有部署时可以留空，改由前端输入 Key；公网部署建议写入 `.env`。
- `PUBLIC_BASE_URL`：外网可访问的服务地址，火山引擎需要通过它拉取音频。
- `DATA_DIR`：音频、任务和识别结果的保存目录。
- `MAX_UPLOAD_MB`：允许上传的最大音频体积。
- `ALLOWED_ORIGIN`：接口跨域来源。

首页支持选择服务商、输入密钥，并通过右侧帮助按钮以 Bootstrap toast 展示接入指引。当前识别流程已接入火山引擎；阿里云、腾讯云入口已在界面和接口层预留，但识别适配器尚未实现。若 `.env` 中已配置 `VOLCENGINE_API_KEY`，后端优先使用 `.env`，前端 Key 可以留空。若 `.env` 未配置，则前端输入的 Key 会随识别请求和轮询请求发送给后端。勾选“记住到浏览器 Cookie”后，密钥会保存在当前浏览器 Cookie 中。

## 服务商与模型支持

目前系统已完整接入以下五种 ASR 转写服务，均支持通过后端 `.env` 配置或前端 Web 界面临时输入凭证（Web 端输入具有绝对优先权）：

| 服务商 | 适用产品/模型 | 当前状态 | 凭证类型 | 音频拉取要求 | 字幕网页支持 | 特性说明 |
| --- | --- | --- | --- | --- | --- | --- |
| **火山引擎** | 录音文件识别 | **已接入** | API Key | 需要公网可访问的音频 URL | **支持** (含时间戳) | 通用中英文，识别精度高 |
| **阿里云百炼** | Fun-ASR Paraformer | **已接入** | DashScope API Key | 需要公网可访问的音频 URL | **支持** (含时间戳) | 句级时间戳，性价比极高，多语言支持 |
| **阿里云百炼** | Paraformer-v2 | ****已接入**** | DashScope API Key | 需要公网可访问的音频 URL | **支持** (含时间戳) | 针对普通话深度优化，超低计费，性价比首选 |
| **阿里云百炼** | Qwen3-ASR-Flash | **已接入** | DashScope API Key | 需要公网可访问的音频 URL | 暂无 (返回纯文本) | 通义千问大模型，同步瞬间响应，极强语义纠错能力 |
| **腾讯云** | 录音文件识别 | **已接入** | SecretId / SecretKey | 需要公网可访问的音频 URL | **支持** (含时间戳) | 支持中文普通话及多种方言，双凭证支持 |

服务商入口由 [providers.py](file:///Users/xw/Documents/Codex/2026-05-13/files-mentioned-by-the-user-txt/server_asr/asr_app/providers.py) 统一维护，并动态提供给前端渲染。所有服务商均支持密钥保存到浏览器 Cookie，且均通过了完整的转写测试。

## 本地运行

```bash
python3 app.py
```

开发时可以使用自动重载模式：

```bash
python3 app.py --reload
```

在该模式下，修改 `app.py` 或 `asr_app/*.py` 后服务会自动重启；修改 `public/` 里的 HTML、CSS、JS 后刷新浏览器即可生效，不需要重启 Python 应用。自动重载模式会对静态文件添加 `Cache-Control: no-store`，减少浏览器缓存干扰。

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

## 安全提示

- 不要提交 `.env`，其中包含 API Key。
- 不要把 `data/` 作为公开仓库内容上传，里面可能包含用户音频和识别结果。
- 如果部署到公网，建议通过 Nginx、HTTPS、防火墙和访问控制保护服务。

## License

This project is licensed under the MIT License. See [LICENSE](LICENSE) for details.
