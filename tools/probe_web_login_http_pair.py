"""Compare anonymous and saved-cookie desktop-Web requests through the parser HTTP path.

Credential values, signed URLs and media URLs remain in memory. The report keeps
only redacted request metadata, response headers and media identity summaries.
"""
from __future__ import annotations

import argparse
import base64
from datetime import datetime
import hashlib
import json
import re
import sys
import time
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from original_parser.client import OriginalParser, ParseError, load_credentials  # noqa: E402
from original_parser.guest import get_guest  # noqa: E402

WORKS = ("7707954213745085746", "7708052871413075238")
SESSION_NAMES = {"sessionid", "sessionid_ss", "sid_tt"}
SAFE_QUERY_VALUES = {"aid", "codec_type", "force_fids", "stream_type", "vquality",
                     "ratio", "line", "is_play_url", "watermark", "source",
                     "device_platform", "platform", "version_code"}
SENSITIVE = re.compile(r"cookie|auth|token|secret|sign|signature|session|passport|csrf|"
                       r"uifid|verify|fingerprint|device_id|nonce|ticket|sid|fp|trace|logid", re.I)


def digest(value: str | bytes) -> str:
    raw = value if isinstance(value, bytes) else value.encode("utf-8", "replace")
    return hashlib.sha256(raw).hexdigest()


def safe_url(url: str) -> dict:
    parts = urlsplit(url)
    query = parse_qs(parts.query, keep_blank_values=True)
    safe_query = {}
    for name, values in sorted(query.items()):
        safe_query[name] = [value[:128] if name.lower() in SAFE_QUERY_VALUES else
                            {"present": bool(value), "length": len(value), "sha256": digest(value)}
                            for value in values]
    path = re.sub(r"(/video/fplay/1/)[^/]+/[^/]+", r"\1<opaque>", parts.path)
    return {"scheme": parts.scheme, "host": parts.hostname, "path": path,
            "path_sha256": digest(parts.path), "query_keys": sorted(query),
            "query": safe_query, "url_sha256": digest(url)}


def safe_headers(headers) -> dict:
    result = {}
    for name, value in sorted(headers.items(), key=lambda item: item[0].lower()):
        lower = name.lower()
        text = str(value)
        if lower in {"cookie", "set-cookie"}:
            names = sorted({part.split("=", 1)[0].strip() for part in text.split(";") if "=" in part})
            result[lower] = {"present": bool(text), "cookie_names": names}
        elif SENSITIVE.search(lower):
            result[lower] = {"present": bool(text), "length": len(text), "sha256": digest(text)}
        elif lower in {"referer", "origin", "location"}:
            parts = urlsplit(text)
            result[lower] = {"scheme": parts.scheme, "host": parts.hostname,
                             "path": re.sub(r"/video/\d+", "/video/<work>", parts.path)}
        else:
            result[lower] = text[:512]
    return result


