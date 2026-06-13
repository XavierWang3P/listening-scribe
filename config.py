import os
from pathlib import Path

# ── 项目路径配置 ────────────────────────────────────────────────────────────
# ROOT: 项目根目录绝对路径
ROOT = Path(__file__).resolve().parent
# PUBLIC_DIR: 静态资源前端目录 (存放主页 index.html, JS/CSS 资源等)
PUBLIC_DIR = ROOT / "public"


# ── 载入 .env 环境变量配置文件 ────────────────────────────────────────────────
def load_env_file(path: Path):
    """
    手动解析并加载环境配置文件 (通常为 .env)。
    仅将文件中定义的、且当前系统环境变量中尚不存在的变量注入到 os.environ 中。
    """
    if not path.exists():
        return
    for raw_line in path.read_text("utf-8").splitlines():
        line = raw_line.strip()
        # 排除空行、注释行 (# 开头) 或不含等号的行
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        # 去除值两端可能存在的引号
        value = value.strip().strip('"').strip("'")
        # 写入环境变量缓存，确保优先级不覆盖系统已定义的环境变量
        if key and key not in os.environ:
            os.environ[key] = value


# 启动时优先加载根目录下的 .env 配置文件
load_env_file(ROOT / ".env")


# ── 环境变量快捷获取工具函数 ──────────────────────────────────────────────────
def env(name: str, default: str = "") -> str:
    """获取指定名称的环境变量值，自动去除首尾空白字符，若不存在则返回默认值。"""
    return os.environ.get(name, default).strip()


def required_env(name: str) -> str:
    """获取必须配置的环境变量，若不存在或为空，则抛出 RuntimeError 异常。"""
    value = env(name)
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


# ── 运行数据目录配置与初始化 ──────────────────────────────────────────────────
def data_dir() -> Path:
    """
    确定数据存放的主目录 DATA_DIR：
    1. 优先读取环境变量 DATA_DIR，若未配置则默认为根目录下的 "data" 文件夹。
    2. 支持绝对路径与用户目录缩写 (~)。如果是相对路径，则解析为相对于项目根目录的绝对路径。
    """
    configured = Path(env("DATA_DIR", "data")).expanduser()
    return configured if configured.is_absolute() else ROOT / configured


# 定义各个运行时子目录
DATA_DIR = data_dir()                         # 数据根目录
AUDIO_DIR = DATA_DIR / "audio"                # 音频文件物理存放目录
RESULTS_DIR = DATA_DIR / "results"            # 识别结果物理存放目录 (存放 txt, srt, html 等)
TASKS_DIR = DATA_DIR / "tasks"                # 异步转写任务状态 JSON 缓存目录
TMP_DIR = DATA_DIR / "tmp"                    # 文件上传的临时分块/未决目录
HASH_DIR = DATA_DIR / "hashes"                # SHA256 音频哈希去重索引目录
ADMIN_TOKEN = env("ADMIN_TOKEN")              # 服务访问密钥管理凭证 (若留空则不开启访问校验)


def ensure_dirs():
    """初始化并确保上述所有的运行时必要目录均已在物理磁盘上创建。"""
    for directory in (AUDIO_DIR, RESULTS_DIR, TASKS_DIR, TMP_DIR, HASH_DIR):
        directory.mkdir(parents=True, exist_ok=True)


# 执行运行时目录初始化
ensure_dirs()


import logging
import sys

# ── 日志系统初始化 ────────────────────────────────────────────────────────────
def setup_logging():
    """
    配置全局日志系统：
    1. 日志级别获取优先级：启动命令行参数 `--log-level=LEVEL` 或 `--log LEVEL` > 环境变量 `LOG_LEVEL` > 默认值 `INFO`。
    2. 支持标准的 DEBUG, INFO, WARNING, ERROR 等等级。
    3. 格式化日志输出，包含时间戳、日志等级、模块名及日志内容。
    """
    log_level_str = "INFO"
    # 检查环境变量配置
    if "LOG_LEVEL" in os.environ:
        log_level_str = os.environ["LOG_LEVEL"].upper()

    # 检查命令行启动参数
    for i, arg in enumerate(sys.argv):
        if arg.startswith("--log-level="):
            log_level_str = arg.split("=", 1)[1].upper()
        elif arg in ("--log-level", "--log"):
            if i + 1 < len(sys.argv):
                log_level_str = sys.argv[i + 1].upper()

    level = getattr(logging, log_level_str, logging.INFO)
    
    # 强制覆盖初始化 root logger，确保自定义格式生效
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
        force=True
    )

# 自动运行日志配置
setup_logging()
