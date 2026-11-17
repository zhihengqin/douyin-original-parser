"""尝试破解 file_id 的推导规律：用手上已知的 url_key / size / bitrate 与 file_id 配对验证。

用法：python tools/crack_file_id.py
"""
from __future__ import annotations

import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

VID = "v03033g10000dbs82lnog65ls2l3ol5g"
# (url_key, file_id, size, bitrate, codec, quality)
PAIRS = (
    (f"{VID}_h264_540p_1112036", "93890dffa15741f5884a55e3a4ef6391", 45992041, 1112036, "h264", "540p"),
    (f"{VID}_bytevc1_720p_686804", "4bdd7aa5efbc4352a6d6f63df0f96e37", 28405118, 686804, "bytevc1", "720p"),
    (f"{VID}_bytevc1_540p_590319", "d37dbc65b8f8415786bc40093973e006", 24414636, 590319, "bytevc1", "540p"),
    (f"{VID}_bytevc1_540p_511116", "f3ef68ad2e2a473ea25beafe4adff94d", 21138968, 511116, "bytevc1", "540p"),
)


def md5(text: str) -> str:
    return hashlib.md5(text.encode()).hexdigest()


def variants(pair) -> dict[str, str]:
    url_key, _, size, bitrate, codec, quality = pair
    made = {
        "url_key": md5(url_key),
        "url_key 去前缀": md5(url_key.replace(VID + "_", "")),
        "vid+bitrate": md5(f"{VID}{bitrate}"),
        "bitrate+vid": md5(f"{bitrate}{VID}"),
        "vid+size": md5(f"{VID}{size}"),
        "size+vid": md5(f"{size}{VID}"),
        "size": md5(str(size)),
        "bitrate": md5(str(bitrate)),
        "vid": md5(VID),
        "vid_codec_quality_bitrate": md5(f"{VID}_{codec}_{quality}_{bitrate}"),
        "vid+codec+quality": md5(f"{VID}_{codec}_{quality}"),
        "codec_quality_bitrate": md5(f"{codec}_{quality}_{bitrate}"),
        "vid_size_bitrate": md5(f"{VID}_{size}_{bitrate}"),
        "size_bitrate": md5(f"{size}_{bitrate}"),
    }
    return made


def main() -> int:
    lines = ["用已知 4 组配对验证 file_id 推导规律："]
    hit_names = None
    for pair in PAIRS:
        target = pair[1]
        made = variants(pair)
        matched = [name for name, value in made.items() if value == target]
        lines.append(f"\n目标 file_id={target} size={pair[2]} bitrate={pair[3]}")
        lines.append(f"  命中={matched or '无'}")
        hit_names = set(matched) if hit_names is None else hit_names & set(matched)
    lines.append(f"\n四组共同命中的推导={sorted(hit_names) if hit_names else '无'}")
    text = "\n".join(lines)
    print(text)
    out = ROOT / "output"
    out.mkdir(exist_ok=True)
    (out / "crack-file-id.txt").write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
