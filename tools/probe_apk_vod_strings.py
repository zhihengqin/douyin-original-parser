"""探针：在 APK 的 dex / so 里搜 VOD 播放授权的调用形态（URL 模板与参数名）。"""

import re
import zipfile
from pathlib import Path

APK = Path(__file__).resolve().parent.parent / "douyin-32.2.6" / "douyin-32.2.6.apk"
NEEDLES = [b"GetPlayInfo", b"bytedanceapi", b"play_auth_token", b"X-Amz-SignedQueries",
           b"X-Amz-NotSignBody", b"vod-luna", b"/vid/", b"PlayAuth"]
TEXT = re.compile(rb"[ -~]{6,}")


def contexts(blob, needle, width=90, limit=4):
    out = []
    for match in re.finditer(re.escape(needle), blob):
        start = max(0, match.start() - width)
        window = blob[start:match.end() + width]
        runs = TEXT.findall(window)
        joined = " | ".join(run.decode("ascii", "replace") for run in runs)
        out.append(joined[:260])
        if len(out) >= limit:
            break
    return out


with zipfile.ZipFile(APK) as archive:
    targets = [n for n in archive.namelist()
               if n.endswith(".dex") or (n.startswith("lib/") and n.endswith(".so"))]
    print("scanning", len(targets), "entries")
    for name in targets:
        blob = archive.read(name)
        hits = [needle for needle in NEEDLES if needle in blob]
        if not hits:
            continue
        print(f"\n=== {name}  hits={[h.decode() for h in hits]}")
        for needle in hits:
            for context in contexts(blob, needle):
                print("   ", context)
