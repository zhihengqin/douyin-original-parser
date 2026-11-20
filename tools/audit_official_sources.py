"""Audit every video candidate in official detail/model/fplay responses.

Reads only the requested work. Does not consult the original catalog, use an
external parser, or classify a file as original from its size or resolution.
The report contains fingerprints instead of signed URLs or authentication data.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlsplit, urlunsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

from original_parser.client import (DETAIL_URL, MEDIA_HOSTS, OriginalParser, ParseError,
                                    check_url, load_credentials, signed_headers, signed_query)
from original_parser.codec import decode_url
from original_parser.media import inspect_mp4

AUDIT_HOSTS = tuple(dict.fromkeys((*MEDIA_HOSTS, "zjcdn.com")))
EXCLUDED_FIELDS = {"cover", "origin_cover", "cover_original_scale", "gaussian_cover", "dynamic_cover", "big_thumbs",
                   "y_cover", "y_cover_hor", "animated_cover", "audio",
                   "bit_rate_audio", "audio_list", "token_auth"}
ADDRESS_FIELDS = ("main_url", "backup_url", "backup_url_1", "backup_url_2", "backup_url_3")
DETAIL_PROFILES = ("minimal",)
AUDIO_FIELDS = {"audio", "bit_rate_audio", "audio_list"}


def decoded(value):
    if isinstance(value, str) and value.lstrip()[:1] in ("{", "["):
        try:
            return json.loads(value)
        except ValueError:
            pass
    return value


def fingerprint(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def positive_int(value) -> int:
    try:
        return max(0, int(value or 0)) if not isinstance(value, bool) else 0
    except (TypeError, ValueError, OverflowError):
        return 0


def url_identity(url: str) -> str:
    """Merge CDN mirrors of an object; never equate all files of a video VID."""
    part = urlsplit(url)
    query = parse_qs(part.query)
    fid = query.get("file_id", [""])[0]
    if re.fullmatch(r"[a-fA-F0-9]{32}", fid):
        return "file_id:" + fid.lower()
    if "/video/tos/" in part.path:
        return "object:" + fingerprint(part.path.split("/video/tos/", 1)[1].rstrip("/"))
    return "url:" + fingerprint(url)


class CandidateCollector:
    def __init__(self, *, audio: bool = False):
        self.observations: list[dict] = []
        self.nodes = 0
        self.decode_failures = 0
        self.excluded_subtrees = 0
        self.audio = audio
        self.excluded_fields = EXCLUDED_FIELDS - AUDIO_FIELDS if audio else EXCLUDED_FIELDS

    def collect(self, value, origin: str, path: str = "video", inherited=None,
                key_seed: str = "", depth: int = 0):
        if depth > 32 or self.nodes >= 50000:
            raise ValueError("response_structure_budget_exceeded")
        self.nodes += 1
        node = decoded(value)
        if node is not value:
            path += "#json"
        if isinstance(node, list):
            for i, child in enumerate(node):
                self.collect(child, origin, f"{path}[{i}]", inherited, key_seed, depth + 1)
            return
        if not isinstance(node, dict):
            return
        if isinstance(node.get("key_seed"), str):
            key_seed = node["key_seed"]
        meta = dict(inherited or {})
        extra = decoded(node.get("video_extra"))
        if isinstance(extra, dict):
            meta.update(extra)
        meta.update({k: v for k, v in node.items() if not isinstance(v, (dict, list))})
        meta_field = "audio_meta" if self.audio else "video_meta"
        nested_meta = decoded(node.get(meta_field))
        if isinstance(nested_meta, dict):
            meta.update(nested_meta)
        addresses = [(key, node[key]) for key in ADDRESS_FIELDS if node.get(key)]
        if isinstance(node.get("url_list"), list):
            addresses.extend((f"url_list[{i}]", url) for i, url in enumerate(node["url_list"]))
        urls = []
        for key, value in addresses:
            try:
                url = check_url(decode_url(value, key_seed), AUDIT_HOSTS)
            except (ValueError, TypeError, UnicodeError, ParseError):
                self.decode_failures += 1
                continue
            if url not in [entry["url"] for entry in urls]:
                urls.append({"url": url, "path": path + "." + key})
        if urls:
            aliases = {url_identity(entry["url"]) for entry in urls}
            for name in (("file_id", "file_hash", "audio_file_id") if self.audio else ("file_id", "file_hash")):
                val = str(meta.get(name) or "")
                if re.fullmatch(r"[a-fA-F0-9]{32}", val):
                    aliases.add(name + ":" + val.lower())
            safe = {k: meta.get(k) for k in ("quality", "quality_type", "gear_name", "file_id",
                                            "audio_file_id", "file_hash", "size", "data_size", "vwidth", "vheight",
                                            "width", "height", "bitrate", "bit_rate", "codec_type",
                                            "format", "vtype", "encrypt", "spade_a", "encryption_method")
                    if meta.get(k) is not None and not isinstance(meta.get(k), (dict, list))}
            # Encryption data can be opaque key material; keep only its presence.
            for k in ("encrypt", "spade_a", "encryption_method"):
                if k in safe:
                    safe[k] = bool(safe[k])
            self.observations.append({"origin": origin, "path": path, "metadata": safe,
                                      "urls": urls, "aliases": aliases})
        for key, child in node.items():
            if key in self.excluded_fields:
                self.excluded_subtrees += 1
                continue
            if key in ADDRESS_FIELDS or key in ("video_extra", "video_meta"):
                continue
            # Some official media models use url_list={main_url, backup_url}
            # rather than an array. Keep its metadata and inspect that mapping.
            if key == "url_list" and isinstance(child, list):
                continue
            if isinstance(child, (dict, list)) or decoded(child) is not child:
                self.collect(child, origin, path + "." + key, meta, key_seed, depth + 1)

    def candidates(self) -> list[dict]:
        groups = []
        for row in self.observations:
            hits = [group for group in groups if group["aliases"] & row["aliases"]]
            if hits:
                group = hits[0]
                for other in hits[1:]:
                    group["aliases"].update(other["aliases"])
                    group["observations"].extend(other["observations"])
                    groups.remove(other)
            else:
                group = {"aliases": set(), "observations": []}
                groups.append(group)
            group["aliases"].update(row["aliases"])
            group["observations"].append(row)
        return groups


class AuditParser(OriginalParser):
    def __init__(self, *args, max_requests=400, **kwargs):
        super().__init__(*args, **kwargs)
        self.request_count = 0
        self.max_requests = max_requests
        self.stop_reason = None
        send = self.session.send

        def counted_send(request, **options):
            if self.stop_reason:
                raise ParseError("audit_stopped", self.stop_reason)
            if self.request_count >= self.max_requests:
                self.stop_reason = "request_budget_exhausted"
                raise ParseError("audit_budget_exceeded", "audit_request_budget_exceeded")
            self.request_count += 1
            response = send(request, **options)
            if response.status_code in (429, 444):
                self.stop_reason = "upstream_http_" + str(response.status_code)
            return response
        self.session.send = counted_send

    def _get(self, url, *, hosts=AUDIT_HOSTS, headers=None):
        return super()._get(url, hosts=hosts, headers=headers)


def error_summary(exc: Exception) -> dict:
    return {"error_type": type(exc).__name__, "error_code": getattr(exc, "code", None)}


def range_probe(parser: AuditParser, url: str) -> tuple[dict, str | None]:
    with parser._get(url, headers={"Range": "bytes=0-15", "Accept-Encoding": "identity"}) as response:
        part = {"http_status": response.status_code, "mp4": False}
        if response.status_code in (429, 444):
            raise ParseError("audit_stopped", "upstream_http_" + str(response.status_code))
        match = re.fullmatch(r"bytes 0-15/(\d+)", response.headers.get("Content-Range", ""))
        first = response.raw.read(16, decode_content=False)
        if response.status_code == 206 and match and first[4:8] == b"ftyp":
            part.update(mp4=True, actual_size=int(match.group(1)))
            return part, response.url
        return part, None


def media_probe(parser: AuditParser, url: str, size: int, duration: float) -> dict:
    budget = 0

    def read_at(offset, count):
        nonlocal budget
        budget += count
        if budget > 17 * 1024 * 1024:
            raise ValueError("metadata_byte_budget_exceeded")
        with parser._get(url, headers={"Range": f"bytes={offset}-{offset + count - 1}",
                                       "Accept-Encoding": "identity"}) as response:
            if response.status_code != 206 or response.headers.get("Content-Range") != f"bytes {offset}-{offset + count - 1}/{size}":
                raise ValueError("invalid_media_range")
            value = response.raw.read(count, decode_content=False)
            if len(value) != count:
                raise ValueError("truncated_media_range")
            return value
    media = inspect_mp4(read_at, size)
    actual_duration = media.get("duration_seconds") or 0
    media.update(actual_size=size, metadata_bytes_read=budget,
                 duration_matches=bool(duration and abs(duration - actual_duration) <= 1),
                 average_bitrate=round(size * 8 / actual_duration) if actual_duration else None)
    media["verified_complete_mp4"] = bool(media.get("has_video") and media.get("has_audio")
                                         and media["duration_matches"])
    return media


def report_candidate(group: dict, parser: AuditParser | None = None, duration: float = 0,
                     *, audio: bool = False) -> dict:
    observations = group["observations"]
    qualities = sorted({str(row["metadata"]["quality"]).lower() for row in observations
                        if row["metadata"].get("quality")})
    report = {"id": fingerprint("\n".join(sorted(group["aliases"]))),
              "qualities": qualities,
              "media_type": "audio" if audio else "video",
              "explicit_original": False if audio else bool(set(qualities) & {"source", "original"}),
              "observations": [{k: row[k] for k in ("origin", "path", "metadata")} for row in observations],
              "addresses": [], "original_verified": False}
    urls = {}
    for row in observations:
        for entry in row["urls"]:
            urls.setdefault(entry["url"], []).append({"origin": row["origin"], "path": entry["path"]})
    readable = []
    for url, paths in urls.items():
        if parser is not None and parser.stop_reason:
            report["incomplete_reason"] = parser.stop_reason
            break
        address = {"host": urlsplit(url).hostname, "fingerprint": fingerprint(url), "paths": paths}
        if parser is not None and not audio:
            try:
                outcome, final = range_probe(parser, url)
                address.update(outcome)
                if final:
                    readable.append((final, outcome["actual_size"]))
            except Exception as exc:
                address.update(error_summary(exc))
        report["addresses"].append(address)
    if parser is not None and not audio and readable and not parser.stop_reason:
        errors = []
        for final, size in readable:
            if parser.stop_reason:
                report["incomplete_reason"] = parser.stop_reason
                break
            try:
                report["media"] = media_probe(parser, final, size, duration)
                if report["media"]["verified_complete_mp4"]:
                    break
            except Exception as exc:
                errors.append(error_summary(exc))
        if errors:
            report["media_attempt_errors"] = errors
        media = report.get("media") or {}
        declared_sizes = {positive_int(row["metadata"].get("size") or row["metadata"].get("data_size"))
                          for row in observations}
        declared_sizes.discard(0)
        media["declared_size_matches"] = bool(media.get("actual_size") in declared_sizes)
        dimensions = {(positive_int(row["metadata"].get("vwidth") or row["metadata"].get("width")),
                       positive_int(row["metadata"].get("vheight") or row["metadata"].get("height")))
                      for row in observations}
        dimensions = {(width, height) for width, height in dimensions if width and height}
        video_track = next((track for track in media.get("tracks", []) if track.get("type") == "vide"), {})
        media["declared_dimensions_match"] = ((video_track.get("width"), video_track.get("height")) in dimensions)
        encrypted = any(any(row["metadata"].get(k) for k in ("encrypt", "spade_a", "encryption_method"))
                        for row in observations)
        report["original_verified"] = bool(report["explicit_original"] and not encrypted
                                             and media.get("verified_complete_mp4")
                                             and media["declared_size_matches"]
                                             and media["declared_dimensions_match"])
    if parser is not None and parser.stop_reason:
        report["incomplete_reason"] = parser.stop_reason
    if audio:
        report["audio_probe_performed"] = False
    return report


def collect_audio_fields(value, collector: CandidateCollector, origin: str, path: str = "",
                         *, key_seed: str = "", depth: int = 0, budget=None) -> None:
    """Collect only named audio branches into their independent identity space."""
    budget = budget if budget is not None else [0]
    budget[0] += 1
    if depth > 32 or budget[0] > 50000:
        raise ValueError("response_structure_budget_exceeded")
    node = decoded(value)
    if node is not value:
        path += "#json"
    if isinstance(node, dict):
        if isinstance(node.get("key_seed"), str):
            key_seed = node["key_seed"]
        for key, child in node.items():
            child_path = f"{path}.{key}" if path else key
            if key in AUDIO_FIELDS:
                if child is not None:
                    collector.collect(child, origin, child_path, key_seed=key_seed)
            elif key not in EXCLUDED_FIELDS and (isinstance(child, (dict, list)) or decoded(child) is not child):
                collect_audio_fields(child, collector, origin, child_path,
                                     key_seed=key_seed, depth=depth + 1, budget=budget)
    elif isinstance(node, list):
        for index, child in enumerate(node):
            collect_audio_fields(child, collector, origin, f"{path}[{index}]",
                                 key_seed=key_seed, depth=depth + 1, budget=budget)


def validate_detail_identity(detail, work: str) -> dict:
    if not isinstance(detail, dict) or str(detail.get("aweme_id")) != work:
        raise ParseError("identity_mismatch", "detail_aweme_id_mismatch")
    video = detail.get("video") or {}
    if not isinstance(video, dict):
        raise ParseError("detail_unavailable", "invalid_video_structure")
    model = decoded(video.get("video_model"))
    play_addr = video.get("play_addr") or {}
    vid = play_addr.get("uri") if isinstance(play_addr, dict) else None
    if isinstance(model, dict) and vid and model.get("video_id") and model["video_id"] != vid:
        raise ParseError("identity_mismatch", "detail_model_video_id_mismatch")
    return video


def web_pc_params(aweme_id: str, user_agent: str | None) -> dict:
    """Build the fixed Windows PC profile, following Chrome version only."""
    match = re.search(r"Chrome/([0-9.]+)", user_agent or "")
    if not match:
        raise ParseError("unsupported_profile", "web_pc_requires_chrome_user_agent")
    version = match.group(1)
    return {
        "aweme_id": str(aweme_id), "aid": "6383", "device_platform": "webapp",
        "channel": "channel_pc_web", "pc_client_type": "1",
        "version_code": "290100", "version_name": "29.1.0",
        "update_version_code": "170400", "cookie_enabled": "true",
        "screen_width": "1920", "screen_height": "1080",
        "browser_language": "zh-CN", "browser_platform": "Win32",
        "browser_name": "Chrome", "browser_version": version,
        "browser_online": "true", "engine_name": "Blink", "engine_version": version,
        "os_name": "Windows", "os_version": "10", "cpu_core_num": "12",
        "device_memory": "8", "platform": "PC", "downlink": "10",
        "effective_type": "4g", "round_trip_time": "0",
    }


def audit(text: str, parser: AuditParser, *, probe_all=False, app_detail=True, web_pc=False) -> dict:
    work = parser.resolve_id(text)
    report = {"schema_version": 1, "aweme_id": work,
              "created_at": datetime.now(timezone.utc).isoformat(), "catalog_used": False,
              "reference_used": False, "third_party_parser_used": False,
              "coverage": "minimal web and App detail video/audio fields; optional --web-pc detail; issued/original/source fplay for each successful detail's main video_model context",
              "request_count_scope": "requests HTTP attempts including redirects; browser guest initialization excluded",
              "web_pc_enabled": web_pc,
              "web_pc_profile": ("fixed Windows 1920x1080, 12-core, 8-GB profile; Chrome and Blink versions follow the configured User-Agent"
                                 if web_pc else None),
              "audio_scope": "audio, bit_rate_audio and audio_list candidates from returned detail/model/fplay payloads; identity metadata only",
              "audio_probe_performed": False,
              "audio_probe_scope_limit": "--probe-all applies to video candidates only; audio candidates are never fetched or classified as original",
              "routes": [], "candidates": []}
    collector = CandidateCollector()
    audio_collector = CandidateCollector(audio=True)
    detail = None
    detail_contexts = []
    profiles = DETAIL_PROFILES + (("web_pc",) if web_pc else ())
    for profile in profiles:
        if parser.stop_reason:
            break
        try:
            if profile == "minimal":
                current = parser.detail(work)
            else:
                params = web_pc_params(work, parser.user_agent)
                signed = signed_query(params, parser.cookies)
                data = parser._json(DETAIL_URL + "?" + (signed or urlencode(params)),
                                    headers=signed_headers(signed), stage="PC 网页作品详情接口")
                current = data.get("aweme_detail")
                if not isinstance(current, dict) or str(current.get("aweme_id")) != work:
                    raise ParseError("detail_unavailable", "PC detail id missing or mismatched")
            current_video = validate_detail_identity(current, work)
            collector.collect(current_video, "web_detail_" + profile)
            collect_audio_fields(current_video, audio_collector, "web_detail_" + profile, "video")
            detail_contexts.append(("web_detail_" + profile, current_video, {}))
            report["routes"].append({"name": "web_detail_" + profile, "outcome": "received",
                                     "video_tiers": len((current.get("video") or {}).get("bit_rate") or []),
                                     "audio_tiers": sum(len(current_video.get(key) or []) if isinstance(current_video.get(key), list) else int(bool(current_video.get(key)))
                                                        for key in AUDIO_FIELDS)})
            if detail is None:
                detail = current
        except Exception as exc:
            report["routes"].append({"name": "web_detail_" + profile, **error_summary(exc)})
    if app_detail and not parser.stop_reason:
        # Use the same cookie values only on this explicit official API host.
        for name, value in parser.cookies.items():
            parser.session.cookies.set(name, value, domain="api.amemv.com", path="/")
        params = {"aweme_id": work, "aid": "1128", "device_platform": "android",
                  "version_code": "320206", "version_name": "32.2.6", "os": "android",
                  "os_api": "33", "os_version": "13", "device_type": "SM-G988N",
                  "device_brand": "samsung", "channel": "googleplay", "app_name": "aweme"}
        ua = "com.ss.android.ugc.aweme/320206 (Linux; U; Android 13; zh_CN; SM-G988N; Build/TP1A.220624.014)"
        try:
            reply = parser._json("https://api.amemv.com/aweme/v1/aweme/detail/?" + urlencode(params),
                                 headers={"User-Agent": ua})
            app = reply.get("aweme_detail")
            if not isinstance(app, dict) or str(app.get("aweme_id")) != work:
                raise ParseError("detail_unavailable", "missing_or_mismatched_app_detail")
            app_video = validate_detail_identity(app, work)
            collector.collect(app_video, "app_detail")
            collect_audio_fields(app_video, audio_collector, "app_detail", "video")
            detail_contexts.append(("app_detail", app_video, {"User-Agent": ua}))
            report["routes"].append({"name": "app_detail", "outcome": "received"})
            if detail is None:
                detail = app
        except Exception as exc:
            report["routes"].append({"name": "app_detail", **error_summary(exc)})
    video = (detail or {}).get("video") or {}
    contexts = {}
    report["model_contexts"] = []
    for origin, context_video, context_headers in detail_contexts:
        context_report = {"origin": origin}
        report["model_contexts"].append(context_report)
        model = decoded(context_video.get("video_model"))
        if not isinstance(model, dict):
            context_report["outcome"] = "model_missing"
            continue
        model_vid = model.get("video_id")
        if not isinstance(model_vid, str) or not model_vid.strip():
            exc = ParseError("identity_mismatch", "model_video_id_missing")
            context_report.update(outcome="model_rejected", **error_summary(exc))
            report["routes"].append({"name": "fplay_fallback", "context_origins": [origin],
                                     **error_summary(exc)})
            continue
        fallback = model.get("fallback_api")
        fallback = fallback.get("fallback_api") if isinstance(fallback, dict) else fallback
        if isinstance(fallback, str):
            try:
                part = urlsplit(check_url(fallback, ("snssdk.com",)))
            except ParseError as exc:
                context_report.update(outcome="fallback_rejected", **error_summary(exc))
                report["routes"].append({"name": "fplay_fallback", "context_origins": [origin],
                                         **error_summary(exc)})
                continue
        else:
            context_report["outcome"] = "fallback_missing"
            continue
        # VID、完整签发地址和请求头均相同才共用请求，保留所有来源。
        identity = (model_vid, fallback, tuple(sorted(context_headers.items())))
        context_report.update(outcome="queued", fallback_fingerprint=fingerprint(fallback))
        if identity not in contexts:
            contexts[identity] = {"part": part, "origins": [], "reports": [],
                                  "headers": context_headers}
        contexts[identity]["origins"].append(origin)
        contexts[identity]["reports"].append(context_report)
    report["fplay_context_count"] = len(contexts)
    for (model_vid, fallback, _headers), context in contexts.items():
        part = context["part"]
        params = parse_qs(part.query, keep_blank_values=True)
        original = {k: v for k, v in params.items() if k != "logo_type"}
        original.update(force_fids=[base64.b64encode(b"original").decode()], codec_type=["5"])
        source = {k: v for k, v in params.items() if k != "logo_type"}
        source["stream_type"] = ["source"]
        urls = [("fplay_issued", fallback)]
        urls.extend((name, urlunsplit((part.scheme, part.netloc, part.path,
                                      urlencode(query, doseq=True), "")))
                    for name, query in (("fplay_original", original), ("fplay_source", source)))
        outcomes = []
        for name, request_url in urls:
            if parser.stop_reason:
                break
            route = {"name": name, "context_origins": context["origins"],
                     "fallback_fingerprint": fingerprint(fallback)}
            origin = name + "@" + "+".join(context["origins"])
            try:
                reply = (parser._json(request_url, headers=context["headers"])
                         if context["headers"] else parser._json(request_url))
                data = (reply.get("video_info") or {}).get("data") or {}
                route.update(code=reply.get("code"), status=data.get("status"))
                if data.get("video_id") != model_vid or data.get("status") != 10:
                    raise ParseError("identity_mismatch", "fplay_identity_or_status_mismatch")
                collector.collect(data.get("video_list") or [], origin, "video_list", key_seed=data.get("key_seed") or "")
                collect_audio_fields(data, audio_collector, origin, "video_info.data")
                route["outcome"] = "received"
            except Exception as exc:
                route.update(error_summary(exc))
            outcomes.append(route.get("outcome") == "received")
            report["routes"].append(route)
        for item in context["reports"]:
            item["attempted_routes"] = len(outcomes)
            item["outcome"] = ("received" if len(outcomes) == 3 and all(outcomes)
                               else "incomplete" if len(outcomes) < 3 else "route_errors")
    duration = positive_int(video.get("duration")) / 1000
    groups = collector.candidates()
    audio_groups = audio_collector.candidates()
    for group in groups:
        # A later route may stop the transport after earlier routes supplied
        # valid candidates. Retain their metadata even when probing is barred.
        candidate = report_candidate(group, parser if probe_all and not parser.stop_reason else None, duration)
        if parser.stop_reason:
            candidate["incomplete_reason"] = parser.stop_reason
        report["candidates"].append(candidate)
    report.update(request_count=parser.request_count, candidate_count=len(report["candidates"]),
                  audio_candidate_count=len(audio_groups),
                  audio_candidates=[report_candidate(group, audio=True) for group in audio_groups],
                  audio_observation_count=len(audio_collector.observations),
                  visited_audio_nodes=audio_collector.nodes,
                  audio_decode_or_host_rejections=audio_collector.decode_failures,
                  observation_count=len(collector.observations), visited_video_nodes=collector.nodes,
                  decode_or_host_rejections=collector.decode_failures, excluded_subtrees=collector.excluded_subtrees,
                  probe_all=probe_all, original_verified=any(c["original_verified"] for c in report["candidates"]))
    route_errors = [route["name"] for route in report["routes"] if route.get("error_type")]
    report.update(incomplete=bool(parser.stop_reason or route_errors),
                  incomplete_reason=parser.stop_reason or ("route_errors" if route_errors else None),
                  failed_routes=route_errors,
                  audio_discovery_incomplete=bool(parser.stop_reason or route_errors or audio_collector.decode_failures),
                  audio_discovery_incomplete_reason=(parser.stop_reason or ("route_errors" if route_errors else None)
                                                     or ("decode_or_host_rejections" if audio_collector.decode_failures else None)),
                  audio_discovered_candidate_count=len(audio_groups), audio_omitted_candidate_count=0,
                  discovered_candidate_count=len(groups), omitted_candidate_count=len(groups) - len(report["candidates"]))
    report["address_count"] = sum(len(c["addresses"]) for c in report["candidates"])
    report["audio_address_count"] = sum(len(c["addresses"]) for c in report["audio_candidates"])
    return report


def main(argv=None) -> int:
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("link")
    cli.add_argument("--cookie-file", type=Path)
    cli.add_argument("--output", type=Path, required=True)
    cli.add_argument("--probe-all", action="store_true")
    cli.add_argument("--skip-app", action="store_true")
    cli.add_argument("--web-pc", action="store_true",
                     help="also request the fixed-profile Web PC detail endpoint")
    cli.add_argument("--max-requests", type=int, default=400)
    args = cli.parse_args(argv)
    cookies, ua = load_credentials(args.cookie_file) if args.cookie_file else (None, None)
    with AuditParser(cookies=cookies, user_agent=ua, auto_guest=cookies is None,
                     max_requests=args.max_requests, timeout=15,
                     allow_external_asset_recovery=False) as parser:
        result = audit(args.link, parser, probe_all=args.probe_all, app_detail=not args.skip_app,
                       web_pc=args.web_pc)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({k: result[k] for k in ("aweme_id", "request_count", "candidate_count",
                                            "address_count", "original_verified")}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
