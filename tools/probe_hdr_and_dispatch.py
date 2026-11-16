"""1) 试 HDR 能力参数；2) 用外部链接 CDN 头里的对象 MD5 验证官方分发是否接受该对象。

第 2 步只用于证明"该对象就是本作品的原片身份"，不作生产取址依据。
"""

import base64
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlunsplit, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from original_parser.client import OriginalParser, ParseError, check_url  # noqa: E402
from original_parser.codec import decode_url  # noqa: E402

AWEME = "7707993970332290314"
EXTERNAL_MD5 = "b4665e915a3177897c2cffc8bff735ed"
EXTERNAL_SIZE = 38562411

HDR_VARIANTS = [
    ("support_hdr=1", {"support_hdr": "1", "stream_type": "source"}),
    ("hdr_type=1", {"hdr_type": "1", "stream_type": "source"}),
    ("enable_hdr=1", {"enable_hdr": "1", "stream_type": "source"}),
]

with OriginalParser(auto_guest=True) as parser:
    detail = parser.detail(AWEME)
    video = detail.get("video") or {}
    model = video.get("video_model")
    if isinstance(model, str):
        model = json.loads(model)
    vid = (video.get("play_addr") or {}).get("uri")
    fallback = model.get("fallback_api")
    url = fallback.get("fallback_api") if isinstance(fallback, dict) else fallback
    part = urlsplit(check_url(url, ("snssdk.com",)))
    base = parse_qs(part.query, keep_blank_values=True)
    base.pop("logo_type", None)

    print("=== HDR 能力参数 ===")
    for label, extra in HDR_VARIANTS:
        params = {k: list(v) for k, v in base.items()}
        for key, value in extra.items():
            params[key] = [value]
        request_url = urlunsplit((part.scheme, part.netloc, part.path,
                                  urlencode(params, doseq=True), ""))
        try:
            payload = parser._json(request_url, stage="原画接口")
        except Exception as exc:  # noqa: BLE001
            print(f"{label:16} ERR {type(exc).__name__}")
            continue
        data = (payload.get("video_info") or {}).get("data") or {}
        rows = data.get("video_list") or []
        if isinstance(rows, dict):
            rows = list(rows.values())
        buckets = set()
        for row in rows:
            addr = (row or {}).get("main_url") if isinstance(row, dict) else None
            if not isinstance(addr, str):
                continue
            try:
                decoded = decode_url(addr, data.get("key_seed", ""))
            except Exception:  # noqa: BLE001
                continue
            q = urlsplit(decoded)
            buckets |= {x for x in q.path.split("/") if x.startswith("tos-cn-")}
        print(f"{label:16} rows={len(rows)} buckets={sorted(buckets)}")

    print("\n=== 官方分发接受性（外部 MD5 仅作验证） ===")
    for file_id in (vid, "v28033gi0000dbs4nevog65jrl6u1s10"):
        params = {"video_id": vid, "file_id": file_id, "line": "0", "is_play_url": "1",
                  "source": "PackSourceEnum_AWEME_DETAIL", "sign": EXTERNAL_MD5}
        dispatch = "https://www.douyin.com/aweme/v1/play/?" + urlencode(params)
        try:
            with parser._get(dispatch, headers={"Range": "bytes=0-15",
                                                "Accept-Encoding": "identity"}) as response:
                total = response.headers.get("Content-Range", "").split("/")[-1]
                print(f"file_id={file_id[:12]}… HTTP {response.status_code} "
                      f"total={total} ftyp={response.content[4:8]!r}")
        except ParseError as exc:
            print(f"file_id={file_id[:12]}… {exc.code}: {exc}")
