"""换 host 探测：App 侧的 play 接口是否给 HDR 作品下发原片。

候选 host：
  https://aweme.snssdk.com/aweme/v1/play/
  https://api-play.amemv.com/aweme/v1/play/
  https://api.amemv.com/aweme/v1/play/
  https://www.iesdouyin.com/aweme/v1/play/（网页壳，已测）
每个 host 试 ratio=default 与 ratio=1080p，带与不带 sign。
"""
from __future__ import annotations

import sys
from pathlib import Path
from urllib.parse import urlencode

import requests

HOSTS = [
    "https://aweme.snssdk.com",
    "https://api-play.amemv.com",
    "https://api.amemv.com",
]
UA_APP = (
    "com.ss.android.ugc.aweme/320206 (Linux; U; Android 13; zh_CN; "
    "Pixel 7; Build/TQ3A.230805.001; Cronet/58.0.2991.0)"
)


def main(argv: list[str]) -> int:
    if len(argv) < 3:
        print(__doc__)
        return 2
    aweme_id, video_id = argv[1], argv[2]
    sign = argv[3] if len(argv) > 3 else None

    lines = [f"aweme_id={aweme_id} video_id={video_id} sign={sign}"]
    for host in HOSTS:
        for ratio in ("default", "1080p"):
            params = {
                "video_id": video_id,
                "ratio": ratio,
                "line": "0",
                "is_play_url": "1",
                "watermark": "0",
                "source": "PackSourceEnum_AWEME_DETAIL",
                "aid": "1128",
            }
            if sign:
                params["sign"] = sign
                params["file_id"] = video_id
            url = f"{host}/aweme/v1/play/?{urlencode(params)}"
            try:
                resp = requests.get(
                    url,
                    headers={"User-Agent": UA_APP, "Accept": "*/*", "Range": "bytes=0-0"},
                    allow_redirects=True,
                    timeout=20,
                )
            except Exception as error:  # noqa: BLE001
                lines.append(f"{host} {ratio}: !! {type(error).__name__}")
                continue
            total = (resp.headers.get("Content-Range") or "").rsplit("/", 1)[-1]
            lines.append(
                f"{host} {ratio}: status={resp.status_code} ct={resp.headers.get('Content-Type')} total={total}"
            )
            lines.append(f"  final={resp.url[:160]}")
    text = "\n".join(lines)
    print(text)
    root = Path(__file__).resolve().parent.parent / "output"
    root.mkdir(exist_ok=True)
    (root / f"play-hosts-{aweme_id}.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
