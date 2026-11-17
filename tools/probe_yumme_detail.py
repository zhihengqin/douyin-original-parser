"""Read the official Douyin Jingxuan H5 detail and optionally inspect its fplay routes.

Uses the exact request in official yumme-wap chunk 669.08d6f59a.js, module
94886, and the shared timestamp parameter in app.aa4973b6.js, module 65156.
No catalog or third-party parser is consulted. Signed addresses and tokens are
never written to the report. This tool reports listings, not verified originals.
"""
from __future__ import annotations

import argparse
import base64
import json
import random
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from original_parser.client import OriginalParser, ParseError, check_url, load_credentials

DETAIL_ENDPOINT = "https://jingxuan.douyin.com/yumme/v1/web/yumme/detail/"
ROW_FIELDS = ("quality", "definition", "size", "file_id", "file_hash", "vwidth",
              "vheight", "bitrate", "codec_type")


def safe_rows(model: dict) -> list[dict]:
    rows = model.get("video_list") or []
    if isinstance(rows, dict):
        rows = list(rows.values())
    if not isinstance(rows, list):
        return []
    result = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        meta = row.get("video_meta") or row
        if isinstance(meta, dict):
            result.append({key: meta.get(key) for key in ROW_FIELDS})
    return result


def probe(parser: OriginalParser, text: str, *, probe_fallback=False) -> dict:
    work = parser.resolve_id(text)
    params = {"aid": "392139", "app_name": "yumme", "version_code": "26.1.0",
              "device_platform": "web", "request_source": "50", "origin_type": "detail",
              "aweme_id": work, "timestamp": f"{int(time.time() * 1000)}_{random.random() * 1000000}"}
    report = {"aweme_id": work, "endpoint": DETAIL_ENDPOINT, "params": params,
              "catalog_used": False, "third_party_parser_used": False,
              "media_probe_performed": False, "original_verified": False, "fallback_routes": []}
    reply = parser._json(DETAIL_ENDPOINT + "?" + urlencode(params),
                         headers={"Referer": f"https://jingxuan.douyin.com/m/video/{work}?app=yumme"})
    detail = reply.get("yumme_detail")
    if not isinstance(detail, dict) or str(detail.get("aweme_id")) != work:
        raise ParseError("detail_unavailable", "Jingxuan H5 did not return this work")
    video = detail.get("video") or {}
    model = video.get("video_model") or {}
    model = json.loads(model) if isinstance(model, str) else model
    if not isinstance(model, dict):
        raise ParseError("source_unavailable", "Jingxuan H5 video_model is missing")
    vid = model.get("video_id")
    if vid != (video.get("play_addr") or {}).get("uri"):
        raise ParseError("identity_mismatch", "Jingxuan H5 video and model IDs differ")
    report.update(status_code=reply.get("status_code"), video_id=vid, video_keys=sorted(video),
                  model_keys=sorted(model), rows=safe_rows(model))
    fallback = model.get("fallback_api") or {}
    fallback = fallback.get("fallback_api") if isinstance(fallback, dict) else fallback
    if fallback and probe_fallback:
        part = urlsplit(check_url(fallback, ("snssdk.com",)))
        issued = parse_qs(part.query, keep_blank_values=True)
        for name, changes in (("codec8", {"codec_type": ["8"]}),
                              ("source", {"stream_type": ["source"]}),
                              ("original", {"codec_type": ["5"], "force_fids": [base64.b64encode(b"original").decode()]})):
            query = dict(issued)
            if name != "codec8":
                query.pop("logo_type", None)
            query.update(changes)
            route = {"name": name, "changed_query_fields": changes,
                     "removed_query_fields": [] if name == "codec8" else ["logo_type"]}
            try:
                payload = parser._json(urlunsplit((part.scheme, part.netloc, part.path,
                                                  urlencode(query, doseq=True), "")))
                data = (payload.get("video_info") or {}).get("data") or {}
                route.update(code=payload.get("code"), status=data.get("status"),
                             video_id=data.get("video_id"), rows=safe_rows(data))
                if data.get("video_id") and data["video_id"] != vid:
                    raise ParseError("identity_mismatch", "fplay returned another video ID")
            except ParseError as exc:
                route["error_code"] = exc.code
                report["fallback_routes"].append(route)
                if exc.code in ("upstream_rate_limited", "upstream_forbidden", "identity_mismatch"):
                    report["incomplete"] = True
                    break
                continue
            report["fallback_routes"].append(route)
    return report


def main(argv=None) -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("link")
    cli.add_argument("--cookie-file", type=Path)
    cli.add_argument("--probe-fallback", action="store_true")
    cli.add_argument("--output", type=Path, required=True)
    args = cli.parse_args(argv)
    cookies, ua = load_credentials(args.cookie_file) if args.cookie_file else ({}, None)
    try:
        with OriginalParser(cookies=cookies, user_agent=ua, auto_guest=False) as parser:
            report = probe(parser, args.link, probe_fallback=args.probe_fallback)
    except Exception as exc:
        report = {"error_type": type(exc).__name__, "error_code": getattr(exc, "code", None),
                  "incomplete": True, "original_verified": False}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report.get(key) for key in ("aweme_id", "video_id", "error_code", "original_verified")}, ensure_ascii=False))
    return 2 if report.get("error_type") else 0


if __name__ == "__main__":
    raise SystemExit(main())
