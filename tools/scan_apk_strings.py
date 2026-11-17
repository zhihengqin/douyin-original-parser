"""在 APK 的 dex / so 里做字节级字符串扫描，定位 HDR 原片相关字段与方法。

用法：python tools/scan_apk_strings.py [apk路径]
"""
from __future__ import annotations

import sys
import zipfile
from pathlib import Path

NEEDLES = (
    b"play_addr_hdr",
    b"is_source_HDR",
    b"play_addr_hdr_265",
    b"play_addr_hdr_h264",
    b"GetPlayInfo",
    b"openapi/v1",
    b"X-Gorgon",
    b"x-gorgon",
    b"AWS4-HMAC-SHA256",
    b"video/openapi",
    b"play_auth_token",
    b"PTokenAuth",
    b"PlayTokenAuth",
)


def main(argv: list[str]) -> int:
    root = Path(__file__).resolve().parent.parent
    apk = Path(argv[1]) if len(argv) > 1 else root / "douyin-32.2.6" / "douyin-32.2.6.apk"
    hits: dict[str, dict[bytes, int]] = {}
    with zipfile.ZipFile(apk) as archive:
        for name in archive.namelist():
            if not (name.endswith(".dex") or name.endswith(".so")):
                continue
            blob = archive.read(name)
            found = {needle: blob.count(needle) for needle in NEEDLES if needle in blob}
            if found:
                hits[name] = found
    lines = []
    for name in sorted(hits):
        detail = ", ".join(f"{needle.decode()}={count}" for needle, count in sorted(hits[name].items()))
        lines.append(f"{name}: {detail}")
    text = "\n".join(lines) if lines else "无命中"
    print(text)
    out = root / "output"
    out.mkdir(exist_ok=True)
    (out / "apk-string-scan.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