def safe_int(value):
    if isinstance(value, bool):
        return None
    try:
        value = int(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return value if abs(value) < 10**16 else None


def catalog_summary(payload: dict, expected_vid: str) -> dict:
    info = payload.get("video_info") if isinstance(payload.get("video_info"), dict) else {}
    data = info.get("data") if isinstance(info.get("data"), dict) else {}
    rows = data.get("video_list")
    rows = list(rows.values()) if isinstance(rows, dict) else rows
    rows = rows if isinstance(rows, list) else []
    summaries = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        meta = row.get("video_meta") if isinstance(row.get("video_meta"), dict) else {}
        merged = {**row, **meta}
        file_hash = merged.get("file_hash")
        summaries.append({
            "quality": merged.get("quality") if isinstance(merged.get("quality"), str) else "unknown",
            "size": safe_int(merged.get("size")),
            "width": safe_int(merged.get("vwidth", merged.get("width"))),
            "height": safe_int(merged.get("vheight", merged.get("height"))),
            "bitrate": safe_int(merged.get("bitrate")),
            "codec_type": safe_int(merged.get("codec_type")),
            "file_hash": file_hash.lower() if isinstance(file_hash, str)
            and re.fullmatch(r"[0-9a-fA-F]{32}", file_hash) else None,
            "file_id_sha256": digest(str(merged.get("file_id"))) if merged.get("file_id") else None,
            "has_media_address": any(bool(row.get(key) or meta.get(key)) for key in
                                      ("main_url", "backup_url_1", "backup_url_2", "backup_url_3",
                                       "backup_url", "play_addr")),
        })
    return {"payload_sha256": digest(json.dumps(payload, sort_keys=True, ensure_ascii=True,
                                                 separators=(",", ":"))),
            "code": safe_int(payload.get("code")),
            "inner_code": safe_int(info.get("code")),
            "status": safe_int(data.get("status")),
            "vid_matches_detail": data.get("video_id") == expected_vid,
            "vid_sha256": digest(data["video_id"]) if isinstance(data.get("video_id"), str) else None,
            "row_count": len(rows), "rows": summaries}


class RequestRecorder:
    def __init__(self, parser: OriginalParser, work_id: str):
        self.parser = parser
        self.work_id = work_id
        self.events = []
        self._send = parser.session.send
        self._json = parser._json
        parser.session.send = self.send
        parser._json = self.json

    def send(self, request, **kwargs):
        started = time.perf_counter()
        route = "detail" if "/aweme/v1/web/aweme/detail/" in urlsplit(request.url).path else (
            "catalog" if "/video/fplay/" in urlsplit(request.url).path else "media_or_other")
        initiator = {"detail": "OriginalParser.detail -> _detail_once -> _json",
                     "catalog": "probe_context -> OriginalParser._json",
                     "media_or_other": "OriginalParser.probe"}[route]
        try:
            response = self._send(request, **kwargs)
        except Exception as error:
            self.events.append({"sequence": len(self.events) + 1, "route": route,
                                "initiator": initiator,
                                "request": safe_url(request.url), "method": request.method,
                                "request_headers": safe_headers(request.headers),
                                "transport_error_type": type(error).__name__,
                                "elapsed_ms": round((time.perf_counter() - started) * 1000, 3)})
            raise
        elapsed_ms = (time.perf_counter() - started) * 1000
        row = {"sequence": len(self.events) + 1, "route": route,
               "initiator": initiator,
               "request": safe_url(request.url), "method": request.method,
               "request_headers": safe_headers(request.headers),
               "response_status": response.status_code,
               "response_headers": safe_headers(response.headers),
               "response_url": safe_url(response.url),
               "headers_elapsed_ms": round(elapsed_ms, 3),
               "content_length_header": safe_int(response.headers.get("Content-Length")),
               "content_type": response.headers.get("Content-Type", "")[:120]}
        self.events.append(row)
        return response

    def json(self, url, *, headers=None, stage="平台接口"):
        started = time.perf_counter()
        index = len(self.events)
        try:
            payload = self._json(url, headers=headers, stage=stage)
        except ParseError as error:
            if len(self.events) > index:
                self.events[-1]["json_stage"] = stage
                self.events[-1]["json_elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
                self.events[-1]["error_code"] = error.code
            raise
        if len(self.events) > index:
            row = self.events[-1]
            row["json_stage"] = stage
            row["json_elapsed_ms"] = round((time.perf_counter() - started) * 1000, 3)
            if stage == "作品详情接口":
                detail = payload.get("aweme_detail") if isinstance(payload.get("aweme_detail"), dict) else {}
                video = detail.get("video") if isinstance(detail.get("video"), dict) else {}
                vid = (video.get("play_addr") or {}).get("uri")
                model = video.get("video_model")
                if isinstance(model, str):
                    try:
                        model = json.loads(model)
                    except (ValueError, RecursionError):
                        model = None
                row["detail"] = {"detail_present": bool(detail),
                                  "status_code": safe_int(payload.get("status_code")),
                                  "aweme_id_matches": str(detail.get("aweme_id") or "") == self.work_id,
                                  "video_id_sha256": digest(vid) if isinstance(vid, str) else None,
                                  "video_model_present": isinstance(model, dict),
                                  "video_model_row_count": len(OriginalParser._video_rows(model))
                                  if isinstance(model, dict) else 0,
                                  "bitrate_row_count": len(video.get("bit_rate") or [])
                                  if isinstance(video.get("bit_rate"), list) else 0}
            elif isinstance(payload, dict):
                # The caller replaces this with the VID-checked form for catalogs.
                row["json_payload_sha256"] = digest(json.dumps(
                    payload, sort_keys=True, ensure_ascii=True, separators=(",", ":")))
        return payload


def probe_context(label: str, works: tuple[str, ...], cookies: dict[str, str], user_agent: str,
                  session_cookie_present: bool) -> dict:
    context = {"context": label, "credential_cookie_count": len(cookies),
               "user_agent_sha256": digest(user_agent),
               "session_cookie_present": session_cookie_present,
               "login_state_verified": False, "works": []}
    for work in works:
        item = {"work": work, "requests": [], "catalogs": []}
        recorder = None
        try:
            with OriginalParser(cookies=cookies, user_agent=user_agent, auto_guest=False,
                                refresh_guest_on_rejection=False, timeout=25,
                                allow_external_asset_recovery=False) as parser:
                recorder = RequestRecorder(parser, work)
                try:
                    detail = parser.detail(work)
                    video = detail.get("video") or {}
                    video_id = str((video.get("play_addr") or {}).get("uri") or "")
                    item["detail_matches"] = str(detail.get("aweme_id")) == work
                    item["video_id_sha256"] = digest(video_id) if video_id else None
                    model = video.get("video_model")
                    if isinstance(model, str):
                        try:
                            model = json.loads(model)
                        except (ValueError, RecursionError):
                            model = None
                    if not isinstance(model, dict):
                        model = {}
                    item["detail_model_present"] = bool(model)
                    item["embedded_model_rows"] = len(OriginalParser._video_rows(model))
                    item["embedded_qualities"] = [str(row.get("quality") or "unknown")[:40]
                                                  for row in OriginalParser._video_rows(model)[:100]]
                    if not video_id:
                        item["error_code"] = "detail_video_id_missing"
                    else:
                        urls = OriginalParser._fallback_source_urls(model) if model else []
                        selectors = ["original", "source"]
                        if urls:
                            issued = OriginalParser._issued_catalog_url(model)
                            url_by_selector = dict(zip(selectors, urls))
                            url_by_selector["issued"] = issued
                            seen = set()
                            for selector, url in url_by_selector.items():
                                if url in seen:
                                    continue
                                seen.add(url)
                                entry = {"selector": selector, "request": safe_url(url)}
                                try:
                                    payload = parser._json(url, stage=f"目录 {selector}")
                                    entry["response"] = catalog_summary(payload, video_id)
                                    candidates = []
                                    try:
                                        _, candidates = parser._source_candidates(payload, video_id)
                                    except ParseError as error:
                                        entry["candidate_error_code"] = error.code
                                    if candidates:
                                        checks = []
                                        for candidate in candidates:
                                            try:
                                                media = parser.probe(candidate)
                                                checks.append({"quality": candidate.get("official_quality"),
                                                               "size": candidate.get("size"),
                                                               "file_hash": candidate.get("file_hash"),
                                                               "media_valid": bool(media.get("ok")),
                                                               "actual_size": media.get("actual_size"),
                                                               "duration_seconds": media.get("duration_seconds"),
                                                               "has_video": media.get("has_video"),
                                                               "has_audio": media.get("has_audio")})
                                                if media.get("ok"):
                                                    break
                                            except ParseError as error:
                                                checks.append({"quality": candidate.get("official_quality"),
                                                               "size": candidate.get("size"),
                                                               "file_hash": candidate.get("file_hash"),
                                                               "media_valid": False,
                                                               "error_code": error.code})
                                        entry["media_checks"] = checks
                                        entry["original_verified"] = any(x.get("media_valid") for x in checks)
                                except ParseError as error:
                                    entry["error_code"] = error.code
                                except Exception as error:
                                    entry["transport_error_type"] = type(error).__name__
                                item["catalogs"].append(entry)
                except ParseError as error:
                    item["error_code"] = error.code
                item["requests"] = recorder.events
        except Exception as error:
            item["error_type"] = type(error).__name__
            if recorder is not None:
                item["requests"] = recorder.events
        context["works"].append(item)
    return context


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", type=Path, default=ROOT / "credentials.json")
    parser.add_argument("--output", type=Path, default=ROOT / "docs" / "evidence" /
                        "web-login-http-pair-20261119.json")
    args = parser.parse_args()
    if args.output.exists():
        parser.error("output already exists; choose a new path")
    saved_cookies, saved_ua = load_credentials(args.credentials)
    anon_cookies, anon_ua = get_guest()
    ua = saved_ua or anon_ua
    anonymous = probe_context("anonymous_guest", WORKS, anon_cookies, ua, False)
    saved = probe_context("saved_cookie_context", WORKS, saved_cookies, ua,
                          bool(SESSION_NAMES.intersection(saved_cookies)))
    report = {"created_at": datetime.now().astimezone().isoformat(timespec="milliseconds"),
              "mode": "same OriginalParser signed Web detail and official fplay requests via HTTP session",
              "credential_values_saved": False, "saved_login_state_verified": False,
              "same_user_agent_for_both_contexts": True,
              "works": list(WORKS), "observations": [anonymous, saved]}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=True, indent=2)
        stream.write("\n")
    for observation in report["observations"]:
        print(observation["context"], [
            (item["work"], item.get("detail_matches"), item.get("error_code"),
             [(catalog.get("selector"),
               (catalog.get("response") or {}).get("row_count"),
               catalog.get("original_verified"), catalog.get("error_code"))
              for catalog in item.get("catalogs", [])])
            for item in observation["works"]], flush=True)
    print("Saved sanitized report:", args.output.resolve(), flush=True)


if __name__ == "__main__":
    main()
