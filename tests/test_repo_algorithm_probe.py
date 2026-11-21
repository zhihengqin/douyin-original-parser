import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from original_parser.client import OriginalParser, ParseError
from tools.probe_repo_algorithm import (
    MAX_RANGE_BYTES, ProbeParser, main, probe_fplay, probe_link, share_detail,
)

WORK = "7707993970332290314"
VID = "v28033gi0000dbs4nevog65jrl6u1s10"
OTHER_VID = "v0200fg10000db5jd27og65gafbkjltg"
SECRET = "sensitive-signed-query"
MEDIA = {"actual_size": 30, "bytes_read": 24, "http_requests": 3,
         "embedded_vids": [], "media": {"has_video": True, "has_audio": True,
         "duration_seconds": 5.0, "tracks": [{"type": "vide", "width": 720, "height": 1280},
                                             {"type": "soun"}]}}


def video_with_model():
    return {"play_addr": {"uri": VID, "data_size": 100}, "duration": 5000,
            "video_model": {"video_id": VID, "fallback_api":
                f"https://vas-lf-x.snssdk.com/video/fplay/1/{'a' * 32}/{VID}?token={SECRET}"}}


def payload(quality="original", vid=VID):
    return {"code": 0, "video_info": {"code": 0, "data": {
        "status": 10, "video_id": vid, "video_duration": 5.0,
        "video_list": [{"quality": quality, "vtype": "mp4", "size": 30,
                        "vwidth": 720, "vheight": 1280,
                        "main_url": "https://v3.douyinvod.com/file?token=" + SECRET}]}}}


class Raw(io.BytesIO):
    def read(self, size=-1, **_):
        return super().read(size)


class Response:
    def __init__(self, status, body=b"", headers=None):
        self.status_code = status
        self.raw = Raw(body)
        self.headers = headers or {}
        self.url = "https://v3.douyinvod.com/file?token=" + SECRET

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.raw.close()

    def close(self):
        self.raw.close()

    def iter_content(self, length):
        while chunk := self.raw.read(length):
            yield chunk


