import copy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

from original_parser import client
from original_parser.client import OriginalParser, ParseError
from tools.capture_parser_breakpoints import (
    BreakpointCapture, CaptureParser, error_summary, payload_summary, run_capture,
)


WORK = "7700000000000000001"
VIDEO = "synthetic-video-id"


def source_payload(quality="original"):
    return {"code": 0, "video_info": {"code": 0, "data": {
        "status": 10, "video_id": VIDEO, "video_duration": 2.0,
        "video_list": [{"quality": quality, "vtype": "mp4", "vwidth": 640,
                        "vheight": 360, "size": 1000, "bitrate": 4000,
                        "main_url": "https://v1.douyinvod.com/synthetic.mp4?signature=private"}],
    }}}


def detail_for(payload):
    return {"aweme_id": WORK, "video": {
        "duration": 2000, "play_addr": {"uri": VIDEO},
        "video_model": json.dumps(payload["video_info"]["data"]),
    }}


class ParserBreakpointCaptureTests(unittest.TestCase):
    def setUp(self):
        blocker = patch("requests.sessions.Session.send",
                        side_effect=AssertionError("offline tests must not send HTTP"))
        self.blocked_send = blocker.start()
        self.addCleanup(blocker.stop)

    def test_real_selector_is_unchanged_and_records_before_and_after(self):
        payload = source_payload()
        original = copy.deepcopy(payload)
        with tempfile.TemporaryDirectory() as folder, OriginalParser(auto_guest=False) as parser:
            expected = parser._source_candidates(payload, VIDEO)
            capture = BreakpointCapture(Path(folder))
            try:
                with capture.installed(parser):
                    actual = parser._source_candidates(payload, VIDEO)
            finally:
                capture.close()
            self.assertEqual(actual, expected)
            self.assertEqual(payload, original)
            before = next(row for row in capture.events if row["event"] == "breakpoint_call")
            after = next(row for row in capture.events if row["event"] == "breakpoint_return")
            self.assertEqual(before["before"]["model"]["rows"][0]["size"], 1000)
            self.assertEqual(after["candidates"][0]["size"], 1000)
            self.assertEqual(after["candidates"][0]["official_quality"], "original")
            self.assertNotIn("signature=private", json.dumps(capture.events))
            self.assertIsNone(sys.gettrace())
        self.blocked_send.assert_not_called()

    def test_source_unavailable_is_unwinding_not_an_empty_success(self):
        with tempfile.TemporaryDirectory() as folder, OriginalParser(auto_guest=False) as parser:
            capture = BreakpointCapture(Path(folder))
            try:
                with self.assertRaises(ParseError) as caught, capture.installed(parser):
                    parser._source_candidates(source_payload("normal"), VIDEO)
            finally:
                capture.close()
            self.assertEqual(caught.exception.code, "source_unavailable")
            events = [row["event"] for row in capture.events]
            self.assertIn("breakpoint_exception", events)
            self.assertIn("breakpoint_unwind", events)
            self.assertNotIn("breakpoint_return", events)
            self.assertIsNone(sys.gettrace())

    def test_public_summaries_exclude_nested_fields_and_exception_messages(self):
        canary = "DO_NOT_EMIT_PRIVATE_CAPTURE_CANARY"
        payload = source_payload()
        model = payload["video_info"]["data"]
        model[canary] = {"cookie": canary, "authorization": canary}
        row = model["video_list"][0]
        row.update({canary: canary, "file_hash": canary, "main_url": canary,
                    "size": canary, "vwidth": canary})
        detail = detail_for(payload)
        detail[canary] = {canary: canary}
        with tempfile.TemporaryDirectory() as folder, OriginalParser(auto_guest=False) as parser:
            capture = BreakpointCapture(Path(folder))
            try:
                with self.assertRaises(ParseError), capture.installed(parser):
                    parser._source_candidates(payload, VIDEO)
            finally:
                capture.close()
            public = json.dumps({"detail": payload_summary(detail), "events": capture.events,
                                 "error": error_summary(ParseError(canary, canary)),
                                 "value_error": error_summary(ValueError(canary))})
            self.assertNotIn(canary, public)
            self.assertIn('"error_code": "source_unavailable"', public)

    def test_runner_bypasses_default_catalog_and_restores_after_failure(self):
        detail = detail_for(source_payload("normal"))
        saved_remember = client._remember_original_record
        with tempfile.TemporaryDirectory() as folder, \
                patch.dict("os.environ", {"DOUYIN_ALLOW_EXTERNAL_ASSET_RECOVERY": "1"}), \
                patch.object(CaptureParser, "detail", return_value=detail), \
                patch.object(CaptureParser, "_fallback_source_urls", return_value=[]), \
                patch.object(CaptureParser, "_play_default_candidate", return_value=None), \
                patch.object(OriginalParser, "_catalog_original_candidate",
                             side_effect=AssertionError("production catalog read")) as catalog, \
                patch.object(client, "_read_original_records",
                             side_effect=AssertionError("metadata read")) as records:
            report = run_capture(WORK, Path(folder))
            self.assertEqual(report["outcome"]["error_code"], "source_unavailable")
            self.assertIn("catalog_skipped", [row["event"] for row in report["events"]])
            self.assertFalse(report["catalog_read"])
            self.assertFalse(report["catalog_write"])
            catalog.assert_not_called()
            records.assert_not_called()
            self.assertIsNone(sys.gettrace())
            self.assertIs(client._remember_original_record, saved_remember)
        self.blocked_send.assert_not_called()

    def test_successful_parse_does_not_write_catalog_and_restores_patches(self):
        detail = detail_for(source_payload())
        with tempfile.TemporaryDirectory() as folder, \
                patch.object(CaptureParser, "detail", return_value=detail), \
                patch.object(CaptureParser, "probe", return_value={
                    "ok": True, "duration_seconds": 2.0,
                    "has_video": True, "has_audio": True}), \
                patch.object(client, "_remember_original_record",
                             side_effect=AssertionError("production catalog write")) as remember:
            report = run_capture(WORK, Path(folder))
            self.assertEqual(report["outcome"]["status"], "selected")
            self.assertTrue(report["outcome"]["probe_ok"])
            self.assertIsNone(sys.gettrace())
            self.assertIs(client._remember_original_record, remember)
            remember.assert_not_called()
            self.assertNotIn("signature=private", (Path(folder) / "report.json").read_text())
        self.blocked_send.assert_not_called()

    def test_existing_debugger_is_preserved(self):
        def existing_trace(frame, event, arg):
            return existing_trace

        original_trace = sys.gettrace()
        with tempfile.TemporaryDirectory() as folder, OriginalParser(auto_guest=False) as parser:
            capture = BreakpointCapture(Path(folder))
            try:
                sys.settrace(existing_trace)
                with self.assertRaisesRegex(RuntimeError, "existing_debugger"):
                    with capture.installed(parser):
                        self.fail("capture must not replace an existing debugger")
                self.assertIs(sys.gettrace(), existing_trace)
            finally:
                sys.settrace(original_trace)
                capture.close()

    def test_default_no_candidate_is_a_normal_return(self):
        with tempfile.TemporaryDirectory() as folder, OriginalParser(auto_guest=False) as parser:
            capture = BreakpointCapture(Path(folder))
            try:
                with capture.installed(parser):
                    result = parser._play_default_candidate({"video": {}}, VIDEO)
            finally:
                capture.close()
            self.assertIsNone(result)
            self.assertIn("breakpoint_return", [row["event"] for row in capture.events])
            self.assertNotIn("breakpoint_unwind", [row["event"] for row in capture.events])

    def test_default_exception_is_unwinding_not_a_normal_none(self):
        detail = {"video": {"duration": 2000, "play_addr": {"data_size": 500}}}
        with tempfile.TemporaryDirectory() as folder, OriginalParser(auto_guest=False) as parser:
            capture = BreakpointCapture(Path(folder))
            try:
                with patch.object(parser, "_a_bogus_query", side_effect=RuntimeError("private")), \
                        self.assertRaises(RuntimeError), capture.installed(parser):
                    parser._play_default_candidate(detail, VIDEO)
            finally:
                capture.close()
            self.assertIn("breakpoint_unwind", [row["event"] for row in capture.events])
            self.assertNotIn("breakpoint_return", [row["event"] for row in capture.events])


if __name__ == "__main__":
    unittest.main()
