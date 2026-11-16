"""只读探针：抓作品的详情特征，用于对照"是否仍列举原画"。"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from original_parser.client import OriginalParser, ParseError  # noqa: E402

IDS = [
    "7695305664234589459",  # 列举
    "7706430541934972201",  # 列举
    "7706477018388536499",  # 列举
    "7707264789998849307",  # 列举
    "7706466342664277290",  # 不列举
    "7706732556430953770",  # 不列举
    "7706731996801731894",  # 不列举（详情失败）
    "7707196543073275177",  # 不列举
    "7707234108203650342",  # 不列举
    "7707561244894580004",  # 不列举
]

out = []
with OriginalParser(auto_guest=True) as parser:
    for index, aweme_id in enumerate(IDS):
        if index:
            time.sleep(6)
        row = {"aweme_id": aweme_id}
        try:
            detail = parser.detail(aweme_id)
        except ParseError as exc:
            row["error"] = f"{exc.code}: {exc}"
            out.append(row)
            print(aweme_id, "ERR", exc.code, flush=True)
            continue
        video = detail.get("video") or {}
        stats = detail.get("statistics") or {}
        row.update({
            "aweme_type": detail.get("aweme_type"),
            "media_type": detail.get("media_type"),
            "create_time": detail.get("create_time"),
            "is_top": detail.get("is_top"),
            "original": detail.get("original"),
            "is_from_ad_auth": detail.get("is_from_ad_auth"),
            "play_count": stats.get("play_count"),
            "digg_count": stats.get("digg_count"),
            "comment_count": stats.get("comment_count"),
            "share_count": stats.get("share_count"),
            "collect_count": stats.get("collect_count"),
            "duration": video.get("duration"),
            "ratio": video.get("ratio"),
            "width": video.get("width"),
            "height": video.get("height"),
            "video_tags": video.get("tags") or video.get("tag"),
            "has_watermark": video.get("has_watermark"),
            "bit_rate_count": len((video.get("bit_rate") or [])),
            "bit_rate_gears": [b.get("gear_name") for b in (video.get("bit_rate") or [])],
            "author_uid": ((detail.get("author") or {}).get("uid")),
        })
        out.append(row)
        print(aweme_id, row.get("play_count"), row.get("digg_count"), row.get("ratio"),
              row.get("bit_rate_gears"), flush=True)

Path("output/detail-probe.json").write_text(
    json.dumps({"results": out}, ensure_ascii=False, indent=2), encoding="utf-8")
