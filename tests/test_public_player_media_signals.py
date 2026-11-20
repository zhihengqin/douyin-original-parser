import struct
import unittest

from tools.public_player_media_signals import media_kind, mp4_tracks, response_extent


class PublicPlayerMediaSignalsTest(unittest.TestCase):
    def test_media_hints_independent_of_host(self):
        self.assertEqual(media_kind("Fetch", "Video/MP4; foo=bar", "https://a/opaque"), "video")
        self.assertEqual(media_kind("XHR", "", "https://elsewhere/n/init.M4S?q=.png"), "media")
        self.assertEqual(media_kind("Media", "", "https://elsewhere/n"), "media")
        self.assertEqual(media_kind("XHR", "audio/mpegurl", "https://a/n"), "manifest")
        self.assertIsNone(media_kind("Fetch", "application/json", "https://a/data?file=x.mp4"))

    def test_range_size_vs_full_size(self):
        h = {"Content-Range": "bytes 30-49/140778272", "Content-Length": "20"}
        result = response_extent(206, h, from_cache=True)
        self.assertEqual((result["content_length"], result["total_bytes"], result["range_start"],
                          result["range_end"], result["from_cache"]), (20, 140778272, 30, 49, True))
        for partial in ({"content-length": "20"}, {**h, "Content-Range": "bytes 30-49/*"},
                        {**h, "Content-Range": "bytes 30-49/49"}, {**h, "Content-Length": "19"}):
            self.assertIsNone(response_extent(206, partial)["total_bytes"])
        self.assertEqual(response_extent(200, {"Content-Length": "64"})["total_bytes"], 64)
        for status, h in [(304, {"Content-Length": "64"}), (200, {}),
                          (200, {"Content-Length": "64", "Content-Encoding": "gzip"}),
                          (416, {"Content-Length": "30", "Content-Range": "bytes */64"})]:
            self.assertIsNone(response_extent(status, h)["total_bytes"])

    def test_tracks_require_complete_mp4_metadata(self):
        def box(name, payload):
            return struct.pack(">I4s", len(payload) + 8, name) + payload
        def track(handler):
            return box(b"trak", box(b"tkhd", bytes(76) + struct.pack(">II", 1280 << 16, 720 << 16))
                       + box(b"mdia", box(b"hdlr", bytes(8) + handler)))
        body = box(b"ftyp", b"isom") + box(b"moov", track(b"soun") + track(b"vide"))
        self.assertEqual(mp4_tracks(body), [{"handler": "soun"},
                                            {"handler": "vide", "width": 1280, "height": 720}])
        self.assertEqual(mp4_tracks(body[:-1]), [])
        self.assertEqual(mp4_tracks(box(b"mdat", b"moov trak fake vide hdlr")), [])
