import struct
import unittest
from unittest.mock import patch

from original_parser.client import OriginalParser, ParseError
from tests.test_incomplete_mp4_metadata import respond_with
from tests.test_parser import box


VIDEO = "https://media.example/video"
AUDIO = "https://media.example/audio"


def track_file(kind, duration_ms):
    tkhd = bytearray(84)
    if kind == b"vide":
        struct.pack_into(">II", tkhd, 76, 720 << 16, 1280 << 16)
    handler = box(b"hdlr", bytes(8) + kind)
    track = box(b"trak", box(b"tkhd", tkhd) + box(b"mdia", handler))
    header = b"" if duration_ms is None else box(
        b"mvhd", bytes(12) + struct.pack(">II", 1000, duration_ms))
    return box(b"ftyp", b"isom" + bytes(4)) + box(b"moov", header + track)


def probe(video, audio, declared_duration):
    bodies = {VIDEO: video, AUDIO: audio}
    candidate = {"urls": [VIDEO], "audio_urls": [AUDIO], "size": len(video),
                 "audio_size": len(audio), "duration_seconds": declared_duration,
                 "width": 720, "height": 1280}

    def get(url, **kwargs):
        return respond_with(bodies[url])(url, **kwargs)

    with OriginalParser(auto_guest=False) as parser, patch.object(parser, "_get", side_effect=get):
        return parser.probe_dash(candidate)


class DashProbeTests(unittest.TestCase):
    def test_missing_or_zero_duration_on_either_track_is_rejected(self):
        for video_ms, audio_ms in ((None, 2000), (2000, None), (0, 2000), (2000, 0)):
            with self.subTest(video_ms=video_ms, audio_ms=audio_ms), self.assertRaises(ParseError) as caught:
                probe(track_file(b"vide", video_ms), track_file(b"soun", audio_ms), 2)
            self.assertEqual(caught.exception.code, "probe_failed")

    def test_malformed_container_is_a_probe_failure(self):
        # A valid ftyp header followed by a truncated moov passes the initial range check.
        malformed = box(b"ftyp", b"isom" + bytes(4)) + struct.pack(">I4s", 1000, b"moov")
        for video, audio in ((malformed, track_file(b"soun", 2000)),
                             (track_file(b"vide", 2000), malformed)):
            with self.subTest(video_malformed=video == malformed), self.assertRaises(ParseError) as caught:
                probe(video, audio, 2)
            self.assertEqual(caught.exception.code, "probe_failed")

    def test_tracks_must_match_each_other_and_declared_duration(self):
        for video_ms, audio_ms, declared in ((5000, 5000, 2), (3000, 3001, 2),
                                             (3001, 3000, 2), (2000, 3001, 3)):
            with self.subTest(video_ms=video_ms, audio_ms=audio_ms, declared=declared), \
                    self.assertRaises(ParseError) as caught:
                probe(track_file(b"vide", video_ms), track_file(b"soun", audio_ms), declared)
            self.assertEqual(caught.exception.code, "identity_mismatch")

    def test_accepts_one_second_tolerance_and_missing_declaration(self):
        for declared in (2, None):
            with self.subTest(declared=declared):
                result = probe(track_file(b"vide", 2000), track_file(b"soun", 3000), declared)
                self.assertEqual(result["duration_seconds"], 2)
                self.assertTrue(result["ok"])
