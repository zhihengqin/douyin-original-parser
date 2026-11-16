"""诊断：打印某作品官方备用播放接口返回的全部档位字段。

只读；不下载媒体；不打印签名查询串，只打印主机与桶名，避免把凭据写进日志。
"""

import base64
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlunsplit, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from original_parser.client import OriginalParser, ParseError, check_url  # noqa: E402
from original_parser.codec import decode_url  # noqa: E402

AWEME = sys.argv[1] if len(sys.argv) > 1 else "7707993970332290314"

SELECTORS = (
    ("original", {"force_fids": base64.b64encode(b"original").decode("ascii"),
                  "codec_type": "5"}),
    ("source", {"stream_type": "source"}),
)

INFO_KEYS = ("quality", "vtype", "size", "vwidth", "vheight", "bitrate", "codec_type",
             "fps", "float_fps", "file_id", "file_hash", "encrypt", "spade_a",
             "encryption_method", "url_expire", "gears", "assign_tag")

with OriginalParser(auto_guest=True) as parser:
    try:
        detail = parser.detail(AWEME)
    except ParseError as exc:
        print("detail error:", exc.code, exc)
        raise SystemExit(1)

video = detail.get("video") or {}
model = video.get("video_model")
if isinstance(model, str):
    model = json.loads(model)
print("aweme:", detail.get("aweme_id"), "create:", detail.get("create_time"),
      "ratio:", video.get("ratio"), "dur:", video.get("duration"))
print("model keys:", sorted(model.keys()))


def describe_addr(label: str, addr):
    if not isinstance(addr, dict):
        return
    uris = addr.get("url_list") or []
    print(f"  {label}: uri={addr.get('uri')} data_size={addr.get('data_size')} "
          f"width={addr.get('width')} height={addr.get('height')} urls={len(uris)}")
    for item in uris[:4]:
        q = urlsplit(item)
        bucket = next((x for x in q.path.split("/") if x.startswith("tos-cn-")), "-")
        print(f"     host={q.netloc} bucket={bucket}")


print("video keys:", sorted(video.keys()))
for key in sorted(video.keys()):
    if key.startswith("play_addr") or key.startswith("download_addr") or "addr" in key:
        describe_addr(key, video.get(key))

fallback = model.get("fallback_api")
url = fallback.get("fallback_api") if isinstance(fallback, dict) else fallback
p = urlsplit(check_url(url, ("snssdk.com",)))
print("fplay path:", p.path, "query keys:", sorted(parse_qs(p.query).keys()))

for name, extra in SELECTORS:
    params = parse_qs(p.query, keep_blank_values=True)
    params.pop("logo_type", None)
    for key, value in extra.items():
        params[key] = [value]
    url2 = urlunsplit((p.scheme, p.netloc, p.path, urlencode(params, doseq=True), ""))
    payload = parser._json(url2, stage="原画接口")
    data = (payload.get("video_info") or {}).get("data") or {}
    rows = data.get("video_list") or []
    if isinstance(rows, dict):
        rows = list(rows.values())
    print()
    print(f"--- selector={name} code={payload.get('code')} info={payload.get('video_info', {}).get('code')} "
          f"status={data.get('status')} video_id={data.get('video_id')} rows={len(rows)}")
    print("data keys:", sorted(data.keys()))
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            print(index, "non-dict row", type(row).__name__)
            continue
        fields = {k: row.get(k) for k in INFO_KEYS if row.get(k) not in (None, "")}
        addr = next((row.get(k) for k in ("main_url", "backup_url", "backup_url_1")
                     if row.get(k)), None)
        bucket = host = notice = "-"
        if addr:
            try:
                decoded = decode_url(addr, data.get("key_seed", ""))
                q = urlsplit(decoded)
                host = q.netloc
                parts = q.path.split("/")
                bucket = "/".join([x for x in parts if x.startswith("tos-cn-")][:1]) or "-"
                notice = "decode=ok"
            except Exception as exc:  # noqa: BLE001
                notice = f"decode FAIL {type(exc).__name__}"
        else:
            notice = "no address"
        print(f"  [{index}] {json.dumps(fields, ensure_ascii=False)} {notice} host={host} bucket={bucket}")

    try:
        parser._source_candidates(payload, data.get("video_id"))
        print("  -> _source_candidates: OK")
    except ParseError as exc:
        print("  -> _source_candidates:", exc.code, exc)
