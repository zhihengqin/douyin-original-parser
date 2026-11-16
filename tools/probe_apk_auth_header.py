"""字符串定位探针；DEX 字符串相邻不代表存在同一条播放鉴权调用链。

归属必须按具体方法核对；本脚本命中的 AWS4/QoS 常量不证明播放器需要
Authorization，见 docs/original-investigation-2026-11-16-auth-consumer-audit.md。
"""

import re
import zipfile
from pathlib import Path

APK = Path(__file__).resolve().parent.parent / "douyin-32.2.6" / "douyin-32.2.6.apk"
NEEDLES = [b"AWS4-HMAC-SHA256", b"SHA256 Credential", b"SignedHeaders", b"aws4_request",
           b"AKLT", b"GetPlayInfoToken", b"ptoken"]
TEXT = re.compile(rb"[ -~]{6,}")


def show(blob, needle, width=80, limit=3):
    results = []
    for match in list(re.finditer(re.escape(needle), blob))[:limit]:
        window = blob[max(0, match.start() - width):match.end() + width]
        results.append(" | ".join(r.decode("ascii", "replace") for r in TEXT.findall(window))[:300])
    return results


with zipfile.ZipFile(APK) as archive:
    for name in sorted(n for n in archive.namelist() if n.endswith(".dex")):
        blob = archive.read(name)
        hits = [needle for needle in NEEDLES if needle in blob]
        if not hits:
            continue
        print(f"\n=== {name} hits={[h.decode() for h in hits]}")
        for needle in hits:
            for line in show(blob, needle):
                print("   ", line)
