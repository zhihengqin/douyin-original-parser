"""验证新增开源项目提供的旧官方 API、分享页变体及播放入口。

仅输入作品链接；不运行上游应用、不读登录文件/catalog/参考文件。
在五仓库探针基础上增加有限的兼容性请求，所有结果脱敏。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from original_parser.client import OriginalParser, ParseError  # noqa: E402
from tools.probe_official_vid_lineage import inspect_identity  # noqa: E402
from tools.probe_repo_algorithm import (  # noqa: E402
    FAILURES, MOBILE_UA, ProbeParser, failure, probe_fplay, probe_link, safe_vid, share_detail,
    validate_detail,
)

MAX_LEGACY_BYTES = 2 * 1024 * 1024
IPHONE_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) "
             "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/16.0 "
             "Mobile/15E148 Safari/604.1")
APP_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 16_6 like Mac OS X) "
          "AppleWebKit/605.1.15 (KHTML, like Gecko) Mobile/15E148 "
          "aweme/32.7.0 NetType/WIFI Channel/App Store")
LEGACY_UA = ("Mozilla/5.0 (iPhone; CPU iPhone OS 11_0 like Mac OS X) "
             "AppleWebKit/604.1.38 (KHTML, like Gecko) Version/11.0 "
             "Mobile/15A372 Safari/604.1")


def legacy_detail(parser: OriginalParser, work: str, *, app_api: bool) -> tuple[dict | None, dict]:
    if app_api:
        url = "https://api-hl.amemv.com/aweme/v1/aweme/detail/?" + urlencode({
            "aid": "1128", "app_name": "aweme", "version_code": "251", "aweme_id": work})
    else:
        url = "https://www.iesdouyin.com/web/api/v2/aweme/iteminfo/?" + urlencode({"item_ids": work})
    result = {"route": "legacy_app_detail" if app_api else "legacy_iteminfo",
              "original_verified": False}
    with parser._get(url, headers={"User-Agent": LEGACY_UA}) as response:
        result["http_status"] = response.status_code
        if response.status_code != 200:
            result["outcome"] = "http_rejected"
            return None, result
        chunks, size = [], 0
        for chunk in response.iter_content(65536):
            size += len(chunk)
            if size > MAX_LEGACY_BYTES:
                raise ValueError("legacy_json_budget_exceeded")
            chunks.append(chunk)
        result["body_bytes"] = size
    try:
        payload = json.loads(b"".join(chunks))
    except (ValueError, UnicodeError):
        result["outcome"] = "empty_response" if not size else "non_json_response"
        return None, result
    if not isinstance(payload, dict):
        raise ValueError("legacy_payload_not_object")
    status = payload.get("status_code")
    result["status_code"] = status if isinstance(status, int) else None
    if status not in (None, 0):
        result["outcome"] = "platform_error"
        return None, result
    rows = ([payload["aweme_detail"]] if isinstance(payload.get("aweme_detail"), dict) else []) if app_api else payload.get("item_list") or []
    if not isinstance(rows, list):
        raise ValueError("legacy_items_not_list")
    result["item_count"] = len(rows)
    for detail in rows[:16]:
        if not isinstance(detail, dict) or str(detail.get("aweme_id")) != work:
            continue
        validate_detail(detail, work)
        result["outcome"] = "matching_detail_returned"
        return detail, result
    result["outcome"] = "matching_detail_not_returned"
    return None, result


def inspect_address(parser: OriginalParser, url: str, *, user_agent: str = IPHONE_UA) -> dict:
    result = {"original_verified": False}
    with parser._get(url, headers={"User-Agent": user_agent, "Range": "bytes=0-0",
                                   "Accept-Encoding": "identity"}) as response:
        result["http_status"] = response.status_code
        if response.status_code not in (200, 206):
            result["outcome"] = "http_rejected"
            return result
        match = re.fullmatch(r"bytes 0-0/(\d+)", response.headers.get("Content-Range", ""))
        if response.status_code != 206 or not match:
            result["outcome"] = "not_a_verifiable_range_response"
            return result
        size, final_url = int(match[1]), response.url
        if len(response.raw.read(2, decode_content=False)) != 1:
            raise ValueError("range_length_mismatch")
    result.update(inspect_identity(parser, final_url, size))
    result["buckets"] = [part for part in urlsplit(final_url).path.split("/")
                         if re.fullmatch(r"tos-cn-(?:v|ve)-[a-z0-9-]+", part)]
    result["outcome"] = "play_candidate_identity_unconfirmed"
    return result


def inspect_new_detail(parser: OriginalParser, detail: dict, work: str, result: dict,
                       seen_media: set[str]) -> None:
    video = validate_detail(detail, work)
    result.update(vid=safe_vid((video.get("play_addr") or {}).get("uri")),
                  model_present=bool(video.get("video_model")),
                  bit_rate_rows=len(video.get("bit_rate") or []))
    if video.get("video_model"):
        result["source_routes"] = probe_fplay(parser, video)
        result["original_verified"] = any(r.get("original_verified") for r in result["source_routes"])
        result["verification_incomplete"] = any(r.get("error_type") or r.get("candidates_omitted")
                                                or r.get("outcome") == "media_not_verified"
                                                for r in result["source_routes"])
    candidates = []
    for field in ("play_addr", "download_addr"):
        urls = (video.get(field) or {}).get("url_list") or []
        if not urls or not isinstance(urls[0], str):
            continue
        # Change only the documented watermark endpoint, preserving its query.
        url = urls[0].replace("/playwm/", "/play/")
        if url in seen_media:
            continue
        seen_media.add(url)
        try:
            candidate = inspect_address(parser, url)
        except FAILURES as exc:
            candidate = failure(exc)
        candidates.append({"field": field, **candidate})
    if candidates:
        result["media_candidates"] = candidates
        result["verification_incomplete"] = result.get("verification_incomplete", False) or any(
            c.get("error_type") for c in candidates)


def plain_play(parser: OriginalParser, vid: str, *, ies: bool) -> dict:
    if not safe_vid(vid):
        raise ValueError("invalid_video_id")
    endpoint = ("http://www.iesdouyin.com/aweme/v1/play/" if ies else
                "https://www.douyin.com/aweme/v1/play/")
    params = {"video_id": vid, "ratio": "1080p" if ies else "default"}
    if ies:
        params["line"] = "0"
    result = {"route": "videodl_ies_play_1080p" if ies else "tiktokdownloader_bare_default",
              "requested_vid": vid, "original_verified": False}
    result.update(inspect_address(parser, endpoint + "?" + urlencode(params),
                                  user_agent=IPHONE_UA if ies else parser.user_agent))
    return result


def additional_routes(parser: OriginalParser, work: str, vid: str | None) -> list[dict]:
    results = []
    seen_media = set()
    for app_api in (False, True):
        item = {"route": "legacy_app_detail" if app_api else "legacy_iteminfo"}
        try:
            detail, item = legacy_detail(parser, work, app_api=app_api)
            if detail:
                inspect_new_detail(parser, detail, work, item, seen_media)
                vid = vid or item.get("vid")
        except FAILURES as exc:
            item.update(failure(exc))
        results.append(item)
    for profile, ua, slash in (("videodl_ios16", IPHONE_UA, False),
                                ("ios16_trailing_slash", IPHONE_UA, True),
                                ("aweme_32_7_trailing_slash", APP_UA, True)):
        item = {"route": "share_page_variant", "profile": profile}
        try:
            detail, item = share_detail(parser, work, trailing_slash=slash, user_agent=ua)
            item.update(route="share_page_variant", profile=profile)
            if detail:
                inspect_new_detail(parser, detail, work, item, seen_media)
                vid = vid or item.get("vid")
        except FAILURES as exc:
            item.update(failure(exc))
        results.append(item)
    # CatchSnap explicitly forwards an anonymous ttwid across the two official
    # registrable domains, then merges iesdouyin Set-Cookie for one retry.
    for attempt in range(1, 3):
        item = {"route": "catchsnap_anonymous_cookie_share", "attempt": attempt}
        cookies = {c.name: c.value for c in parser.session.cookies
                   if c.domain.lstrip(".") in ("iesdouyin.com", "www.iesdouyin.com")}
        if parser.cookies.get("ttwid"):
            cookies["ttwid"] = parser.cookies["ttwid"]
        headers = {"Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                   "Accept-Language": "zh-CN,zh;q=0.9"}
        if cookies:
            headers["Cookie"] = "; ".join(f"{name}={value}" for name, value in cookies.items())
        try:
            detail, item = share_detail(parser, work, trailing_slash=True,
                                         user_agent=MOBILE_UA, request_headers=headers)
            item.update(route="catchsnap_anonymous_cookie_share", attempt=attempt,
                        anonymous_cookie_attached=bool(cookies))
            if detail:
                inspect_new_detail(parser, detail, work, item, seen_media)
                vid = vid or item.get("vid")
        except FAILURES as exc:
            detail = None
            item.update(failure(exc))
        results.append(item)
        if detail:
            break
    if vid:
        for ies in (False, True):
            try:
                results.append(plain_play(parser, vid, ies=ies))
            except FAILURES as exc:
                results.append({"route": "videodl_ies_play_1080p" if ies else
                                "tiktokdownloader_bare_default", **failure(exc)})
    return results


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("link")
    ap.add_argument("--out", required=True, type=Path)
    ap.add_argument("--direct", action="store_true")
    args = ap.parse_args(argv)
    report = {"started_at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    try:
        with ProbeParser(auto_guest=True, timeout=12, allow_external_asset_recovery=False) as parser:
            if args.direct:
                parser.session.trust_env = False
            report.update(probe_link(parser, args.link))
            extra = additional_routes(parser, report["aweme_id"], (report.get("detail") or {}).get("vid"))
            report["additional_routes"] = extra
            report["original_verified"] = report["original_verified"] or any(r.get("original_verified") for r in extra)
            report["routes_incomplete"] = report["routes_incomplete"] or parser.budget_exhausted or any(
                r.get("error_type") or r.get("verification_incomplete") for r in extra)
            report["result"] = ("official_source_verified" if report["original_verified"] else
                                "investigation_incomplete" if report["routes_incomplete"] else "original_not_discovered")
            report["budget"] = {"http_requests": parser.http_requests,
                                "range_bytes_requested": parser.range_bytes_requested,
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
