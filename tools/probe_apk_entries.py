"""探针：列出 APK 里与 VOD / 播放引擎相关的条目，便于定位 GetPlayInfo 的真实调用形态。"""

import zipfile
from pathlib import Path

APK = Path(__file__).resolve().parent.parent / "douyin-32.2.6" / "douyin-32.2.6.apk"

with zipfile.ZipFile(APK) as archive:
    names = archive.namelist()
    print("entries:", len(names))
    interesting = [n for n in names
                   if n.endswith(".dex") or "ttvideo" in n.lower() or "vod" in n.lower()
                   or "playinfo" in n.lower() or n.startswith("lib/")]
    for name in interesting[:60]:
        print(f"{archive.getinfo(name).file_size:>12,}  {name}")
    print("total interesting:", len(interesting))
