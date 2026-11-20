"""Capture non-pausing breakpoints in the current parser without catalog access."""

from __future__ import annotations

import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import dis
import hashlib
import json
import math
from pathlib import Path
import sys
from unittest.mock import patch
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from original_parser.client import OriginalParser, ParseError, load_credentials, resolve_id_local


QUALITIES = frozenset({"original", "source", "normal", "low", "high", "adapt",
                      "adapt_low", "adapt_lowest", "adapt_lower", "adapt_high", "conflicting"})
EVIDENCE = frozenset({"official_quality", "official_play_default", "official_play_hash"})
FIELDS = ("size", "size_bytes", "width", "height", "vwidth", "vheight", "bitrate",
          "bit_rate", "duration_seconds", "video_duration", "status", "code")


def number(value):
    if type(value) is int or (type(value) is float and math.isfinite(value)):
        return value
    return None


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=True,
                                     separators=(",", ":")).encode()).hexdigest()


def row_summary(row):
    summary = {key: number(row[key]) for key in FIELDS if key in row}
    for key in ("quality", "official_quality"):
        if key in row:
            value = row[key]
            summary[key] = value if isinstance(value, str) and value in QUALITIES else "other"
    value = row.get("source_evidence")
    if isinstance(value, str) and value in EVIDENCE:
        summary["source_evidence"] = value
    if "vtype" in row:
        summary["format"] = "mp4" if row["vtype"] == "mp4" else "other"
    summary["encrypted"] = any(bool(row.get(key)) for key in
                               ("encrypt", "spade_a", "encryption_method"))
    summary["address_fields_present"] = sum(bool(row.get(key)) for key in
        ("main_url", "backup_url_1", "backup_url_2", "backup_url_3", "backup_url", "url"))
    if isinstance(row.get("urls"), list):
        summary["decoded_address_count"] = len(row["urls"])
    if row.get("file_id") or row.get("file_hash"):
        summary["file_identity_sha256"] = digest([row.get("file_id"), row.get("file_hash")])
    return summary


def model_summary(model):
    return {"video_identity_sha256": digest(model.get("video_id")),
            "status": number(model.get("status")),
            "rows": [row_summary(row) for row in OriginalParser._video_rows(model)]}


def payload_summary(payload):
    if not isinstance(payload, dict):
        return {"object_returned": False}
    summary = {"payload_sha256": digest(payload), "code": number(payload.get("code"))}
    detail = payload.get("aweme_detail", payload)
    if isinstance(detail, dict) and isinstance(detail.get("video"), dict):
        summary["work_identity_sha256"] = digest(detail.get("aweme_id"))
        model = detail["video"].get("video_model")
        if isinstance(model, str):
            try:
                model = json.loads(model)
            except (ValueError, RecursionError):
                model = None
        if isinstance(model, dict):
            summary["model"] = model_summary(model)
    info = payload.get("video_info")
    if isinstance(info, dict):
        summary["video_info_code"] = number(info.get("code"))
        if isinstance(info.get("data"), dict):
            summary["model"] = model_summary(info["data"])
    return summary


def error_summary(error):
    # Exception messages can contain requests URLs, including their signatures.
    code = getattr(error, "code", None)
    known = {"source_unavailable", "identity_mismatch", "probe_failed", "network_error",
             "network_tls_error", "upstream_error", "upstream_forbidden", "upstream_rate_limited",
             "upstream_empty_response", "upstream_non_json", "credentials_required",
             "credentials_rejected", "detail_unavailable", "dependency_missing", "capture_budget"}
    return {"error_type": type(error).__name__ if isinstance(error, (ParseError, ValueError,
            OSError, RuntimeError)) else "Exception",
            "error_code": code if isinstance(code, str) and code in known else "other"}


def endpoint(url):
    parsed = urlsplit(url)
    if parsed.hostname == "www.douyin.com":
        if parsed.path == "/aweme/v1/web/aweme/detail/":
            return "detail"
        if parsed.path == "/aweme/v1/play/":
            return "play"
    host = parsed.hostname or ""
    if (host == "snssdk.com" or host.endswith(".snssdk.com")) and parsed.path.startswith("/video/fplay/"):
        return "fplay"
    return "media_or_other"


