"""Capture a sanitized anonymous/login desktop-Web catalog comparison.

The browser naturally loads each work page, then page.fetch requests the three
catalog selectors derived from the page's own video_model. Credential values
stay in memory and are never written to the report.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

from playwright.async_api import Error, async_playwright

PROJECT = Path(__file__).resolve().parents[1]
WORKS = ("7707954213745085746", "7708052871413075238")
SESSION_COOKIE_NAMES = {"sessionid", "sessionid_ss", "sid_tt"}
SENSITIVE_NAME = re.compile(
    r"(?:cookie|auth|token|secret|sign|signature|session|passport|csrf|"
    r"webid|uifid|verify|fingerprint|device_id|nonce|ticket|sid|fp|"
    r"a_bogus|x_bogus|ms_token|odin_tt|uid_tt|user_id|trace|logid|"
    r"eagleid|request_id|visitor_id)", re.I)
SAFE_KEY = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,80}$")


def stamp() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


def digest(value: str | bytes) -> str:
    raw = value if isinstance(value, bytes) else value.encode("utf-8", "surrogatepass")
    return hashlib.sha256(raw).hexdigest()


def safe_name(value: object) -> str:
    text = str(value)
    return text if SAFE_KEY.fullmatch(text) else "*"


def safe_url(value: str) -> dict:
    parts = urlsplit(value)
    query = parse_qs(parts.query, keep_blank_values=True)
    values = {}
    for name, entries in sorted(query.items()):
        key = safe_name(name)
        safe_values = []
        for item in entries:
            if name.lower() in {"aid", "codec_type", "force_fids", "stream_type",
                                "vquality", "ratio", "line", "is_play_url", "watermark",
                                "source", "device_platform", "platform", "version_code"}:
                safe_values.append(item[:256])
            else:
                safe_values.append({"present": bool(item), "length": len(item), "sha256": digest(item)})
        values[key] = safe_values
    return {"scheme": parts.scheme, "host": parts.hostname, "path": parts.path,
            "query_keys": sorted(safe_name(key) for key in query), "query": values,
            "url_sha256": digest(value)}


def safe_header_value(name: str, value: object) -> object:
    name = name.lower()
    text = str(value)
    if name in {"cookie", "set-cookie"}:
        cookie_names = sorted({part.split("=", 1)[0].strip() for part in text.split(";") if "=" in part})
        return {"present": bool(text), "names": cookie_names}
    if SENSITIVE_NAME.search(name):
        return {"present": bool(text), "length": len(text), "sha256": digest(text)}
    if name in {"referer", "origin"}:
        parts = urlsplit(text)
        return {"scheme": parts.scheme, "host": parts.hostname, "path": parts.path}
    return text[:512]


def safe_headers(headers: dict) -> dict:
    return {safe_name(name.lower()): safe_header_value(name, value)
            for name, value in sorted(headers.items(), key=lambda pair: pair[0].lower())}


def body_summary(body: str | None) -> dict:
    if body is None:
        return {"readable": False}
    raw = body.encode("utf-8", "replace")
    result = {"readable": True, "bytes": len(raw), "sha256": digest(raw)}
    try:
        obj = json.loads(body)
    except (ValueError, RecursionError):
        result["json"] = False
        return result
    result["json"] = True
    result["shape"] = shape(obj)
    return result


def shape(value, path="$", counts=None, depth=0):
    if counts is None:
        counts = {}
    typ = type(value).__name__
    counts[path] = {"type": typ, "count": counts.get(path, {}).get("count", 0) + 1}
    if depth >= 12:
        return counts
    if isinstance(value, dict):
        for key, child in value.items():
            shape(child, path + "." + safe_name(key), counts, depth + 1)
    elif isinstance(value, list):
        for child in value[:40]:
            shape(child, path + "[]", counts, depth + 1)
    return counts


def flatten_model_url(model: dict) -> str | None:
    fallback = model.get("fallback_api")
    value = fallback.get("fallback_api") if isinstance(fallback, dict) else fallback
    return value if isinstance(value, str) else None


def catalog_urls(model: dict) -> dict[str, str]:
    issued = flatten_model_url(model)
    if not issued:
        return {}
    parts = urlsplit(issued)
    video_id = parts.path.rsplit("/", 1)[-1]
    if (parts.scheme != "https" or not parts.hostname
            or not (parts.hostname == "snssdk.com" or parts.hostname.endswith(".snssdk.com"))
            or not re.fullmatch(r"/video/fplay/1/[a-fA-F0-9]{32}/[A-Za-z0-9_-]{10,128}", parts.path)
            or not video_id or parse_qs(parts.query).get("aid", [""])[0] != "392139"):
        return {}
    base = parse_qs(parts.query, keep_blank_values=True)
    original = dict(base)
    original.pop("logo_type", None)
    original["force_fids"] = [base64.b64encode(b"original").decode("ascii")]
    original["codec_type"] = ["5"]
    source = dict(base)
    source.pop("logo_type", None)
    source["stream_type"] = ["source"]
    return {
        "original": urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(original, doseq=True), "")),
        "source": urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(source, doseq=True), "")),
        "issued": issued,
    }


def row_summary(row: dict) -> dict:
    meta = row.get("video_meta") if isinstance(row.get("video_meta"), dict) else {}
    merged = {**row, **meta}
    quality = merged.get("quality")
    row_result = {
        "quality": quality if isinstance(quality, str) and len(quality) <= 40 else "unknown",
        "outer_quality": row.get("quality") if isinstance(row.get("quality"), str) else None,
        "meta_quality": meta.get("quality") if isinstance(meta.get("quality"), str) else None,
        "size": safe_int(merged.get("size")),
        "width": safe_int(merged.get("vwidth", merged.get("width"))),
        "height": safe_int(merged.get("vheight", merged.get("height"))),
        "bitrate": safe_int(merged.get("bitrate")),
        "codec_type": safe_int(merged.get("codec_type")),
        "file_hash": None,
        "has_url": False,
        "url_count": 0,
    }
    file_hash = merged.get("file_hash")
    if isinstance(file_hash, str) and re.fullmatch(r"[0-9a-fA-F]{32}", file_hash):
        row_result["file_hash"] = file_hash.lower()
    address = row.get("play_addr") or meta.get("play_addr")
    if isinstance(address, dict):
        urls = address.get("url_list") or []
        row_result["url_count"] = len(urls) if isinstance(urls, list) else 0
        row_result["has_url"] = row_result["url_count"] > 0
    return row_result


def safe_int(value):
    if isinstance(value, bool):
        return None
    try:
        result = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return result if abs(result) < 10**16 else None


def verify_official_originals(payload: dict, video_id: str, cookies: dict, user_agent: str) -> dict:
    """Probe only catalog rows explicitly tagged source/original by the service."""
    from original_parser import OriginalParser, ParseError

    try:
        with OriginalParser(cookies=cookies, user_agent=user_agent, auto_guest=False,
                            allow_external_asset_recovery=False) as parser:
            _, candidates = parser._source_candidates(payload, video_id)
            checks = []
            for candidate in candidates:
                try:
                    media = parser.probe(candidate)
                    checks.append({"quality": candidate.get("quality"), "file_hash": candidate.get("file_hash"),
                                   "declared_size": candidate.get("size"), "media_valid": bool(media.get("ok")),
                                   "actual_size": media.get("actual_size"),
                                   "duration_seconds": media.get("duration_seconds"),
                                   "has_video": media.get("has_video"), "has_audio": media.get("has_audio"),
                                   "width": candidate.get("width"), "height": candidate.get("height")})
                    if media.get("ok"):
                        break
                except ParseError as error:
                    checks.append({"quality": candidate.get("quality"), "file_hash": candidate.get("file_hash"),
                                   "declared_size": candidate.get("size"), "media_valid": False,
                                   "error_code": error.code})
            return {"candidate_count": len(candidates), "checks": checks,
                    "verified": any(check.get("media_valid") for check in checks)}
    except ParseError as error:
        return {"candidate_count": 0, "checks": [], "verified": False, "error_code": error.code}


def catalog_summary(text: str | None, expected_vid: str) -> dict:
    base = body_summary(text)
    if text is None:
        return base
    try:
        payload = json.loads(text)
    except (ValueError, RecursionError):
        return base
    if not isinstance(payload, dict):
        return base
    info = payload.get("video_info") if isinstance(payload.get("video_info"), dict) else {}
    data = info.get("data") if isinstance(info.get("data"), dict) else {}
    rows = data.get("video_list")
    rows = list(rows.values()) if isinstance(rows, dict) else rows
    if not isinstance(rows, list):
        rows = []
    vid = data.get("video_id")
    base["catalog"] = {
        "code": safe_int(payload.get("code")),
        "inner_code": safe_int(info.get("code")),
        "status": safe_int(data.get("status")),
        "vid_matches_detail": vid == expected_vid,
        "vid_sha256": digest(vid) if isinstance(vid, str) else None,
        "row_count": len(rows),
        "rows": [row_summary(row) for row in rows[:100] if isinstance(row, dict)],
    }
    return base


def sensitive_request_body(request: dict) -> dict:
    post_data = request.get("postData")
    if not isinstance(post_data, str):
        return {"present": False}
    output = {"present": True, "bytes": len(post_data.encode("utf-8", "replace")),
              "sha256": digest(post_data)}
    try:
        parsed = json.loads(post_data)
    except (ValueError, RecursionError):
        output["json"] = False
    else:
        output["json"] = True
        output["shape"] = shape(parsed)
    return output


def stack_summary(initiator: dict) -> dict:
    frames = []
    stack = initiator.get("stack") if isinstance(initiator, dict) else None
    while isinstance(stack, dict) and len(frames) < 12:
        for frame in stack.get("callFrames", [])[:12 - len(frames)]:
            location = safe_url(frame.get("url", "")) if frame.get("url") else None
            frames.append({"function": str(frame.get("functionName") or "")[:120],
                           "url": location,
                           "line": safe_int(frame.get("lineNumber")),
                           "column": safe_int(frame.get("columnNumber"))})
        stack = stack.get("parent")
    return {"type": initiator.get("type") if isinstance(initiator, dict) else None,
            "stack": frames}


def route_kind(url: str, resource_type: str | None = None) -> str | None:
    parts = urlsplit(url)
    path = parts.path.rstrip("/")
    host = (parts.hostname or "").lower()
    if host in {"www.douyin.com", "douyin.com"} and path == "/aweme/v1/web/aweme/detail":
        return "detail"
    if "/video/fplay/" in path and (host == "snssdk.com" or host.endswith(".snssdk.com")):
        return "catalog"
    if resource_type in {"XHR", "Fetch"}:
        return "web_json_route"
    return None


class NetworkCapture:
    def __init__(self):
        self.requests = {}
        self.pending_extra = {}
        self.events = []

    def _update_headers(self, request_id, key, headers):
        row = self.requests.get(request_id)
        if row is None:
            self.pending_extra.setdefault(request_id, {})[key] = headers
            return
        row[key] = safe_headers(headers)

    def request_will_be_sent(self, event):
        request_id = event.get("requestId")
        req = event.get("request") or {}
        url = req.get("url", "")
        kind = route_kind(url, event.get("type"))
        if kind is None:
            return
        row = {"request_id": request_id, "route_kind": kind,
               "resource_type": event.get("type"), "request": safe_url(url),
               "method": req.get("method"), "headers": safe_headers(req.get("headers") or {}),
               "body": sensitive_request_body(req),
               "initiator": stack_summary(event.get("initiator") or {}),
               "request_timestamp": event.get("timestamp"), "wall_time": event.get("wallTime")}
        previous = self.requests.get(request_id)
        if previous:
            previous.setdefault("redirects", []).append(row)
            self.requests[request_id] = row
        else:
            self.requests[request_id] = row
        for key, headers in self.pending_extra.pop(request_id, {}).items():
            self._update_headers(request_id, key, headers)
        self.events.append(row)

    def request_extra(self, event):
        self._update_headers(event.get("requestId"), "extra_headers", event.get("headers") or {})

    def response_received(self, event):
        request_id = event.get("requestId")
        row = self.requests.get(request_id)
        if row is None:
            return
        response = event.get("response") or {}
        row["response"] = {
            "status": safe_int(response.get("status")),
            "status_text": str(response.get("statusText") or "")[:120],
            "mime_type": str(response.get("mimeType") or "")[:120],
            "protocol": response.get("protocol"),
            "headers": safe_headers(response.get("headers") or {}),
            "timing": {key: val for key, val in (response.get("timing") or {}).items()
                       if isinstance(val, (int, float)) and not isinstance(val, bool)},
            "from_disk_cache": bool(response.get("fromDiskCache")),
            "from_service_worker": bool(response.get("fromServiceWorker")),
            "response_timestamp": event.get("timestamp"),
        }

    def response_extra(self, event):
        row = self.requests.get(event.get("requestId"))
        if row is not None:
            row.setdefault("response_extra", {})["headers"] = safe_headers(event.get("headers") or {})
            row["response_extra"]["status"] = safe_int(event.get("statusCode"))

    def loading_finished(self, event):
        row = self.requests.get(event.get("requestId"))
        if row is not None:
            row["loading_finished"] = {"timestamp": event.get("timestamp"),
                                       "encoded_data_length": safe_int(event.get("encodedDataLength"))}

    def loading_failed(self, event):
        row = self.requests.get(event.get("requestId"))
        if row is not None:
            row["loading_failed"] = {"timestamp": event.get("timestamp"),
                                     "error_text": str(event.get("errorText") or "")[:120],
                                     "blocked_reason": event.get("blockedReason")}

    async def read_bodies(self, cdp):
        for row in self.events:
            response = row.get("response") or {}
            mime = (response.get("mime_type") or "").lower()
            finished = row.get("loading_finished")
            if (not finished or not ("json" in mime or mime.endswith("+json"))
                    or finished.get("encoded_data_length", 0) > 4 * 1024 * 1024):
                continue
            try:
                result = await cdp.send("Network.getResponseBody", {"requestId": row["request_id"]})
                body = result.get("body")
                if result.get("base64Encoded") and isinstance(body, str):
                    decoded = base64.b64decode(body, validate=False)
                    body = decoded.decode("utf-8", "replace")
                if isinstance(body, str):
                    if row.get("route_kind") in {"detail", "catalog"}:
                        row["response_body"] = body_summary(body)
                    else:
                        summary = body_summary(body)
                        shape_data = summary.pop("shape", {})
                        summary["root_keys"] = sorted(
                            key[2:] for key in shape_data
                            if key.startswith("$.") and "." not in key[2:] and "[" not in key
                        )[:100]
                        summary["root_shape_fields"] = len(shape_data)
                        row["response_body"] = summary
            except (Error, ValueError):
                row["response_body"] = {"readable": False}


async def read_json_response(response):
    try:
        value = await response.json()
        return value if isinstance(value, dict) else None
    except (ValueError, Error):
        return None


async def capture_context(browser, label: str, work: str, credentials: dict | None,
                          user_agent: str, settle_ms: int) -> dict:
    settings = {"locale": "zh-CN", "timezone_id": "Asia/Shanghai",
                "viewport": {"width": 1440, "height": 960}, "user_agent": user_agent}
    context = await browser.new_context(**settings)
    cookie_names = []
    if credentials:
        cookies = credentials.get("cookies") or {}
        cookie_names = sorted(str(name) for name in cookies)
        await context.add_cookies([
            {"name": str(name), "value": str(value), "domain": ".douyin.com", "path": "/",
             "secure": True, "httpOnly": False, "sameSite": "Lax"}
            for name, value in cookies.items()
        ])
    page = await context.new_page()
    cdp = await context.new_cdp_session(page)
    network = NetworkCapture()
    for name, handler in (
        ("Network.requestWillBeSent", network.request_will_be_sent),
        ("Network.requestWillBeSentExtraInfo", network.request_extra),
        ("Network.responseReceived", network.response_received),
        ("Network.responseReceivedExtraInfo", network.response_extra),
        ("Network.loadingFinished", network.loading_finished),
        ("Network.loadingFailed", network.loading_failed),
    ):
        cdp.on(name, handler)
    await cdp.send("Network.enable", {"maxTotalBufferSize": 16 * 1024 * 1024,
                                      "maxResourceBufferSize": 4 * 1024 * 1024})
    await cdp.send("Network.setCacheDisabled", {"cacheDisabled": True})
    playwright_responses = []

    def response_seen(response):
        kind = route_kind(response.url, response.request.resource_type)
        if kind == "detail":
            playwright_responses.append(response)

    page.on("response", response_seen)
    row = {"context": label, "work": work, "started_at": stamp(),
           "credential_cookie_names_count": len(cookie_names),
           "session_cookie_present": bool(SESSION_COOKIE_NAMES.intersection(cookie_names)),
           "details": [], "catalogs": [], "network": []}
    try:
        nav = await page.goto("https://www.douyin.com/video/" + work,
                              wait_until="commit", timeout=30000)
        row["page_http"] = nav.status if nav else None
        await page.wait_for_timeout(settle_ms)
        title = await page.title()
        row["verification_title"] = "验证" in title
        row["login_prompt_visible"] = await page.locator("button,[role=button]").evaluate_all(
            "els => els.some(e => { const s=getComputedStyle(e); const r=e.getBoundingClientRect(); "
            "return r.width>0 && r.height>0 && s.visibility!=='hidden' && s.display!=='none' "
            "&& /登录|扫码登录/.test((e.innerText || e.getAttribute('aria-label') || '').trim()); })")
        cookie_state = await context.cookies("https://www.douyin.com/")
        row["session_cookie_present_after_navigation"] = any(
            c.get("name") in SESSION_COOKIE_NAMES for c in cookie_state)
        row["page_user_agent_sha256"] = digest(await page.evaluate("navigator.userAgent"))
        detail = None
        for response in playwright_responses:
            obj = await read_json_response(response)
            candidate = obj.get("aweme_detail") if isinstance(obj, dict) else None
            if (isinstance(candidate, dict) and str(candidate.get("aweme_id")) == work
                    and obj.get("status_code") == 0):
                detail = candidate
                row["details"].append({"http": response.status,
                                       "status_code": safe_int(obj.get("status_code")),
                                       "work_matches": True})
            elif obj is not None:
                row["details"].append({"http": response.status,
                                       "status_code": safe_int(obj.get("status_code")),
                                       "work_matches": False})
        try:
            fetched = await page.evaluate("""async (awemeId) => {
                try {
                    const response = await window.fetch(
                        '/aweme/v1/web/aweme/detail/?aweme_id=' + awemeId
                            + '&aid=392139&device_platform=webapp',
                        {credentials: 'include', cache: 'no-store'});
                    return {status: response.status, body: await response.text()};
                } catch (error) {
                    return {status: null, error: error?.name || 'FetchError'};
                }
            }""", work)
            try:
                fetched_json = json.loads(fetched.get("body") or "")
            except (ValueError, RecursionError):
                fetched_json = None
            fetched_detail = fetched_json.get("aweme_detail") if isinstance(fetched_json, dict) else None
            fetched_matches = (isinstance(fetched_detail, dict)
                               and str(fetched_detail.get("aweme_id")) == work
                               and isinstance(fetched_json, dict) and fetched_json.get("status_code") == 0)
            row["page_fetch_detail"] = {"http": fetched.get("status"),
                                         "status_code": safe_int(fetched_json.get("status_code"))
                                         if isinstance(fetched_json, dict) else None,
                                         "fetch_error": fetched.get("error"),
                                         "work_matches": bool(fetched_matches),
                                         "model_present": bool((fetched_detail or {}).get("video", {}).get("video_model"))
                                         if isinstance(fetched_detail, dict) else False}
            if fetched_matches and (detail is None or row["page_fetch_detail"]["model_present"]):
                detail = fetched_detail
                row["detail_source"] = "page_fetch_aid_392139"
        except Error as error:
            row["page_fetch_detail"] = {"error_type": type(error).__name__}
        if detail is None:
            row["detail_available"] = False
            row["network"] = list(network.events)
            row["ended_at"] = stamp()
            return row
        row.setdefault("detail_source", "natural_page_response")
        video = detail.get("video") if isinstance(detail.get("video"), dict) else {}
        address = video.get("play_addr") if isinstance(video.get("play_addr"), dict) else {}
        vid = address.get("uri")
        model = video.get("video_model")
        if isinstance(model, str):
            try:
                model = json.loads(model)
            except (ValueError, RecursionError):
                model = None
        model = model if isinstance(model, dict) else {}
        row["detail_available"] = True
        row["detail_vid_sha256"] = digest(vid) if isinstance(vid, str) else None
        row["detail_model_present"] = bool(model)
        row["detail_fallback_present"] = bool(flatten_model_url(model))
        row["detail_fallback_sha256"] = digest(flatten_model_url(model)) if flatten_model_url(model) else None
        row["detail_bitrate_rows"] = len(video.get("bit_rate") or []) if isinstance(video.get("bit_rate"), list) else 0
        requests = catalog_urls(model)
        if not vid or not requests:
            row["catalog_error"] = "detail_model_missing_vid_or_fallback"
        else:
            for selector, url in requests.items():
                entry = {"selector": selector, "request": safe_url(url), "started_at": stamp()}
                try:
                    result = await page.evaluate("""async (url) => {
                        try {
                            const response = await window.fetch(url, {credentials: 'include', cache: 'no-store'});
                            const text = await response.text();
                            return {status: response.status, body: text};
                        } catch (error) {
                            return {status: null, fetch_error: error?.name || 'FetchError'};
                        }
                    }""", url)
                    entry["http"] = result.get("status")
                    entry["fetch_error"] = result.get("fetch_error")
                    entry["response"] = catalog_summary(result.get("body"), vid)
                    try:
                        catalog_payload = json.loads(result.get("body") or "")
                    except (ValueError, RecursionError):
                        catalog_payload = None
                    if (isinstance(catalog_payload, dict)
                            and (catalog_payload.get("video_info") or {}).get("data", {}).get("video_id") == vid):
                        entry["official_original_media_check"] = verify_official_originals(
                            catalog_payload, vid,
                            {cookie["name"]: cookie["value"] for cookie in cookie_state}, user_agent)
                except Error as error:
                    entry["browser_error_type"] = type(error).__name__
                entry["ended_at"] = stamp()
                row["catalogs"].append(entry)
            selectors_by_digest = {safe_url(url)["url_sha256"]: selector
                                   for selector, url in requests.items()}
            for event in network.events:
                url_digest = (event.get("request") or {}).get("url_sha256")
                if event.get("route_kind") == "catalog":
                    event["catalog_selector"] = selectors_by_digest.get(url_digest, "natural")
        await page.wait_for_timeout(700)
        row["network"] = list(network.events)
        row["ended_at"] = stamp()
        return row
    except Error as error:
        row["browser_error_type"] = type(error).__name__
        row["network"] = list(network.events)
        row["ended_at"] = stamp()
        return row
    finally:
        await network.read_bodies(cdp)
        row["network"] = list(network.events)
        await context.close()


async def run(output: Path, credential_path: Path, timeout: int):
    if output.exists():
        raise SystemExit("输出文件已存在，请指定新路径")
    credentials = None
    if credential_path.is_file():
        try:
            loaded = json.loads(credential_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            loaded = None
        if (isinstance(loaded, dict) and isinstance(loaded.get("cookies"), dict)
                and isinstance(loaded.get("user_agent"), str)):
            credentials = loaded
    if credentials is None:
        raise SystemExit("凭据文件缺少可用的 Cookie/User-Agent 结构")
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(PROJECT / ".browsers"))
    result = {"created_at": stamp(),
              "mode": "desktop Web; natural page requests plus page-context fetch of official catalogs",
              "works": list(WORKS), "credential_values_saved": False,
              "catalog_method": "video_model fallback_api selectors original/source and unchanged issued URL",
              "observations": []}
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(timeout=20000)
        try:
            for work in WORKS:
                rows = await asyncio.gather(
                    capture_context(browser, "anonymous", work, None,
                                    credentials["user_agent"], timeout),
                    capture_context(browser, "logged_in_cookie_context", work, credentials,
                                    credentials["user_agent"], timeout),
                )
                result["observations"].extend(rows)
                print(work, [(row["context"], row.get("page_http"),
                              [(item.get("selector"), item.get("http"),
                                (item.get("response", {}).get("catalog") or {}).get("row_count"))
                               for item in row.get("catalogs", [])]) for row in rows], flush=True)
        finally:
            await browser.close()
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("x", encoding="utf-8") as stream:
        json.dump(result, stream, ensure_ascii=True, indent=2)
        stream.write("\n")
    print("Saved sanitized capture:", output.resolve(), flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path,
                        default=PROJECT / "docs" / "evidence" / "browser-login-anonymous-catalog-pair-20261119.json")
    parser.add_argument("--credentials", type=Path, default=PROJECT / "credentials.json")
    parser.add_argument("--timeout", type=int, default=15000,
                        help="settle time per page in milliseconds")
    args = parser.parse_args()
    if not 1000 <= args.timeout <= 60000:
        parser.error("--timeout must be between 1000 and 60000")
    asyncio.run(run(args.output, args.credentials, args.timeout))


if __name__ == "__main__":
    main()
