import io
import json
import unittest
from unittest.mock import patch

from original_parser.client import OriginalParser, ParseError
from tools.probe_additional_repo_routes import (
    additional_routes, inspect_address, inspect_new_detail, legacy_detail,
)

WORK = "7707993970332290314"
VID = "v28033gi0000dbs4nevog65jrl6u1s10"
SECRET = "anonymous-cookie-secret"


class Raw(io.BytesIO):
    def read(self, count=-1, **_):
        return super().read(count)


class Response:
    def __init__(self, payload=None):
        self.status_code = 200
        self.raw = Raw(json.dumps(payload).encode())
        self.headers = {}
        self.url = "https://v3.douyinvod.com/file?token=" + SECRET

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.raw.close()

    def iter_content(self, count):
        while chunk := self.raw.read(count):
            yield chunk


class AdditionalRepoRouteTests(unittest.TestCase):
    def test_legacy_detail_requires_matching_work_and_no_platform_error(self):
        detail = {"aweme_id": WORK, "video": {"play_addr": {"uri": VID}}}
        cases = (({"status_code": 0, "item_list": [{**detail, "aweme_id": "123"}]}, False),
                 ({"status_code": 11110, "item_list": [detail]}, False),
                 ({"status_code": 0, "item_list": [detail]}, True))
        for payload, accepted in cases:
            with self.subTest(accepted=accepted, code=payload["status_code"]), \
                    OriginalParser(auto_guest=False) as parser, \
                    patch.object(parser, "_get", return_value=Response(payload)):
                observed, report = legacy_detail(parser, WORK, app_api=False)
            self.assertEqual(observed is not None, accepted)
            self.assertFalse(report["original_verified"])

    def test_observed_media_stays_unconfirmed_after_valid_metadata(self):
        response = Response()
        response.status_code = 206
        response.raw = Raw(b"x")
        response.headers = {"Content-Range": "bytes 0-0/30"}
        metadata = {"actual_size": 30, "media": {"has_audio": True, "has_video": True}}
        with OriginalParser(auto_guest=False) as parser, \
                patch.object(parser, "_get", return_value=response), \
                patch("tools.probe_additional_repo_routes.inspect_identity", return_value=metadata):
            result = inspect_address(parser, response.url)
        self.assertFalse(result["original_verified"])
        self.assertEqual(result["outcome"], "play_candidate_identity_unconfirmed")
        self.assertNotIn(SECRET, json.dumps(result))

    def test_share_details_are_checked_before_media_requests_and_deduplicated(self):
        address = {"url_list": ["https://www.douyin.com/aweme/v1/playwm/?token=" + SECRET]}
        detail = {"aweme_id": WORK, "video": {"play_addr": {"uri": VID, **address},
                                               "download_addr": address}}
        seen = set()
        with OriginalParser(auto_guest=False) as parser, \
                patch("tools.probe_additional_repo_routes.inspect_address", return_value={}) as inspect:
            with self.assertRaises(ParseError):
                inspect_new_detail(parser, {**detail, "aweme_id": "123"}, WORK, {}, seen)
            inspect.assert_not_called()
            report = {}
            inspect_new_detail(parser, detail, WORK, report, seen)
            inspect_new_detail(parser, detail, WORK, {}, seen)
        inspect.assert_called_once()
        self.assertIn("/play/?", inspect.call_args.args[1])
        self.assertNotIn(SECRET, json.dumps(report))

    def test_catchsnap_cookie_retry_uses_only_anonymous_state_and_is_bounded(self):
        detail = {"aweme_id": WORK, "video": {"play_addr": {"uri": VID}}}
        calls = []

        def share(parser, work, **kwargs):
            calls.append(kwargs)
            if len(calls) == 4:
                parser.session.cookies.set("share_nonce", "new-anonymous-nonce", domain=".iesdouyin.com")
                parser.session.cookies.set("host_nonce", "host-anonymous-nonce", domain="www.iesdouyin.com")
            result = {"route": "mobile_share_ssr", "original_verified": False}
            return (detail if len(calls) == 5 else None), result

        with OriginalParser(auto_guest=False) as parser, \
                patch("original_parser.client._read_original_records", side_effect=AssertionError("catalog read")), \
                patch("tools.probe_additional_repo_routes.legacy_detail", return_value=(None, {})), \
                patch("tools.probe_additional_repo_routes.share_detail", side_effect=share), \
                patch("tools.probe_additional_repo_routes.plain_play", return_value={"original_verified": False}):
            parser.cookies = {"ttwid": SECRET}
            result = additional_routes(parser, WORK, None)
        self.assertEqual(len(calls), 5)  # Three variants, then at most two Cookie attempts.
        self.assertEqual(calls[3]["request_headers"]["Cookie"], "ttwid=" + SECRET)
        self.assertIn("share_nonce=new-anonymous-nonce", calls[4]["request_headers"]["Cookie"])
        self.assertIn("host_nonce=host-anonymous-nonce", calls[4]["request_headers"]["Cookie"])
        self.assertTrue(calls[4]["trailing_slash"])
        self.assertFalse(any(row.get("original_verified") for row in result))
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertNotIn("new-anonymous-nonce", json.dumps(result))
        self.assertNotIn("host-anonymous-nonce", json.dumps(result))


if __name__ == "__main__":
    unittest.main()
