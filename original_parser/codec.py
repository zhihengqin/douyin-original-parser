"""还原官方播放器返回的地址；不处理 DRM 或视频内容加密。"""

import base64
import hashlib
from urllib.parse import urlsplit

from cryptography.hazmat.primitives import padding
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

# 官方播放器 videodec 的地址派生常量；仅参与播放地址编码。
URL_SALT = bytes.fromhex(
    "4dd4c2e6b83162090e52b3c7a6733ba41cb2462b829ab58a196b39db57177524"
    "f49baf7f08e8d68d26a72e37c1a95a2f1f05a51892aef2949732b62a38aadd58"
)


def decode_url(value: str, key_seed: str = "") -> str:
    """支持普通 URL、Base64 URL、a8/1 地址封装，未知格式明确失败。"""
    if not isinstance(value, str) or not value:
        raise ValueError("播放地址为空")
    if value.startswith(("https://", "http://")):
        url = value
    else:
        raw = base64.b64decode(value, validate=True)
        if raw.startswith((b"https://", b"http://")):
            url = raw.decode("utf-8")
        else:
            if raw[:4] != b"\xa8\x00\x01\x00":
                raise ValueError("未知播放地址封装版本")
            seed = base64.b64decode(key_seed, validate=True)
            if len(seed) != 32 or len(raw) <= 4 or (len(raw) - 4) % 16:
                raise ValueError("播放地址或 key_seed 长度异常")
            material = hashlib.sha512(hashlib.sha512(seed).digest() + URL_SALT).digest()
            decoder = Cipher(algorithms.AES(material[:16]), modes.CBC(material[16:32])).decryptor()
            padded = decoder.update(raw[4:]) + decoder.finalize()
            unpadder = padding.PKCS7(128).unpadder()
            url = (unpadder.update(padded) + unpadder.finalize()).decode("utf-8")
    parsed = urlsplit(url)
    if parsed.scheme not in ("https", "http") or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("还原结果不是有效 HTTP 播放地址")
    return url
