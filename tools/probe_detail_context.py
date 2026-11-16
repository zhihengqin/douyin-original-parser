"""探针：换详情请求的客户端上下文，看平台是否给出不同的 video_model / 原片档。

只发官方详情接口（aid=392139，DETAIL_URL），按不同 device_platform 取证；
不下载媒体、不改 catalog。
"""

import base64
import json
import sys
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlunsplit, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from original_parser.client import (  # noqa: E402
    DETAIL_URL, MEDIA_HOSTS, OriginalParser, ParseError, check_url, signed_headers,
    signed_query,
)
from original_parser.codec import decode_url  # noqa: E402

A = sys.argv[1] if len(sys.argv) > 1 else "7707993970332290314"

CONTEXTS = [
    ("webapp", "webapp"),
    ("android", "android"),
    ("iphone", "iphone"),
    ("unknown", "unknown"),
]

ANDROID_UA = ("com.ss.android.ugc.aweme/410000 (Linux; U; Android 13; zh_CN; "
              "SM-G981B; Build/TP1A.220624.014; Cronet/TTNetVersion:3d3d0a4b 2023-11-01)")


def bucket_of(row, seed):
    addr = row.get("main_url") or row.get("backup_url")
    if not isinstance(addr, str):
        return None
    try:
        decoded = decode_url(addr, seed)
    except Exception:  # noqa: BLE001
        return None
    return next((x for x in urlsplit(decoded).path.split("/") if x.startswith("tos-cn-")), None)


with OriginalParser(auto_guest=True) as parser:
    parser.detail(A)  # 先走一次正常详情，完成访客初始化并拿到 UIFID
    for label, platform in CONTEXTS:
        params = {"aweme_id": A, "aid": "392139", "device_platform": platform}
        signed = signed_query(params, parser.cookies)
        url = DETAIL_URL + "?" + (signed or urlencode(params))
        headers = {"User-Agent": parser.user_agent if platform == "webapp" else ANDROID_UA}
        headers.update(signed_headers(signed))
        try:
            data = parser._json(url, headers=headers, stage=f"详情({label})")
        except ParseError as exc:
            print(f"{label:8} {exc.code}: {str(exc)[:70]}")
            continue
        detail = data.get("aweme_detail")
        if not isinstance(detail, dict):
            print(f"{label:8} 无 aweme_detail keys={list(data)[:6]}")
            continue
        video = detail.get("video") or {}
        model = video.get("video_model")
        try:
            model = json.loads(model) if isinstance(model, str) else model
        except ValueError:
            model = None
        fallback = (model or {}).get("fallback_api")
        fplay = fallback.get("fallback_api") if isinstance(fallback, dict) else None
        q = parse_qs(urlsplit(fplay).query) if isinstance(fplay, str) else {}
        rows = (model or {}).get("video_list") or []
        if isinstance(rows, dict):
            rows = list(rows.values())
        buckets = sorted({b for row in rows if isinstance(row, dict)
                          for b in [bucket_of(row.get("video_meta") and row or row, "")] if b})
        print(f"{label:8} HDR={video.get('is_source_HDR')} model_rows={len(rows)} "
              f"dev={q.get('device_platform', ['-'])[0]} codec={q.get('codec_type', ['-'])[0]} "
              f"vq={q.get('vquality', ['-'])[0]} imp={q.get('imp', ['-'])[0]}")
        print(f"         qualities={sorted({str((r.get('video_meta') or r).get('quality')) for r in rows if isinstance(r, dict)})}")
        if isinstance(fplay, str):
            # 用同一上下文打一次 fplay，看是否出现原片桶行
            part = urlsplit(check_url(fplay, ("snssdk.com",)))
            fp = parse_qs(part.query, keep_blank_values=True)
            fp.pop("logo_type", None)
            fp["force_fids"] = [base64.b64encode(b"original").decode("ascii")]
            fp["codec_type"] = ["5"]
            req = urlunsplit((part.scheme, part.netloc, part.path, urlencode(fp, doseq=True), ""))
            try:
                payload = parser._json(req, stage="原画接口")
            except ParseError as exc:
                print(f"         fplay {exc.code}")
                continue
            data2 = (payload.get("video_info") or {}).get("data") or {}
            rows2 = data2.get("video_list") or []
            if isinstance(rows2, dict):
                rows2 = list(rows2.values())
            seed = data2.get("key_seed", "")
            found = sorted({b for row in rows2 if isinstance(row, dict)
                            for b in [bucket_of(row, seed)] if b})
            print(f"         fplay rows={len(rows2)} buckets={found} "
                  f"star={'YES' if any(b.startswith('tos-cn-v-') for b in found) else 'no'}")
