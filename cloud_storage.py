"""自研原生腾讯云语音识别 COS 与阿里云 OSS 上传/清理/预签名接口。

无需任何第三方依赖，纯标准库实现。
"""
import base64
import datetime
import hashlib
import hmac
import time
import urllib.parse
from pathlib import Path
from urllib import request

from config import env


def get_cos_config() -> tuple[str, str, str, str]:
    """获取 COS 配置参数。"""
    secret_id = env("COS_SECRET_ID") or env("TENCENT_SECRET_ID")
    secret_key = env("COS_SECRET_KEY") or env("TENCENT_SECRET_KEY")
    region = env("COS_REGION") or env("TENCENT_REGION") or "ap-guangzhou"
    bucket = env("COS_BUCKET")
    return (secret_id or "").strip(), (secret_key or "").strip(), (region or "").strip(), (bucket or "").strip()


def get_oss_config() -> tuple[str, str, str, str]:
    """获取 OSS 配置参数。"""
    access_key_id = env("OSS_ACCESS_KEY_ID")
    access_key_secret = env("OSS_ACCESS_KEY_SECRET")
    endpoint = env("OSS_ENDPOINT") or "oss-cn-hangzhou.aliyuncs.com"
    bucket = env("OSS_BUCKET")
    return (access_key_id or "").strip(), (access_key_secret or "").strip(), (endpoint or "").strip(), (bucket or "").strip()


def is_cloud_storage_enabled() -> bool:
    """检查是否启用了云存储上传。"""
    provider = (env("UPLOAD_PROVIDER") or "").lower().strip()
    if provider == "cos":
        sid, skey, _, bucket = get_cos_config()
        return bool(sid and skey and bucket)
    elif provider == "oss":
        aki, aks, _, bucket = get_oss_config()
        return bool(aki and aks and bucket)
    return False


# ── 腾讯云语音识别 COS 接口 ──────────────────────────────────────────────────────────

def cos_upload(local_file_path: Path, object_key: str) -> str:
    """上传本地文件到腾讯云语音识别 COS，返回预签名的 GET 下载地址。"""
    secret_id, secret_key, region, bucket = get_cos_config()
    if not secret_id or not secret_key or not bucket:
        raise RuntimeError("Tencent Cloud COS configuration is incomplete.")

    host = f"{bucket}.cos.{region}.myqcloud.com"
    url = f"https://{host}/{urllib.parse.quote(object_key)}"

    now = int(time.time())
    expire = now + 3600
    key_time = f"{now};{expire}"

    # 1. 计算 SignKey
    sign_key = hmac.new(secret_key.encode("utf-8"), key_time.encode("utf-8"), hashlib.sha1).hexdigest()

    # 2. 构造 HttpString (PUT 请求)
    header_list = "host"
    canonical_headers = f"host={host}"
    http_string = f"put\n/{object_key}\n\n{canonical_headers}\n"

    # 3. 计算 StringToSign
    string_to_sign = f"sha1\n{key_time}\n{hashlib.sha1(http_string.encode('utf-8')).hexdigest()}\n"

    # 4. 计算 Signature
    signature = hmac.new(sign_key.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha1).hexdigest()

    auth_header = (
        f"q-sign-algorithm=sha1&q-ak={secret_id}&q-sign-time={key_time}&"
        f"q-key-time={key_time}&q-header-list={header_list}&q-url-param-list=&q-signature={signature}"
    )

    # 读取文件
    with local_file_path.open("rb") as f:
        file_data = f.read()

    headers = {
        "Authorization": auth_header,
        "Host": host,
        "Content-Type": "audio/mpeg",
        "Content-Length": str(len(file_data)),
    }

    req = request.Request(url, data=file_data, headers=headers, method="PUT")
    with request.urlopen(req) as resp:
        resp.read()

    # 生成一个 24 小时过期的预签名 GET 地址供 ASR 拉取
    return cos_presigned_url(object_key)


def cos_presigned_url(object_key: str, expires_in: int = 86400) -> str:
    """生成腾讯云语音识别 COS 对象的预签名 GET URL。"""
    secret_id, secret_key, region, bucket = get_cos_config()
    host = f"{bucket}.cos.{region}.myqcloud.com"

    now = int(time.time())
    expire = now + expires_in
    key_time = f"{now};{expire}"

    sign_key = hmac.new(secret_key.encode("utf-8"), key_time.encode("utf-8"), hashlib.sha1).hexdigest()

    header_list = "host"
    canonical_headers = f"host={host}"
    http_string = f"get\n/{object_key}\n\n{canonical_headers}\n"
    string_to_sign = f"sha1\n{key_time}\n{hashlib.sha1(http_string.encode('utf-8')).hexdigest()}\n"
    signature = hmac.new(sign_key.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha1).hexdigest()

    params = {
        "q-sign-algorithm": "sha1",
        "q-ak": secret_id,
        "q-sign-time": key_time,
        "q-key-time": key_time,
        "q-header-list": header_list,
        "q-url-param-list": "",
        "q-signature": signature,
    }
    return f"https://{host}/{urllib.parse.quote(object_key)}?{urllib.parse.urlencode(params)}"


