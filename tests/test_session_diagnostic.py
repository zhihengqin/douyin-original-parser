import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from original_parser.client import ParseError
from tools.compare_original_sessions import (
    CONTROL, DiagnosticParser, analyze_detail, comparison,
)
from tools import capture_login_cookies

WORK = "7707196543073275177"
VID = "v02033g10000dbqncrvog65l6dmpd7rg"
SECRET = "private-cookie-token-and-signed-url"


def detail():
    return {"aweme_id": WORK, "video": {
        "play_addr": {"uri": VID},
        "video_model": json.dumps({"video_id": VID, "fallback_api": {"fallback_api":
            f"https://vas-lf-x.snssdk.com/video/fplay/1/{'a' * 32}/{VID}?aid=392139&token={SECRET}"}}),
    }}


def normal_payload():
    return {"code": 0, "video_info": {"code": 0, "data": {
        "status": 10, "video_id": VID, "key_seed": SECRET, "status_msg": SECRET,
        "video_list": {"video_1": {"quality": "normal", "size": 57651328,
            "main_url": "https://example.invalid/?token=" + SECRET,
            "file_id": "observed-file-id", "file_hash": "a" * 32}},
    }}}


def phase(available=False, availability="valid_directory_without_original", session=True):
    return [{"work": CONTROL, "original_verified": True}, {
        "work": WORK, "detail_matches": True, "original_verified": available,
        "availability": "verified_original" if available else availability,
        "session_cookie_present": session,
    }]


class SessionDiagnosticTests(unittest.TestCase):
    def test_real_selector_flow_reports_two_normal_directories_without_secrets_or_catalog(self):
        with patch.object(DiagnosticParser, "_json", return_value=normal_payload()), \
                patch("original_parser.client._read_original_records", side_effect=AssertionError("catalog read")):
            result = analyze_detail(WORK, detail(), {"sessionid": SECRET}, "test")
        self.assertFalse(result["original_verified"])
        self.assertEqual(result["availability"], "valid_directory_without_original")
        self.assertEqual(len(result["directories"]), 2)
        text = json.dumps(result)
        self.assertNotIn(SECRET, text)
        self.assertNotIn("https://", text)

    def test_later_candidate_can_pass_and_probe_exception_text_is_not_saved(self):
        candidate = {"official_quality": "original", "size": 123, "width": 720, "height": 1280,
                     "url": "https://example.invalid/?token=" + SECRET, "urls": [SECRET]}
        probe = {"ok": True, "actual_size": 123, "has_video": True, "has_audio": True}
        with patch.object(DiagnosticParser, "source_streams", return_value=({}, [dict(candidate), dict(candidate)])), \
                patch.object(DiagnosticParser, "probe", side_effect=[ParseError("probe_failed", SECRET), probe]):
            result = analyze_detail(WORK, detail(), {}, "test")
        self.assertTrue(result["original_verified"])
        self.assertNotIn(SECRET, json.dumps(result))

    def test_missing_source_url_records_each_requested_directory_only_once(self):
        response = normal_payload()
        data = response["video_info"]["data"]
        data["video_duration"] = 2
        data["video_list"]["video_1"].update(
            quality="original", main_url="", vtype="mp4", vwidth=720, vheight=1280)
        with patch.object(DiagnosticParser, "_json", return_value=response), \
                patch.object(DiagnosticParser, "_dispatch_official_original", return_value=None), \
                patch("original_parser.client._read_original_records", side_effect=AssertionError("catalog read")):
            result = analyze_detail(WORK, detail(), {}, "test")
        self.assertEqual(result["error_code"], "source_unavailable")
        self.assertEqual([row["selector"] for row in result["directories"]], ["original", "source"])
        self.assertEqual(result["availability"], "inconclusive")
        self.assertNotIn(SECRET, json.dumps(result))

    def test_inline_directory_has_its_own_label_and_keeps_selector_comparison(self):
        response = normal_payload()
        work = detail()
        model = json.loads(work["video"]["video_model"])
        model.update(status=10, video_list=[{"video_meta": {"quality": "normal", "size": 123}}])
        work["video"]["video_model"] = json.dumps(model)
        with patch.object(DiagnosticParser, "_json", return_value=response), \
                patch("original_parser.client._read_original_records", side_effect=AssertionError("catalog read")):
            result = analyze_detail(WORK, work, {}, "test")
        self.assertEqual([row["selector"] for row in result["directories"]], ["inline", "original", "source"])
        self.assertEqual(result["directories"][0]["rows"][0]["quality"], "normal")
        self.assertEqual(result["availability"], "valid_directory_without_original")

    def test_unusable_inline_original_is_not_reported_as_original_absent(self):
        work = detail()
        model = json.loads(work["video"]["video_model"])
        model.update(status=10, video_duration=2, video_list=[{"video_meta": {
            "quality": "original", "size": 123, "vtype": "mp4", "vwidth": 720, "vheight": 1280}}])
        work["video"]["video_model"] = json.dumps(model)
        with patch.object(DiagnosticParser, "_json", return_value=normal_payload()), \
                patch("original_parser.client._read_original_records", side_effect=AssertionError("catalog read")):
            result = analyze_detail(WORK, work, {}, "test")
        self.assertEqual(result["error_code"], "source_unavailable")
        self.assertEqual(result["availability"], "inconclusive")

    def test_all_candidate_probe_failures_remain_inconclusive(self):
        with patch.object(DiagnosticParser, "source_streams", return_value=({}, [{}])), \
                patch.object(DiagnosticParser, "probe", side_effect=ParseError("probe_failed", SECRET)):
            result = analyze_detail(WORK, detail(), {}, "test")
        self.assertEqual(result["availability"], "inconclusive")
        self.assertEqual(result["error_code"], "probe_failed")
        self.assertNotIn(SECRET, json.dumps(result))

    def test_wrong_model_identity_is_rejected_before_request(self):
        wrong = detail()
        wrong["video"]["play_addr"]["uri"] = "v-another-video"
        with patch.object(DiagnosticParser, "_json", side_effect=AssertionError("network request")):
            result = analyze_detail(WORK, wrong, {}, "test")
        self.assertEqual(result["error_code"], "identity_mismatch")
        self.assertFalse(result["original_verified"])

    def test_target_network_failure_does_not_establish_login_effect(self):
        phases = {"anonymous_before": phase(availability="inconclusive"),
                  "session_after_login": phase(True), "anonymous_after": phase()}
        result = comparison(phases, [WORK])
        self.assertTrue(result["all_control_probes_passed"])
        self.assertEqual(result["targets"][0]["interpretation"], "inconclusive")

    def test_three_valid_phases_distinguish_session_difference_and_no_original(self):
        phases = {"anonymous_before": phase(), "session_after_login": phase(True), "anonymous_after": phase()}
        self.assertEqual(comparison(phases, [WORK])["targets"][0]["interpretation"],
                         "original_only_in_session_after_login")
        phases["session_after_login"] = phase()
        self.assertEqual(comparison(phases, [WORK])["targets"][0]["interpretation"],
                         "no_original_in_tested_sessions")
        phases["anonymous_before"][0]["original_verified"] = False
        self.assertEqual(comparison(phases, [WORK])["targets"][0]["interpretation"], "inconclusive")

    def test_missing_or_expired_session_does_not_establish_login_effect(self):
        phases = {"anonymous_before": phase(), "session_after_login": phase(True, session=False),
                  "anonymous_after": phase()}
        self.assertEqual(comparison(phases, [WORK])["targets"][0]["interpretation"], "inconclusive")


