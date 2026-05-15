import mimetypes
import re
from pathlib import Path
from urllib import parse


def clean_name(value: str) -> str:
    name = re.sub(r'[\\/:*?"<>|]+', "_", value).strip()
    return name.strip(". ") or "audio"


def audio_ext(filename: str, content_type: str = "") -> str:
    suffix = Path(filename).suffix.lower()
    if re.fullmatch(r"\.[a-z0-9]{1,12}", suffix or ""):
        return suffix
    guessed = mimetypes.guess_extension(content_type or "")
    return guessed or ".bin"


def quote_path(*parts: str) -> str:
    return "/".join(parse.quote(part, safe="-_.~") for part in parts)


def safe_relative_path(value: str) -> Path:
    value = parse.unquote(value).replace("\\", "/")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise RuntimeError("Invalid path")
    return path


def normalized_path(environ) -> str:
    path = environ.get("PATH_INFO", "/")
    try:
        return parse.unquote(path.encode("latin-1").decode("utf-8"))
    except UnicodeError:
        return parse.unquote(path)


def valid_record_id(value: str) -> bool:
    return bool(re.fullmatch(r"(?:[0-9]{8}-[0-9]{6}-[a-f0-9]{8}|[a-f0-9]{64})", value))