def cos_delete(object_key: str):
    """从腾讯云语音识别 COS 删除指定对象。"""
    secret_id, secret_key, region, bucket = get_cos_config()
    if not secret_id or not secret_key or not bucket:
        return

    host = f"{bucket}.cos.{region}.myqcloud.com"
    url = f"https://{host}/{urllib.parse.quote(object_key)}"

    now = int(time.time())
    expire = now + 3600
    key_time = f"{now};{expire}"

    sign_key = hmac.new(secret_key.encode("utf-8"), key_time.encode("utf-8"), hashlib.sha1).hexdigest()

    header_list = "host"
    canonical_headers = f"host={host}"
    http_string = f"delete\n/{object_key}\n\n{canonical_headers}\n"
    string_to_sign = f"sha1\n{key_time}\n{hashlib.sha1(http_string.encode('utf-8')).hexdigest()}\n"
    signature = hmac.new(sign_key.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha1).hexdigest()

    auth_header = (
        f"q-sign-algorithm=sha1&q-ak={secret_id}&q-sign-time={key_time}&"
        f"q-key-time={key_time}&q-header-list={header_list}&q-url-param-list=&q-signature={signature}"
    )

    headers = {
        "Authorization": auth_header,
        "Host": host,
    }

    req = request.Request(url, headers=headers, method="DELETE")
    try:
        with request.urlopen(req) as resp:
            resp.read()
    except Exception:
        pass


# ── 阿里云 OSS 接口 ──────────────────────────────────────────────────────────

def oss_upload(local_file_path: Path, object_key: str) -> str:
    """上传本地文件到阿里云 OSS，返回预签名的 GET 下载地址。"""
    access_key_id, access_key_secret, endpoint, bucket = get_oss_config()
    if not access_key_id or not access_key_secret or not bucket:
        raise RuntimeError("Aliyun OSS configuration is incomplete.")

    url = f"https://{bucket}.{endpoint}/{urllib.parse.quote(object_key)}"
    now = datetime.datetime.utcnow()
    date_str = now.strftime("%a, %d %b %Y %H:%M:%S GMT")

    content_type = "audio/mpeg"
    resource = f"/{bucket}/{object_key}"
    string_to_sign = f"PUT\n\n{content_type}\n{date_str}\n{resource}"

    h = hmac.new(access_key_secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha1)
    signature = base64.b64encode(h.digest()).decode("utf-8")

    with local_file_path.open("rb") as f:
        file_data = f.read()

    headers = {
        "Authorization": f"OSS {access_key_id}:{signature}",
        "Date": date_str,
        "Content-Type": content_type,
        "Content-Length": str(len(file_data)),
    }

    req = request.Request(url, data=file_data, headers=headers, method="PUT")
    with request.urlopen(req) as resp:
        resp.read()

    # 生成一个 24 小时过期的预签名 GET 地址供 ASR 拉取
    return oss_presigned_url(object_key)


def oss_presigned_url(object_key: str, expires_in: int = 86400) -> str:
    """生成阿里云 OSS 对象的预签名 GET URL。"""
    access_key_id, access_key_secret, endpoint, bucket = get_oss_config()
    expires = int(time.time()) + expires_in
    resource = f"/{bucket}/{object_key}"
    string_to_sign = f"GET\n\n\n{expires}\n{resource}"

    h = hmac.new(access_key_secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha1)
    signature = base64.b64encode(h.digest()).decode("utf-8")

    params = {
        "OSSAccessKeyId": access_key_id,
        "Expires": str(expires),
        "Signature": signature,
    }
    return f"https://{bucket}.{endpoint}/{urllib.parse.quote(object_key)}?{urllib.parse.urlencode(params)}"


def oss_delete(object_key: str):
    """从阿里云 OSS 删除指定对象。"""
    access_key_id, access_key_secret, endpoint, bucket = get_oss_config()
    if not access_key_id or not access_key_secret or not bucket:
        return

    url = f"https://{bucket}.{endpoint}/{urllib.parse.quote(object_key)}"
    now = datetime.datetime.utcnow()
    date_str = now.strftime("%a, %d %b %Y %H:%M:%S GMT")

    resource = f"/{bucket}/{object_key}"
    string_to_sign = f"DELETE\n\n\n{date_str}\n{resource}"

    h = hmac.new(access_key_secret.encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha1)
    signature = base64.b64encode(h.digest()).decode("utf-8")

    headers = {
        "Authorization": f"OSS {access_key_id}:{signature}",
        "Date": date_str,
    }

    req = request.Request(url, headers=headers, method="DELETE")
    try:
        with request.urlopen(req) as resp:
            resp.read()
    except Exception:
        pass
