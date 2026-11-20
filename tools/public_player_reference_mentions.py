"""Find literal hints of a known media file in already received, decoded text bodies.

These observations concern declarations only. They do not verify that any URL
serves the file, or that the browser requested its bytes.
"""
from __future__ import annotations

import json
import re
from functools import lru_cache


# File identity only; never used to construct a network request.
REFERENCES = {
    "7708052871413075238": {"size": 140778272, "md5": "351f10c0e8f038973f2a63c9c749cb41"},
    "7707954213745085746": {"size": 523731371, "md5": "54266bc27c1c4ae85fd8e649e0d4e7c4"},
}
_SIZE_FIELDS = {"size", "data_size", "file_size", "datasize", "filesize"}
_HASH_FIELDS = {"md5", "file_hash", "file_md5", "filehash", "filemd5"}
_JSON_LIMIT = 4 * 1024 * 1024


@lru_cache(maxsize=64)
def _patterns(size: int, md5: str):
    if type(size) is not int or size <= 0 or not re.fullmatch(r"[a-fA-F0-9]{32}", md5):
        raise ValueError("Expected a positive byte count and a 32-digit hexadecimal MD5")
    return (
        re.compile(rb"(?<![a-zA-Z0-9_.+-])" + str(size).encode() + rb"(?![a-zA-Z0-9_]|\.\d)"),
        re.compile(rb"(?<![a-z0-9_])" + md5.encode() + rb"(?![a-z0-9_])", re.I),
    )


def scan_body(body: bytes, *, size: int, md5: str) -> dict:
    """Scan JSON or HTML bytes. Return counts and allowlisted names, never excerpts.

    Only standalone literals count, with MD5 matched case-insensitively. Size
    alone is weak evidence. A declared pair must be exact values on the same
    JSON object; HTML and non-JSON text can only produce literal mentions.
    """
    size_pattern, hash_pattern = _patterns(size, md5)
    size_mentions = sum(1 for _ in size_pattern.finditer(body))
    md5_mentions = sum(1 for _ in hash_pattern.finditer(body))
    result = {"size_mentions": size_mentions, "md5_mentions": md5_mentions,
              "classification": "md5_mention" if md5_mentions else "size_only" if size_mentions else "none",
              "declared_fields": []}
    if (not (size_mentions or md5_mentions) or len(body) > _JSON_LIMIT
            or body.lstrip()[:1] not in (b"{", b"[")):
        return result
    try:
        stack = [json.loads(body)]
    except (ValueError, UnicodeError, RecursionError):
        return result

    declared = set()
    while stack:
        obj = stack.pop()
        if isinstance(obj, dict):
            size_keys, hash_keys = set(), set()
            for k, v in obj.items():
                key = k.lower()
                if key in _SIZE_FIELDS and (type(v) is int and v == size
                                            or isinstance(v, str) and v == str(size)):
                    size_keys.add(key)
                if key in _HASH_FIELDS and isinstance(v, str) and v.lower() == md5.lower():
                    hash_keys.add(key)
                if isinstance(v, (dict, list)):
                    stack.append(v)
            declared.update(size_keys | hash_keys)
            if hash_keys and size_keys:
                result["classification"] = "declared_md5_and_size"
            elif hash_keys and result["classification"] != "declared_md5_and_size":
                result["classification"] = "declared_md5"
        elif isinstance(obj, list):
            stack.extend(v for v in obj if isinstance(v, (dict, list)))
    result["declared_fields"] = sorted(declared)
    return result
