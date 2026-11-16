"""对照：作品的 is_source_HDR / is_long_video 与"是否仍列举原片"。"""

import json
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from original_parser.client import OriginalParser, ParseError  # noqa: E402

LISTED = {
    "7695305664234589459": True,
    "7706430541934972201": True,
    "7706477018388536499": True,
    "7707264789998849307": True,
    "7706466342664277290": False,
    "7706732556430953770": False,
    "7706731996801731894": False,
    "7707196543073275177": False,
    "7707234108203650342": False,
    "7707561244894580004": False,
    "7707993970332290314": False,
}

rows = []
with OriginalParser(auto_guest=True) as parser:
    for index, (aweme_id, listed) in enumerate(LISTED.items()):
        if index:
            time.sleep(5)
        row = {"aweme_id": aweme_id, "listed": listed}
        try:
            detail = parser.detail(aweme_id)
        except ParseError as exc:
            row["error"] = exc.code
            rows.append(row)
            print(aweme_id, "ERR", exc.code, flush=True)
            continue
        video = detail.get("video") or {}
        row.update({
            "is_source_HDR": video.get("is_source_HDR"),
            "is_long_video": video.get("is_long_video"),
            "original": detail.get("original"),
            "play_count": (detail.get("statistics") or {}).get("play_count"),
            "ratio": video.get("ratio"),
            "is_ads": detail.get("is_ads"),
            "aweme_type": detail.get("aweme_type"),
        })
        rows.append(row)
        print(aweme_id, "listed=", listed, "HDR=", row["is_source_HDR"],
              "long=", row["is_long_video"], "ratio=", row["ratio"],
              "play=", row["play_count"], flush=True)

Path("output/hdr-vs-listing.json").write_text(json.dumps(rows, ensure_ascii=False, indent=2),
                                              encoding="utf-8")
