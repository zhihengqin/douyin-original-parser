"""只读探针：检查若干作品当前是否被官方 fplay 列举原画档位。

只发两类请求：官方作品详情、官方备用播放接口（两个选择器）。不改 catalog、
不下载媒体、不使用任何外部哈希。用于回答"原画列举是随时间消失，还是只对
部分作品开放"。
"""

import argparse
import base64
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlunsplit, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from original_parser.client import OriginalParser, ParseError, check_url  # noqa: E402

SELECTORS = (
    ("original", {"force_fids": base64.b64encode(b"original").decode("ascii"),
                  "codec_type": "5"}),
    ("source", {"stream_type": "source"}),
)


def selector_urls(model: dict, video_id: str) -> list[tuple[str, str]]:
    fallback = model.get("fallback_api")
    url = fallback.get("fallback_api") if isinstance(fallback, dict) else fallback
    if not isinstance(url, str):
        raise ParseError("source_unavailable", "详情没有备用播放接口")
    p = urlsplit(check_url(url, ("snssdk.com",)))
    out = []
    for name, extra in SELECTORS:
        params = parse_qs(p.query, keep_blank_values=True)
        params.pop("logo_type", None)
        for key, value in extra.items():
            params[key] = [value]
        out.append((name, urlunsplit((p.scheme, p.netloc, p.path,
                                      urlencode(params, doseq=True), ""))))
    return out


def summarize(payload: dict) -> dict:
    info = payload.get("video_info") or {}
    data = info.get("data") or {}
    rows = data.get("video_list") or []
    if isinstance(rows, dict):
        rows = list(rows.values())
    rows = [r for r in rows if isinstance(r, dict)]
    qualities = sorted({str(r.get("quality") or "?") for r in rows})
    biggest = max(rows, key=lambda r: int(r.get("size") or 0)) if rows else {}
    return {
        "code": payload.get("code"), "info_code": info.get("code"),
        "status": data.get("status"), "video_id": data.get("video_id"),
        "rows": len(rows), "qualities": qualities,
        "has_hash": sorted(str(r.get("quality")) for r in rows if r.get("file_hash")),
        "max_size": int(biggest.get("size") or 0),
        "max_row": {"quality": biggest.get("quality"),
                    "vwidth": biggest.get("vwidth"), "vheight": biggest.get("vheight"),
                    "size": int(biggest.get("size") or 0),
                    "codec_type": biggest.get("codec_type")},
        "original_rows": [
            {"quality": r.get("quality"), "size": int(r.get("size") or 0),
             "vwidth": r.get("vwidth"), "vheight": r.get("vheight"),
             "file_hash": r.get("file_hash"), "file_id": r.get("file_id")}
            for r in rows if str(r.get("quality") or "").lower() in ("original", "source")
        ],
    }


def probe_one(parser: OriginalParser, aweme_id: str) -> dict:
    record = {"aweme_id": aweme_id}
    try:
        detail = parser.detail(aweme_id)
    except ParseError as exc:
        record["error"] = f"{exc.code}: {exc}"
        return record
    video = detail.get("video") or {}
    model = video.get("video_model")
    if isinstance(model, str):
        try:
            model = json.loads(model)
        except ValueError:
            model = None
    video_id = (video.get("play_addr") or {}).get("uri")
    record.update({
        "video_id": video_id,
        "create_time": detail.get("create_time"),
        "duration": video.get("duration"),
        "ratio": video.get("ratio"),
        "vwidth": video.get("width"),
        "vheight": video.get("height"),
        "has_video_model": isinstance(model, dict),
        "is_from_ad_auth": detail.get("is_from_ad_auth"),
        "original": detail.get("original"),
        "selectors": {},
    })
    if not isinstance(model, dict):
        record["note"] = "详情未下发 video_model"
        return record
    for name, url in selector_urls(model, video_id):
        try:
            payload = parser._json(url, stage="原画接口")
            record["selectors"][name] = summarize(payload)
        except ParseError as exc:
            record["selectors"][name] = {"error": f"{exc.code}: {exc}"}
        time.sleep(3)
    return record


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("aweme_ids", nargs="+")
    ap.add_argument("--gap", type=float, default=6.0, help="作品之间的间隔秒数")
    ap.add_argument("--out", default="")
    args = ap.parse_args()

    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    results = []
    with OriginalParser(auto_guest=True) as parser:
        for index, aweme_id in enumerate(args.aweme_ids):
            if index:
                time.sleep(args.gap)
            results.append(probe_one(parser, aweme_id))
            row = results[-1]
            summary = ",".join(
                f"{k}={v.get('rows')}档/{','.join(v.get('qualities', []))}"
                if "rows" in v else f"{k}=ERR"
                for k, v in (row.get("selectors") or {}).items()
            ) or row.get("error") or row.get("note")
            print(f"{aweme_id} {summary}", flush=True)

    report = {"started_at": started, "results": results}
    if args.out:
        Path(args.out).write_text(json.dumps(report, ensure_ascii=False, indent=2),
                                  encoding="utf-8")
        print(f"\n报告：{args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
