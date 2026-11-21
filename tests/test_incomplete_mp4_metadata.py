import hashlib
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from original_parser.client import OriginalParser, ParseError
from tests.test_parser import AWEME, VID, Response, mp4, verified_result


MEDIA_URL = "https://v11.douyinvod.com/fixture.mp4"


def incomplete_media():
    # Keep the original box sizes, file length and audio/video handlers intact.
    return ((name, mp4().replace(kind, b"free")) for name, kind in
            (("missing duration", b"mvhd"), ("missing dimensions", b"tkhd")))


def respond_with(content):
    def get(url, *, headers=None):
        if not headers or "Range" not in headers:
            return Response(content, url=url)
        lo, hi = map(int, headers["Range"][6:].split("-"))
        return Response(content[lo:hi + 1], status=206, url=url,
                        headers={"Content-Range": f"bytes {lo}-{hi}/{len(content)}"})

    return get


def candidate(content):
    return {"urls": [MEDIA_URL], "size": len(content),
            "file_hash": hashlib.md5(content).hexdigest()}


class IncompleteMediaTests(unittest.TestCase):
    def test_probe_rejects_unverifiable_container(self):
        for name, content in incomplete_media():
            with self.subTest(case=name), OriginalParser(auto_guest=False) as parser, \
                    patch.object(parser, "_get", side_effect=respond_with(content)):
                row = candidate(content)
                with self.assertRaises(ParseError) as caught:
                    parser.probe(row)
                self.assertEqual(caught.exception.code, "incomplete_media")
                self.assertNotIn("url", row)

    def test_registration_rejects_metadata_before_writing(self):
        detail = {"aweme_id": AWEME, "video": {"play_addr": {"uri": VID}, "duration": 2000}}
        for name, content in incomplete_media():
            with self.subTest(case=name), OriginalParser(auto_guest=False) as parser, \
                    patch.object(parser, "detail", return_value=detail), \
                    patch.object(parser, "_get", side_effect=respond_with(content)), \
                    patch("original_parser.client._remember_original_record") as remember:
                with self.assertRaises(ParseError) as caught:
                    parser.register_external_original(AWEME, MEDIA_URL)
                self.assertEqual(caught.exception.code, "incomplete_media")
                remember.assert_not_called()

    def test_download_does_not_publish_when_hash_matches_but_metadata_is_missing(self):
        for name, content in incomplete_media():
            with self.subTest(case=name), tempfile.TemporaryDirectory() as folder, \
                    OriginalParser(auto_guest=False) as parser, \
                    patch.object(parser, "_get", side_effect=respond_with(content)):
                result = verified_result(candidate(content))
                with self.assertRaises(ParseError) as caught:
                    parser._download_once(result, Path(folder) / "out.mp4")
                self.assertEqual(caught.exception.code, "download_failed")
                self.assertEqual(list(Path(folder).iterdir()), [])

    def test_complete_media_supplies_missing_candidate_metadata(self):
        content = mp4()
        row = candidate(content)
        with tempfile.TemporaryDirectory() as folder, OriginalParser(auto_guest=False) as parser, \
                patch.object(parser, "_get", side_effect=respond_with(content)):
            probe = parser.probe(row)
            self.assertEqual((row["width"], row["height"], probe["duration_seconds"]), (1920, 1080, 2))
            result = verified_result(row, probe=probe)
            dest = Path(folder) / "out.mp4"
            record = parser._download_once(result, dest)
            self.assertTrue(record["official_hash_match"])
            self.assertEqual(dest.read_bytes(), content)
