import base64
import hashlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from original_parser.client import OriginalParser, ParseError, _content_md5
from tests.test_parser import verified_result


class Raw(io.BytesIO):
    def read(self, size=-1, **kwargs):
        return super().read(size)


class Response:
    def __init__(self, body, headers=None, status=200):
        self.body, self.headers, self.status_code = body, headers or {}, status
        self.url = "https://v3.douyinvod.com/video.mp4"
        self.raw = Raw(body)
        self.iterated = False

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.raw.close()

    def iter_content(self, size):
        self.iterated = True
        yield self.body


def result_for(body):
    url = "https://v3.douyinvod.com/video.mp4"
    return verified_result({"urls": [url], "size": len(body), "file_hash": None})


class DownloadHashTests(unittest.TestCase):
    def test_download_without_payload_hash_uses_official_response_digest(self):
        from tests.test_parser import mp4
        body = mp4()
        response = Response(body, {"Content-MD5": base64.b64encode(hashlib.md5(body).digest()).decode()})
        with tempfile.TemporaryDirectory() as folder, OriginalParser(auto_guest=False) as parser, \
                patch.object(parser, "_get", return_value=response):
            path = Path(folder) / "original.mp4"
            record = parser._download_once(result_for(body), path)
            self.assertTrue(record["official_hash_match"])
            self.assertEqual(record["md5"], hashlib.md5(body).hexdigest())
            self.assertEqual(path.read_bytes(), body)

    def test_wrong_official_digest_never_publishes_download(self):
        body = b"tampered-file-payload"
        response = Response(body, {"Content-MD5": base64.b64encode(bytes(16)).decode()})
        with tempfile.TemporaryDirectory() as folder, OriginalParser(auto_guest=False) as parser, \
                patch.object(parser, "_get", return_value=response):
            path = Path(folder) / "original.mp4"
            with self.assertRaises(ParseError):
                parser._download_once(result_for(body), path)
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_download_without_upstream_digest_reports_no_official_hash_match(self):
        body = b"complete-file-payload"
        missing = Response(body)
        result = result_for(body)
        result["data"]["video_list"][0].update(duration_seconds=2, width=1920, height=1080)
        media = {"has_audio": True, "has_video": True, "duration_seconds": 2,
                 "tracks": [{"type": "vide", "width": 1920, "height": 1080}]}
        with tempfile.TemporaryDirectory() as folder, OriginalParser(auto_guest=False) as parser, \
                patch.object(parser, "_get", return_value=missing), \
                patch("original_parser.client.inspect_file", return_value=media):
            record = parser._download_once(result, Path(folder) / "original.mp4")
        self.assertIsNone(record["official_hash_match"])
        self.assertEqual(record["md5"], hashlib.md5(body).hexdigest())
        self.assertEqual(record["sha256"], hashlib.sha256(body).hexdigest())

    def test_without_upstream_hash_wrong_duration_or_dimensions_cannot_be_published(self):
        for width, duration in ((1920, 30), (1280, 2)):
            result = result_for(b"payload")
            result["data"]["video_list"][0].update(duration_seconds=2, width=1920, height=1080)
            media = {"has_audio": True, "has_video": True, "duration_seconds": duration,
                     "tracks": [{"type": "vide", "width": width, "height": 1080}]}
            with self.subTest(width=width, duration=duration), tempfile.TemporaryDirectory() as folder, \
                    OriginalParser(auto_guest=False) as parser, \
                    patch.object(parser, "_get", return_value=Response(b"payload")), \
                    patch("original_parser.client.inspect_file", return_value=media):
                with self.assertRaises(ParseError):
                    parser._download_once(result, Path(folder) / "original.mp4")
                self.assertEqual(list(Path(folder).iterdir()), [])

    def test_only_valid_full_md5_is_accepted(self):
        for headers in ({}, {"ETag": '"' + "a" * 32 + '"'}, {"Content-MD5": "bad"},
                        {"Content-MD5": base64.b64encode(b"short").decode()}):
            with self.subTest(headers=headers):
                self.assertIsNone(_content_md5(headers))


if __name__ == "__main__":
    unittest.main()
