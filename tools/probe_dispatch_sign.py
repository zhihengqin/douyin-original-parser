"""核实：官方分发的跳转目标形状，以及 sign 是否必须是真实整文件 MD5。"""

import sys
from pathlib import Path
from urllib.parse import urlencode, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from original_parser.client import OriginalParser, ParseError  # noqa: E402

VID = "v28033gi0000dbs4nevog65jrl6u1s10"
REAL_MD5 = "b4665e915a3177897c2cffc8bff735ed"
CASES = [
    ("真实 MD5", REAL_MD5),
    ("全零 32 位", "0" * 32),
    ("另一个普通档 MD5", "8cb2358a9f30b153326f5a9c06267948"),
]

with OriginalParser(auto_guest=True) as parser:
    for label, sign in CASES:
        params = {"video_id": VID, "file_id": VID, "line": "0", "is_play_url": "1",
                  "source": "PackSourceEnum_AWEME_DETAIL", "sign": sign}
        url = "https://www.douyin.com/aweme/v1/play/?" + urlencode(params)
        try:
            with parser._get(url, headers={"Range": "bytes=0-15",
                                           "Accept-Encoding": "identity"}) as response:
                total = response.headers.get("Content-Range", "").split("/")[-1]
                target = urlsplit(response.url)
                bucket = next((x for x in target.path.split("/") if x.startswith("tos-cn-")), "-")
                keys = sorted(k for k in target.query.split("&") if k)
                print(f"{label:16} HTTP {response.status_code} total={total} "
                      f"host={target.netloc} bucket={bucket}")
                print(f"                 query={keys}")
        except ParseError as exc:
            print(f"{label:16} {exc.code}: {exc}")
