import json
import unittest
from unittest.mock import patch

from original_parser.client import ParseError
from tools.compare_original_sessions import (
    CONTROL, DiagnosticParser, analyze_detail, comparison,
)

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


if __name__ == "__main__":
    unittest.main()