class RepoAlgorithmProbeTests(unittest.TestCase):
    def test_official_source_without_catalog_or_reference_and_no_secret_output(self):
        detail = {"aweme_id": WORK, "video": video_with_model()}
        with OriginalParser(auto_guest=False) as parser, \
                patch.object(parser, "detail", return_value=detail), \
                patch.object(parser, "_json", return_value=payload()), \
                patch.object(parser, "source_streams", side_effect=AssertionError("catalog flow")), \
                patch.object(parser, "_get", side_effect=AssertionError("unexpected network")), \
                patch("original_parser.client._read_original_records", side_effect=AssertionError("catalog read")), \
                patch("original_parser.client._remember_original_record", side_effect=AssertionError("catalog write")), \
                patch("tools.probe_repo_algorithm.inspect_identity", return_value=MEDIA), \
                patch("tools.probe_repo_algorithm.share_detail", return_value=(None, {"route": "mobile_share_ssr"})):
            result = probe_link(parser, "https://www.douyin.com/video/" + WORK)
        self.assertTrue(result["original_verified"])
        self.assertFalse(result["catalog_used"])
        self.assertFalse(result["reference_used"])
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertNotIn("https://", json.dumps(result))

    def test_normal_wrong_vid_and_missing_audio_cannot_pass_as_source(self):
        for reply, media in ((payload("normal"), MEDIA),
                             (payload(vid=OTHER_VID), MEDIA),
                             (payload(), {**MEDIA, "media": {**MEDIA["media"], "has_audio": False}}),
                             (payload(), {**MEDIA, "embedded_vids": [OTHER_VID]})):
            with self.subTest(reply=reply["video_info"]["data"]["video_id"], media=media), \
                    OriginalParser(auto_guest=False) as parser, \
                    patch.object(parser, "_json", return_value=reply), \
                    patch("tools.probe_repo_algorithm.inspect_identity", return_value=media):
                rows = probe_fplay(parser, video_with_model())
            self.assertTrue(rows)
            self.assertFalse(any(row.get("original_verified") for row in rows))

    def test_share_page_does_not_accept_unrelated_work_or_empty_router(self):
        for items, outcome in (([], "item_list_not_present"),
                               ([{"aweme_id": "123", "video": {"play_addr": {"uri": VID}}}], "work_identity_mismatch")):
            router = {"loaderData": {"video_(id)/page": {"videoInfoRes": {"item_list": items}}}}
            html = ("<script>window._ROUTER_DATA = " + json.dumps(router) + ";</script>").encode()
            with self.subTest(outcome=outcome), OriginalParser(auto_guest=False) as parser, \
                    patch.object(parser, "_get", return_value=Response(200, html)) as get:
                detail, result = share_detail(parser, WORK)
            self.assertIsNone(detail)
            self.assertEqual(result["outcome"], outcome)
            self.assertFalse(result["original_verified"])
            get.assert_called_once()

    def test_cli_failure_is_nonzero_and_does_not_write_error_url(self):
        with tempfile.TemporaryDirectory() as folder, \
                patch("tools.probe_repo_algorithm.probe_link",
                      side_effect=ParseError("network_error", "https://host/?token=" + SECRET)), \
                patch("sys.stdout", new_callable=io.StringIO):
            out = Path(folder) / "report.json"
            status = main([WORK, "--out", str(out)])
            report = out.read_text(encoding="utf-8")
        self.assertEqual(status, 2)
        self.assertFalse(json.loads(report)["original_verified"])
        self.assertNotIn(SECRET, report)

    def test_budget_includes_redirects_and_rejects_oversized_range_before_network(self):
        redirect = Response(302, headers={"Location": "https://v3.douyinvod.com/next"})
        with ProbeParser(auto_guest=False) as parser, \
                patch("tools.probe_repo_algorithm.MAX_HTTP_REQUESTS", 1):
            parser._transport_request = Mock(return_value=redirect)
            with self.assertRaises(ParseError) as caught:
                parser._get("https://v3.douyinvod.com/start")
            self.assertEqual(caught.exception.code, "probe_budget_exceeded")
            self.assertTrue(parser.budget_exhausted)
            self.assertEqual(parser.http_requests, 1)
            parser._transport_request.assert_called_once()
        with ProbeParser(auto_guest=False) as parser:
            parser._transport_request = Mock(side_effect=AssertionError("unexpected network"))
            with self.assertRaises(ParseError):
                parser._get("https://v3.douyinvod.com/start", headers={"Range": f"bytes=0-{MAX_RANGE_BYTES}"})
            self.assertTrue(parser.budget_exhausted)
            self.assertEqual(parser.http_requests, 0)

    def test_omitted_candidates_report_incomplete(self):
        detail = {"aweme_id": WORK, "video": video_with_model()}
        candidate = {"urls": ["https://v3.douyinvod.com/file"], "size": 30}
        with OriginalParser(auto_guest=False) as parser, \
                patch.object(parser, "detail", return_value=detail), \
                patch.object(parser, "_json", return_value=payload()), \
                patch.object(parser, "_source_candidates", return_value=({}, [candidate] * 4)), \
                patch("tools.probe_repo_algorithm.inspect_identity", side_effect=ValueError(SECRET)), \
                patch("tools.probe_repo_algorithm.share_detail", return_value=(None, {"route": "mobile_share_ssr"})):
            result = probe_link(parser, WORK)
        self.assertFalse(result["original_verified"])
        self.assertTrue(result["routes_incomplete"])
        self.assertEqual(result["result"], "investigation_incomplete")
        self.assertEqual(result["routes"][0]["candidates_omitted"], 1)
        self.assertNotIn(SECRET, json.dumps(result))


if __name__ == "__main__":
    unittest.main()