class BreakpointCapture:
    METHODS = ("_json", "detail", "_source_candidates", "_play_default_candidate", "probe", "parse")

    def __init__(self, directory):
        self.events = []
        self.codes = {getattr(OriginalParser, name).__code__: name for name in self.METHODS}
        self.stream = (directory / "events.jsonl").open("x", encoding="utf-8")
        self.parser = None

    def emit(self, event, **values):
        row = {"sequence": len(self.events) + 1, "event": event, **values}
        self.events.append(row)
        self.stream.write(json.dumps(row, ensure_ascii=True) + "\n")
        self.stream.flush()

    def trace(self, frame, event, arg):
        method = self.codes.get(frame.f_code)
        if method is None or frame.f_locals.get("self") is not self.parser:
            return None
        coordinate = {"method": method, "file": "original_parser/client.py", "line": frame.f_lineno}
        if event == "call":
            values = {}
            if method == "_source_candidates":
                values = {"before": payload_summary(frame.f_locals["payload"]),
                          "allow_missing_urls": frame.f_locals["allow_missing_urls"]}
            elif method == "probe":
                values = {"candidate": row_summary(frame.f_locals["candidate"])}
            self.emit("breakpoint_call", **coordinate, **values)
        elif event == "exception":
            state = {}
            if method == "_source_candidates":
                state = {"selector_state": {key: number(frame.f_locals.get(key))
                         for key in ("source_count", "normal_count")},
                         "candidate_count": len(frame.f_locals.get("candidates", []))}
            self.emit("breakpoint_exception", **coordinate, **error_summary(arg[1]), **state)
        elif event == "return":
            returning = dis.opname[frame.f_code.co_code[frame.f_lasti]].startswith("RETURN_")
            if not returning:
                # CPython also emits return(None) when an exception unwinds a frame.
                self.emit("breakpoint_unwind", **coordinate)
            elif method in ("_json", "detail"):
                self.emit("breakpoint_return", **coordinate, snapshot=payload_summary(arg))
            elif method == "_source_candidates":
                self.emit("breakpoint_return", **coordinate,
                          candidates=[row_summary(row) for row in arg[1]])
            elif method == "parse":
                self.emit("breakpoint_return", **coordinate, selected=row_summary(arg["data"]),
                          probe_ok=bool((arg["data"].get("probe") or {}).get("ok")))
            elif method == "probe":
                self.emit("breakpoint_return", **coordinate, probe={
                    key: number(arg.get(key)) for key in ("actual_size", "duration_seconds")},
                    has_video=bool(arg.get("has_video")), has_audio=bool(arg.get("has_audio")))
            else:
                self.emit("breakpoint_return", **coordinate,
                          candidate=row_summary(arg) if isinstance(arg, dict) else None)
        return self.trace

    @contextmanager
    def installed(self, parser):
        if sys.gettrace() is not None:
            raise RuntimeError("an_existing_debugger_is_active")
        self.parser = parser
        sys.settrace(self.trace)
        try:
            yield
        finally:
            sys.settrace(None)
            self.parser = None

    def close(self):
        self.stream.close()


class CaptureParser(OriginalParser):
    def __init__(self, capture, *, max_requests=24, **kwargs):
        super().__init__(**kwargs)
        self.capture = capture
        self.request_count = 0
        self.stop = False
        send = self.session.send

        def captured_send(request, **options):
            if self.stop or self.request_count >= max_requests:
                raise ParseError("capture_budget", "capture_request_budget_exhausted_or_upstream_stopped")
            self.request_count += 1
            request_number = self.request_count
            route = endpoint(request.url)
            capture.emit("http_request", request_number=request_number, endpoint=route)
            try:
                response = send(request, **options)
            except Exception as exc:
                capture.emit("http_error", request_number=request_number, **error_summary(exc))
                raise
            capture.emit("http_response", request_number=request_number, endpoint=route,
                         status=response.status_code)
            if response.status_code in (429, 444):
                self.stop = True
            return response

        self.session.send = captured_send

    def _catalog_original_candidate(self, detail, video_id):
        self.capture.emit("catalog_skipped")
        return None


def run_capture(work, directory, *, cookie_file=None, timeout=20):
    capture = BreakpointCapture(directory)
    outcome = {"status": "inconclusive"}
    requests_count = 0
    try:
        cookies, user_agent = load_credentials(cookie_file) if cookie_file else (None, None)
        with CaptureParser(capture, cookies=cookies, user_agent=user_agent,
                           auto_guest=cookie_file is None, timeout=timeout,
                           refresh_guest_on_rejection=False,
                           allow_external_asset_recovery=False) as parser:
            try:
                # Keep a real successful parse from updating the production catalog.
                with patch("original_parser.client._remember_original_record", return_value=None), \
                        capture.installed(parser):
                    result = parser.parse(work)
                outcome = {"status": "selected", "selected": row_summary(result["data"]),
                           "probe_ok": bool((result["data"].get("probe") or {}).get("ok"))}
            finally:
                requests_count = parser.request_count
    except Exception as exc:
        outcome = {"status": "failed", **error_summary(exc)}
    finally:
        capture.close()
    report = {"created_at": datetime.now(timezone.utc).isoformat(), "work_id": work,
              "capture_mode": "non_pausing_python_breakpoints", "catalog_read": False,
              "catalog_write": False, "parser_http_requests": requests_count,
              "guest_initialization_requests_included": False,
              "credential_mode": "provided_file" if cookie_file else "auto_guest",
              "outcome": outcome, "events": capture.events}
    with (directory / "report.json").open("x", encoding="utf-8") as stream:
        json.dump(report, stream, ensure_ascii=True, indent=2)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work")
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cookie-file", type=Path)
    args = parser.parse_args(argv)
    work, _ = resolve_id_local(args.work)
    if not work:
        parser.error("a work ID or full video link is required")
    args.out.mkdir(parents=True, exist_ok=False)
    report = run_capture(work, args.out, cookie_file=args.cookie_file)
    print(json.dumps({"work_id": work, "outcome": report["outcome"],
                      "parser_http_requests": report["parser_http_requests"],
                      "breakpoint_events": len(report["events"])}, ensure_ascii=True))
    return 0 if report["outcome"]["status"] == "selected" else 2


if __name__ == "__main__":
    raise SystemExit(main())
