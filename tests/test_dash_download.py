"""Check the published MP4 and digests using synthetic, offline media."""

import hashlib
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from original_parser.client import OriginalParser, ParseError
from original_parser.media import inspect_file
from tests.test_default_hash import Response


class DashDownloadTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which("ffmpeg"), "ffmpeg required for mux test")
    def test_muxes_both_tracks_and_records_their_actual_digests(self):
        with tempfile.TemporaryDirectory() as folder, OriginalParser(auto_guest=False) as parser:
            root = Path(folder)
            video, audio = root / "input.mp4", root / "input.m4a"
            subprocess.run([
                "ffmpeg", "-v", "error",
                "-f", "lavfi", "-i", "color=size=32x64:duration=1",
                "-f", "lavfi", "-i", "sine=duration=1",
                "-map", "0:v", "-c:v", "mpeg4", str(video),
                "-map", "1:a", "-c:a", "aac", str(audio)
            ], capture_output=True, check=True)
            video_body, audio_body = video.read_bytes(), audio.read_bytes()
            urls = ["https://media.example/video", "https://media.example/audio"]
            bodies = dict(zip(urls, (video_body, audio_body)))
            candidate = dict(urls=urls[:1], audio_urls=urls[1:], size=len(video_body),
                             audio_size=len(audio_body), file_hash="0" * 32, audio_hash="1" * 32,
                             duration_seconds=1, width=32, height=64)
            result = {"data": dict(dash_mux_required=True, url=urls[0], video_list=[candidate])}

            output = root / "merged.mp4"
            with patch.object(parser, "_get", side_effect=lambda url: Response(bodies[url])):
                record = parser.download(result, output)

            media = inspect_file(output)
            self.assertTrue(media["has_video"] and media["has_audio"])
            self.assertAlmostEqual(media["duration_seconds"], 1.0, delta=0.1)
            self.assertEqual(record["video_bytes"], len(video_body))
            self.assertEqual(record["audio_bytes"], len(audio_body))
            self.assertEqual(record["video_md5"], hashlib.md5(video_body).hexdigest())
            self.assertEqual(record["audio_md5"], hashlib.md5(audio_body).hexdigest())
            self.assertFalse(record["video_hash_match"])
            self.assertFalse(record["audio_hash_match"])
            self.assertIsNone(record["official_hash_match"])
            self.assertEqual(record["bytes"], output.stat().st_size)
            self.assertEqual(record["sha256"], hashlib.sha256(output.read_bytes()).hexdigest())

    def test_missing_ffmpeg_leaves_destination_empty(self):
        result = {"data": dict(dash_mux_required=True, url="https://media.example/video",
                               video_list=[{"audio_urls": ["https://media.example/audio"]}])}
        with tempfile.TemporaryDirectory() as folder, OriginalParser(auto_guest=False) as parser, \
                patch("shutil.which", return_value=None):
            with self.assertRaises(ParseError) as error:
                parser.download(result, Path(folder) / "merged.mp4")
            self.assertEqual(error.exception.code, "ffmpeg_missing")
            self.assertEqual(list(Path(folder).iterdir()), [])
