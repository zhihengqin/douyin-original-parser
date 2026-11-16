"""探针：挖出 GetPlayInfo openapi 模板周围的常量（host、ptoken 来源、附加参数）。"""

import re
import zipfile
from pathlib import Path

APK = Path(__file__).resolve().parent.parent / "douyin-32.2.6" / "douyin-32.2.6.apk"
NEEDLE = b"video/openapi/v1/?action=GetPlayInfo"
TEXT = re.compile(rb"[ -~]{4,}")

with zipfile.ZipFile(APK) as archive:
    for name in ("classes30.dex", "classes4.dex"):
        blob = archive.read(name)
        print(f"\n===== {name} =====")
        for match in re.finditer(re.escape(NEEDLE), blob):
            start = max(0, match.start() - 700)
            window = blob[start:match.end() + 700]
            print(f"-- offset {match.start()} --")
            for run in TEXT.findall(window):
                text = run.decode("ascii", "replace")
                if len(text) >= 4:
                    print("   ", text[:160])
        for needle in (b"ptoken", b"vod-urls", b"video/openapi"):
            count = blob.count(needle)
            print(f"count {needle.decode()}: {count}")