class LoginCaptureTests(unittest.TestCase):
    def test_capture_preserves_new_session_fields_and_creates_parent_directory(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch("playwright.sync_api.sync_playwright") as factory, \
                patch("sys.stdout", new_callable=io.StringIO) as stdout:
            output = Path(directory) / "new" / "session.json"
            browser = factory.return_value.__enter__.return_value.chromium.launch.return_value
            context = browser.new_context.return_value
            context.cookies.return_value = [{"name": "sessionid", "value": SECRET},
                                            {"name": "sid_guard", "value": "new-field-value"}]
            self.assertEqual(capture_login_cookies.main(["capture", str(output), "1"]), 0)
            data = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(data["cookies"], {"sessionid": SECRET, "sid_guard": "new-field-value"})
            context.cookies.assert_called_once_with("https://www.douyin.com/")
            self.assertNotIn(SECRET, stdout.getvalue())
            self.assertNotIn("new-field-value", stdout.getvalue())
            browser.close.assert_called_once()

    def test_existing_credentials_are_not_overwritten_or_browser_launched(self):
        with tempfile.TemporaryDirectory() as directory, \
                patch("playwright.sync_api.sync_playwright") as factory, \
                patch("sys.stdout", new_callable=io.StringIO):
            output = Path(directory) / "session.json"
            output.write_text("keep-existing", encoding="utf-8")
            self.assertEqual(capture_login_cookies.main(["capture", str(output)]), 2)
            self.assertEqual(output.read_text(encoding="utf-8"), "keep-existing")
            factory.assert_not_called()


if __name__ == "__main__":
    unittest.main()
