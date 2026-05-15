import os
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_DIR = ROOT / "public"


def load_env_file(path: Path):
    if not path.exists():
        return
    for raw_line in path.read_text("utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


load_env_file(ROOT / ".env")


def env(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def required_env(name: str) -> str:
    value = env(name)
    if not value:
        raise RuntimeError(f"Missing environment variable: {name}")
    return value


def data_dir() -> Path:
    configured = Path(env("DATA_DIR", "data")).expanduser()
    return configured if configured.is_absolute() else ROOT / configured


DATA_DIR = data_dir()
AUDIO_DIR = DATA_DIR / "audio"
RESULTS_DIR = DATA_DIR / "results"
TASKS_DIR = DATA_DIR / "tasks"
TMP_DIR = DATA_DIR / "tmp"
HASH_DIR = DATA_DIR / "hashes"


def ensure_dirs():
    for directory in (AUDIO_DIR, RESULTS_DIR, TASKS_DIR, TMP_DIR, HASH_DIR):
        directory.mkdir(parents=True, exist_ok=True)


ensure_dirs()
