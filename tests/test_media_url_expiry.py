"""Issued-time query values must not consume the download refresh allowance."""

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from original_parser.client import OriginalParser, ParseError, _media_url_expiry
from original_parser.guard import GuardConfig, RequestGuard


WORK = "7700000000000000001"
VID = "v03033g10000expirytest"
NOW = 2_000_000_000
CDN = "https://v3.douyinvod.com/77359400/video.mp4"


def result_for(url):
    expiry = _media_url_expiry(url)
    return {"code": 0, "data": {
        "aweme_id": WORK, "url": url, "expires_at": expiry,
        "source_selected": True, "fallback_used": False,
        "quality": "source", "official_quality": "original", "source_evidence": "official_play_hash",
        "probe": {"ok": True, "has_audio": True, "has_video": True},
        "video_list": [{"url": url, "urls": [url], "expires_at": expiry,
                        "quality": "source", "official_quality": "original", "source_evidence": "official_play_hash"}],
    }}


class MediaUrlExpiryTests(unittest.TestCase):
    def test_issued_time_and_hex_path_do_not_claim_an_expiry(self):
        self.assertIsNone(_media_url_expiry(CDN))
        self.assertIsNone(_media_url_expiry(CDN + f"?dy_q={NOW - 1}"))

    def test_all_existing_explicit_expiry_fields_are_preserved(self):
        for key in ("x-expires", "expires", "x-tos-expires", "url_expire", "expire"):
            with self.subTest(field=key):
                self.assertEqual(_media_url_expiry(
                    CDN + f"?dy_q={NOW - 1}&{key}={NOW + 3600}"), str(NOW + 3600))

    def test_explicit_field_priority_and_blank_values_are_preserved(self):
        self.assertEqual(_media_url_expiry(
            CDN + "?expire=500&url_expire=400&x-tos-expires=300&expires=200&x-expires=100"), "100")
        self.assertEqual(_media_url_expiry(CDN + "?x-expires=&expires=200"), "200")

    def test_original_dispatch_paths_use_explicit_expiry_only(self):
        detail = {"aweme_id": WORK, "video": {"duration": 2000}}
        record = {"aweme_id": WORK, "video_id": VID, "file_id": VID,
                  "file_hash": "a" * 32, "size": 1000, "width": 640,
                  "height": 360, "duration_seconds": 2}
        candidate = {**record, "expires_at": "1", "source_evidence": "official_quality"}
        for query, expected in ((f"dy_q={NOW - 1}", None),
                                (f"dy_q={NOW - 1}&expire={NOW + 3600}", str(NOW + 3600))):
            url = CDN + "?" + query
            with self.subTest(query=query), OriginalParser(auto_guest=False) as parser:
                with patch.object(parser, "_dispatch_official_original", return_value=url), \
                        patch("original_parser.client._read_original_records", return_value={WORK: record}):
                    refreshed = parser._redispatch_source_candidate(detail, VID, candidate)
                    catalog = parser._catalog_original_candidate(detail, VID)
                for kind, value in (("redispatch", refreshed), ("catalog", catalog)):
                    with self.subTest(path=kind):
                        self.assertIsNotNone(value)
                        self.assertEqual(value["url"], url)
                        self.assertEqual(value["expires_at"], expected)

    def test_unknown_expiry_does_not_refresh_before_downloading(self):
        result = result_for(CDN + f"?dy_q={NOW - 1}")
        with tempfile.TemporaryDirectory() as folder, OriginalParser(auto_guest=False) as parser, \
                patch("original_parser.client.time.time", return_value=NOW), \
                patch.object(parser, "parse") as refresh, \
                patch.object(parser, "_download_once", return_value={"ok": True}) as download:
            self.assertEqual(parser.download(result, Path(folder) / "video.mp4"), {"ok": True})
            refresh.assert_not_called()
            download.assert_called_once()

    def test_first_download_failure_can_still_refresh_once(self):
        result = result_for(CDN + f"?dy_q={NOW - 1}")
        fresh = result_for(CDN + f"?x-expires={NOW + 3600}")
        with tempfile.TemporaryDirectory() as folder, OriginalParser(auto_guest=False) as parser, \
                patch("original_parser.client.time.time", return_value=NOW), \
                patch.object(parser, "parse", return_value=copy.deepcopy(fresh)) as refresh, \
                patch.object(parser, "_download_once", side_effect=[
                    ParseError("download_failed", "first attempt failed"), {"ok": True}]) as download:
            self.assertEqual(parser.download(result, Path(folder) / "video.mp4"), {"ok": True})
            refresh.assert_called_once_with(WORK)
            self.assertEqual(download.call_count, 2)
            self.assertEqual(result, fresh)

    def test_actual_expiry_still_refreshes_before_downloading(self):
        result = result_for(CDN + f"?x-expires={NOW - 1}")
        fresh = result_for(CDN + f"?x-expires={NOW + 3600}")
        with tempfile.TemporaryDirectory() as folder, OriginalParser(auto_guest=False) as parser, \
                patch("original_parser.client.time.time", return_value=NOW), \
                patch.object(parser, "parse", return_value=copy.deepcopy(fresh)) as refresh, \
                patch.object(parser, "_download_once", return_value={"ok": True}) as download:
            parser.download(result, Path(folder) / "video.mp4")
            refresh.assert_called_once_with(WORK)
            download.assert_called_once()
            self.assertEqual(result, fresh)

    def test_unknown_expiry_still_prevents_guard_caching(self):
        for query, expected_loads in ((f"dy_q={NOW - 1}", 2),
                                      (f"x-expires={NOW + 3600}", 1)):
            with self.subTest(query=query):
                guard = RequestGuard(GuardConfig(interval_range=(0, 0)), wall_clock=lambda: NOW)
                calls = []

                def load():
                    calls.append(1)
                    return result_for(CDN + "?" + query)

                try:
                    guard.run(WORK, load)
                    guard.run(WORK, load)
                    self.assertEqual(len(calls), expected_loads)
                finally:
                    guard.close()


if __name__ == "__main__":
    unittest.main()
