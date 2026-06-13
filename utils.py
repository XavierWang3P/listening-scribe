import mimetypes
import re
from pathlib import Path
from urllib import parse


def clean_name(value: str) -> str:
    """
    文件名清洗器：
    过滤掉操作系统不允许或者不推荐在文件名中使用的危险字符（如 `\ / : * ? " < > |`），
    统一替换为下划线。并移除首尾的多余空格和点，以防文件名欺骗或路径拼接故障。
    """
    name = re.sub(r'[\\/:*?"<>|]+', "_", value).strip()
    return name.strip(". ") or "audio"


def audio_ext(filename: str, content_type: str = "") -> str:
    """
    推导或提取安全的音频文件后缀名。
    1. 优先提取原始文件名中的后缀，如果匹配 `.[a-z0-9]` 格式则保留。
    2. 如果文件名没有合理后缀，则根据 HTTP 请求头中的 Content-Type 进行 MIME 类型猜测推理。
    3. 兜底返回 `.bin`。
    """
    suffix = Path(filename).suffix.lower()
    if re.fullmatch(r"\.[a-z0-9]{1,12}", suffix or ""):
        return suffix
    guessed = mimetypes.guess_extension(content_type or "")
    return guessed or ".bin"


def quote_path(*parts: str) -> str:
    """
    对路径的各个层级部分依次执行安全 URL 编码。
    将特殊字符进行 `%XX` 转义，同时保留 `-_.~` 等 URL 协议标准安全字符。
    主要用于生成合法的 Web 文件资源引用链接。
    """
    return "/".join(parse.quote(part, safe="-_.~") for part in parts)


def safe_relative_path(value: str) -> Path:
    """
    路径安全检查防线（防御路径遍历/跨目录读取攻击）：
    1. 先对相对路径做 URL 反编码，并将 Windows 下的反斜线 `\` 统一替换为正斜线 `/`。
    2. 对路径分段层级进行严密校验：绝对路径、或路径段落中含有上溯符 `..` 的均视为恶意请求，并直接抛出 RuntimeError。
    """
    value = parse.unquote(value).replace("\\", "/")
    path = Path(value)
    if path.is_absolute() or ".." in path.parts:
        raise RuntimeError("Invalid path")
    return path


def normalized_path(environ) -> str:
    """
    对 WSGI 中的 PATH_INFO 请求路径执行解码与规范化处理。
    由于部分 WSGI 服务器会对 PATH_INFO 采用 latin-1 编码读取，在此优先尝试将其转回 utf-8 字符串以防中文目录及路径乱码。
    """
    path = environ.get("PATH_INFO", "/")
    try:
        return parse.unquote(path.encode("latin-1").decode("utf-8"))
    except UnicodeError:
        return parse.unquote(path)


def valid_record_id(value: str) -> bool:
    """
    校验 Record ID 是否符合系统严格约定的字符串特征规范：
    支持 `YYYYMMDD-HHMMSS-8位UUID` 格式 或 64 字节的 SHA256 音频指纹格式。
    """
    return bool(re.fullmatch(r"(?:[0-9]{8}-[0-9]{6}-[a-f0-9]{8}|[a-f0-9]{64})", value))
