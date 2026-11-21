"""只凭作品链接复核五个开源项目涉及的官方取址路线。

用法：python tools/probe_repo_algorithm.py LINK --out report.json --direct
仅使用匿名访客和官方接口；不读登录文件、原片目录或参考样本，不保存临时 URL。
exit 0 表示发现官方 original/source 且 MP4 校验通过；exit 2 表示尚未证实。
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

import requests

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from original_parser.client import (  # noqa: E402
    PLATFORM_HOSTS, OriginalParser, ParseError, check_url,
)
from tools.probe_official_vid_lineage import inspect_identity, rows_of  # noqa: E402

MAX_HTML_BYTES = 4 * 1024 * 1024
MAX_SOURCE_CANDIDATES = 3
MAX_HTTP_REQUESTS = 64
MAX_RANGE_BYTES = 8 * 1024 * 1024
MAX_PROBE_SECONDS = 120
VID = re.compile(r"v[A-Za-z0-9]{15,63}")
MOBILE_UA = (
    "Mozilla/5.0 (iPhone; CPU iPhone OS 17_2 like Mac OS X) "
    "AppleWebKit/605.1.15 (KHTML, like Gecko) EdgiOS/121.0.2277.107 "
    "Version/17.0 Mobile/15E148 Safari/604.1"
)
FAILURES = (ParseError, requests.RequestException, ValueError, TypeError, OSError, ImportError)


class ProbeParser(OriginalParser):
    """为整个实验限制 HTTP 次数（含跳转）、Range 预算和发起请求的总时限。"""

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.http_requests = 0
        self.range_bytes_requested = 0
        self.budget_exhausted = False
        self.request_deadline = time.monotonic() + MAX_PROBE_SECONDS
        self._transport_request = self.session.request
        self.session.request = self._budgeted_request

    def _budgeted_request(self, method, url, **kwargs):
        match = re.fullmatch(r"bytes=(\d+)-(\d+)", (kwargs.get("headers") or {}).get("Range", ""))
        length = int(match[2]) - int(match[1]) + 1 if match else 0
        remaining = self.request_deadline - time.monotonic()
        if (remaining <= 0 or self.http_requests >= MAX_HTTP_REQUESTS
                or self.range_bytes_requested + length > MAX_RANGE_BYTES):
            self.budget_exhausted = True
            raise ParseError("probe_budget_exceeded", "实验请求预算耗尽，结果不完整")
        self.http_requests += 1
        self.range_bytes_requested += length
        kwargs["timeout"] = min(kwargs.get("timeout") or self.timeout, remaining)
        return self._transport_request(method, url, **kwargs)


def failure(exc: Exception) -> dict:
    # Exception messages can contain signed URLs or arbitrary upstream text.
    result = {"outcome": "request_or_validation_failed", "error_type": type(exc).__name__}
    if isinstance(exc, ParseError):
        result["error_code"] = exc.code
    return result


def number(value) -> int:
    try:
        return max(0, int(value or 0))
    except (ValueError, TypeError, OverflowError):
        return 0


def safe_vid(value) -> str | None:
    return value if isinstance(value, str) and VID.fullmatch(value) else None


def validate_detail(detail: dict, work: str) -> dict:
    if not isinstance(detail, dict) or str(detail.get("aweme_id")) != work:
        raise ParseError("identity_mismatch", "作品详情标识不匹配")
    video = detail.get("video")
    if not isinstance(video, dict):
        raise ValueError("missing_video")
    return video


def source_requests(video: dict) -> tuple[str, list[tuple[str, str]]]:
    vid = (video.get("play_addr") or {}).get("uri")
    if not isinstance(vid, str) or not VID.fullmatch(vid):
        raise ValueError("invalid_video_id")
    model = video.get("video_model")
    model = json.loads(model) if isinstance(model, str) else model
    if not isinstance(model, dict):
        raise ValueError("missing_video_model")
    if model.get("video_id") != vid:
        raise ParseError("identity_mismatch", "播放模型与详情 VID 不一致")
    fallback = model.get("fallback_api")
    fallback = fallback.get("fallback_api") if isinstance(fallback, dict) else fallback
    part = urlsplit(check_url(fallback, ("snssdk.com",)))
    if not re.fullmatch(r"/video/fplay/1/[a-fA-F0-9]{32}/" + re.escape(vid), part.path):
        raise ValueError("unexpected_fallback_path")
    query = parse_qs(part.query, keep_blank_values=True)
    query.pop("logo_type", None)
    original = {**query, "force_fids": [base64.b64encode(b"original").decode()], "codec_type": ["5"]}
    source = {**query, "stream_type": ["source"]}
    requests_ = [("fplay_issued", fallback)]
    for name, params in (("fplay_original", original), ("fplay_source", source)):
        requests_.append((name, urlunsplit((part.scheme, part.netloc, part.path,
                                          urlencode(params, doseq=True), ""))))
    return vid, requests_


def validate_media(parser: OriginalParser, candidate: dict, requested_vid: str) -> dict:
    last = None
    for url in candidate["urls"]:
        try:
            measured = inspect_identity(parser, url, candidate["size"])
            if measured["embedded_vids"] and requested_vid not in measured["embedded_vids"]:
                # A different embedded VID can be lineage rather than a wrong
                # object. It requires more evidence; do not declare success here.
                return {"outcome": "embedded_identity_unconfirmed", "original_verified": False,
                        "embedded_vids": measured["embedded_vids"]}
            media = measured["media"]
            if not media["has_video"] or not media["has_audio"]:
                raise ValueError("incomplete_media")
            expected = float(candidate.get("duration_seconds") or 0)
            actual = float(media.get("duration_seconds") or 0)
            if actual <= 0 or expected <= 0 or abs(actual - expected) > 1:
                raise ParseError("identity_mismatch", "时长不匹配或缺失")
            track = next(t for t in media["tracks"] if t.get("type") == "vide")
            if (track.get("width"), track.get("height")) != (candidate["width"], candidate["height"]):
                raise ParseError("identity_mismatch", "分辨率不匹配")
            return {"outcome": "official_source_verified", "original_verified": True,
                    "official_quality": candidate["official_quality"],
                    "size": candidate["size"], "width": candidate["width"],
                    "height": candidate["height"], **measured}
        except FAILURES as exc:
            last = exc
    return failure(last or ValueError("no_media_url"))


def probe_fplay(parser: OriginalParser, video: dict) -> list[dict]:
    try:
        vid, urls = source_requests(video)
    except FAILURES as exc:
        return [{"route": "fplay", **failure(exc)}]
    results = []
    for name, url in urls:
        item = {"route": name, "requested_vid": vid, "original_verified": False}
        try:
            payload = parser._json(url, stage="开源路线复核")
            info = payload.get("video_info") or {}
            data = info.get("data") or {}
            rows = rows_of(data)
            item.update(code=payload.get("code") if isinstance(payload.get("code"), int) else None,
                        info_code=info.get("code") if isinstance(info.get("code"), int) else None,
                        status=data.get("status") if isinstance(data.get("status"), int) else None,
                        response_vid=safe_vid(data.get("video_id")),
                        row_count=len(rows), qualities=sorted({str(r.get("quality")) for r in rows
                            if re.fullmatch(r"[a-z0-9_-]{1,32}", str(r.get("quality")))}),
                        max_size=max((number(r.get("size")) for r in rows), default=0))
            # _source_candidates enforces status, VID, official quality, encryption,
            # container type and CDN allowlist. It never reads the local catalog.
            try:
                _, candidates = parser._source_candidates(payload, vid)
            except ParseError as exc:
                if (exc.code == "source_unavailable" and payload.get("code") == 0
                        and info.get("code") == 0 and data.get("status") == 10
                        and data.get("video_id") == vid and rows
                        and not any(str(r.get("quality")).lower() in ("original", "source") for r in rows)):
                    item["outcome"] = "no_official_source_in_response"
                else:
                    item.update(failure(exc))
            else:
                item["candidate_count"] = len(candidates)
                item["candidates_omitted"] = max(0, len(candidates) - MAX_SOURCE_CANDIDATES)
                item["candidates"] = [validate_media(parser, c, vid) for c in candidates[:MAX_SOURCE_CANDIDATES]]
                item["original_verified"] = any(c.get("original_verified") for c in item["candidates"])
                item["outcome"] = "official_source_verified" if item["original_verified"] else "media_not_verified"
        except FAILURES as exc:
            item.update(failure(exc))
        results.append(item)
    return results


def share_detail(parser: OriginalParser, work: str, *, trailing_slash: bool = False,
                 user_agent: str = MOBILE_UA, request_headers: dict | None = None) -> tuple[dict | None, dict]:
    item = {"route": "mobile_share_ssr", "original_verified": False}
    url = f"https://www.iesdouyin.com/share/video/{work}" + ("/" if trailing_slash else "")
    with parser._get(url, hosts=PLATFORM_HOSTS,
                     headers={**(request_headers or {}), "User-Agent": user_agent}) as response:
        item["http_status"] = response.status_code
        if response.status_code != 200:
            item["outcome"] = "http_rejected"
            return None, item
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > MAX_HTML_BYTES:
                raise ValueError("share_html_budget_exceeded")
            chunks.append(chunk)
        item["html_bytes"] = size
    html = b"".join(chunks).decode("utf-8", errors="replace")
    match = re.search(r"window\._ROUTER_DATA\s*=\s*(.*?)</script>", html, re.DOTALL)
    if not match:
        item["outcome"] = "router_data_not_present"
        return None, item
    router, _ = json.JSONDecoder().raw_decode(match.group(1).lstrip())
    loaders = router.get("loaderData") or {}
    observed_items = 0
    for key in ("video_(id)/page", "note_(id)/page"):
        items = ((loaders.get(key) or {}).get("videoInfoRes") or {}).get("item_list") or []
        observed_items += len(items)
        for detail in items[:16]:
            if not isinstance(detail, dict) or str(detail.get("aweme_id")) != work:
                continue
            video = validate_detail(detail, work)
            item.update(outcome="matching_play_address_returned", requested_work_matches=True,
                        vid=safe_vid((video.get("play_addr") or {}).get("uri")),
                        bit_rate_rows=len(video.get("bit_rate") or []))
            return detail, item
    item.update(outcome="work_identity_mismatch" if observed_items else "item_list_not_present",
                observed_items=observed_items)
    return None, item


def probe_link(parser: OriginalParser, link: str) -> dict:
    work = parser.resolve_id(link)
    report = {"schema_version": 1, "aweme_id": work,
              "catalog_used": False, "reference_used": False,
              "login_file_used": False, "third_party_parser_used": False,
              "routes": [], "original_verified": False}
    try:
        detail = parser.detail(work)
        video = validate_detail(detail, work)
        report["detail"] = {"aweme_id_matches": True,
                            "vid": safe_vid((video.get("play_addr") or {}).get("uri")),
                            "model_present": bool(video.get("video_model"))}
        report["routes"].extend(probe_fplay(parser, video))
    except FAILURES as exc:
        report["detail"] = failure(exc)
    try:
        shared, item = share_detail(parser, work)
        report["routes"].append(item)
        if shared:
            report["routes"].extend(probe_fplay(parser, validate_detail(shared, work)))
    except FAILURES as exc:
        report["routes"].append({"route": "mobile_share_ssr", **failure(exc)})
    report["original_verified"] = any(r.get("original_verified") for r in report["routes"])
    report["routes_incomplete"] = any(r.get("candidates_omitted") or r.get("error_type")
                                      or r.get("outcome") == "media_not_verified"
                                      for r in report["routes"])
    report["result"] = ("official_source_verified" if report["original_verified"] else
                        "investigation_incomplete" if report["routes_incomplete"] else "original_not_discovered")
    return report


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("link")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--direct", action="store_true", help="HTTP 请求不使用环境代理")
    args = ap.parse_args(argv)
    report = {"started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        with ProbeParser(auto_guest=True, timeout=12, allow_external_asset_recovery=False) as parser:
            if args.direct:
                parser.session.trust_env = False
            report.update(probe_link(parser, args.link))
            report["budget"] = {"http_requests": parser.http_requests,
                                "max_http_requests": MAX_HTTP_REQUESTS,
                                "range_bytes_requested": parser.range_bytes_requested,
                                "max_range_bytes": MAX_RANGE_BYTES,
                                "max_probe_seconds": MAX_PROBE_SECONDS,
                                "budget_exhausted": parser.budget_exhausted}
    except FAILURES as exc:
        report.update(failure(exc), original_verified=False)
    report["finished_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(report, ensure_ascii=True, indent=2))
    return 0 if report.get("original_verified") else 2


if __name__ == "__main__":
    raise SystemExit(main())
