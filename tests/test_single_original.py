"""Public parser and downloader accept only an explicitly identified, complete file."""
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from original_parser.client import OriginalParser, ParseError, _valid_original_record
from tests.test_incomplete_mp4_metadata import respond_with
from tests.test_parser import mp4, verified_result
from tests.test_source_pipeline import CDN, WORK, detail, payload, source_row


class SingleOriginalTests(unittest.TestCase):
    def test_one_complete_original_or_no_result(self):
        for has_audio in (True, False):
            body = mp4(audio=has_audio)
            row = source_row(size=len(body))
            work = detail([row, dict(row, main_url=CDN + "unused.mp4")])
            with self.subTest(has_audio=has_audio), OriginalParser(auto_guest=False) as parser, \
                    patch.object(parser, "detail", return_value=work), \
                    patch.object(parser, "_json", return_value=payload([source_row(quality="normal")])), \
                    patch.object(parser, "_catalog_original_candidate", return_value=None), \
                    patch.object(parser, "_get", side_effect=respond_with(body)), \
                    patch("original_parser.client._remember_original_record") as remember:
                if not has_audio:
                    with self.assertRaises(ParseError) as caught:
                        parser.parse(WORK)
                    self.assertEqual(caught.exception.code, "source_unavailable")
                    remember.assert_not_called()
                    continue
                result = parser.parse(WORK)
                data = result["data"]
                self.assertEqual(len(data["video_list"]), 1)
                self.assertNotIn("audio_url", data)
                self.assertNotIn("dash_mux_required", data)
                with tempfile.TemporaryDirectory() as folder:
                    dest = Path(folder) / "original.mp4"
                    parser.download(result, dest)
                    self.assertEqual(dest.read_bytes(), body)

    def test_skip_probe_request_fails_before_network(self):
        with OriginalParser(auto_guest=False) as parser, patch.object(parser, "detail") as detail_request:
            with self.assertRaises(ParseError):
                parser.parse(WORK, with_probe=False)
            detail_request.assert_not_called()

    def test_old_or_unverified_result_rejected_before_download_or_refresh(self):
        url = CDN + "video.mp4"
        for where, fields in (("data", {"source_evidence": "official_web_pc_bitrate"}),
                              ("row", {"official_quality": "normal"}),
                              ("data", {"source_selected": False}),
                              ("row", {"audio_urls": [CDN + "audio.mp4"]}),
                              ("data", {"dash_mux_required": True}),
                              ("probe", {"dash": True}),
                              ("probe", {"has_audio": False}),
                              ("data", {"download": {"dash_mux": True}})):
            result = verified_result({"urls": [url]}, expires_at=1)
            data = result["data"]
            targets = {"data": data, "row": data["video_list"][0], "probe": data["probe"]}
            targets[where].update(fields)
            with self.subTest(where=where, fields=fields), tempfile.TemporaryDirectory() as folder, \
                    OriginalParser(auto_guest=False) as parser, patch.object(parser, "parse") as refresh, \
                    patch.object(parser, "_get") as get:
                with self.assertRaises(ParseError) as caught:
                    parser.download(result, Path(folder) / "output" / "original.mp4")
                self.assertEqual(caught.exception.code, "source_unavailable")
                self.assertEqual(list(Path(folder).iterdir()), [])
                refresh.assert_not_called()
                get.assert_not_called()

    def test_historical_default_playback_record_is_never_an_original(self):
        record = dict(aweme_id=WORK, file_id="v01234567890", video_id="v01234567890",
                      file_hash="a" * 32, duration_seconds=2, size=1000, width=1920, height=1080,
                      verified_by="official_play_default_and_mp4_probe")
        for allow_external in (False, True):
            self.assertFalse(_valid_original_record(record, allow_external=allow_external))
