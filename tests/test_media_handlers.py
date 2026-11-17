"""QuickTime files can have distinct media and data handler boxes per track."""

import struct
import unittest

from original_parser.media import inspect_mp4


def box(kind, data):
    return struct.pack(">I4s", len(data) + 8, kind) + data


def handler(component, subtype):
    # QuickTime Handler Reference: version/flags, component type, subtype,
    # manufacturer, flags, flags mask. mdia uses mhlr, minf uses dhlr.
    return box(b"hdlr", bytes(4) + component + subtype + bytes(12))


def movie(track_specs, *, media_handler_first=True):
    """Simplified structure observed in official work 7698054262056552561."""
    mvhd = bytearray(100)
    struct.pack_into(">II", mvhd, 12, 1000, 46249)
    tracks = []
    for media_type, codec, data_type in track_specs:
        tkhd = bytearray(84)
        if codec == b"hvc1":
            struct.pack_into(">II", tkhd, 76, 1080 << 16, 1920 << 16)
        stsd = box(b"stsd", bytes(4) + struct.pack(">I", 1) + box(codec, bytes(32)))
        minf = box(b"minf", handler(b"dhlr", data_type) + box(b"stbl", stsd))
        media_handler = handler(b"mhlr", media_type) if media_type else b""
        mdia = media_handler + minf if media_handler_first else minf + media_handler
        tracks.append(box(b"trak", box(b"tkhd", tkhd) + box(b"mdia", mdia)))
    return (box(b"ftyp", b"qt  " + bytes(12)) + box(b"mdat", bytes(64))
            + box(b"moov", box(b"mvhd", mvhd) + b"".join(tracks)))


def inspect(data):
    return inspect_mp4(lambda offset, size: data[offset:offset + size], len(data))


class MediaHandlerTests(unittest.TestCase):
    def test_quicktime_data_handler_does_not_replace_media_handler(self):
        for media_handler_first in (True, False):
            with self.subTest(media_handler_first=media_handler_first):
                result = inspect(movie([
                    (b"vide", b"hvc1", b"url "),
                    (b"soun", b"mp4a", b"url "),
                ], media_handler_first=media_handler_first))
                self.assertTrue(result["has_video"])
                self.assertTrue(result["has_audio"])
                self.assertEqual(result["duration_seconds"], 46.249)
                self.assertEqual(result["tracks"], [
                    {"width": 1080, "height": 1920, "type": "vide", "codec": "hvc1"},
                    {"type": "soun", "codec": "mp4a"},
                ])

    def test_data_handler_cannot_supply_missing_audio_track(self):
        result = inspect(movie([(b"vide", b"hvc1", b"soun")]))
        self.assertTrue(result["has_video"])
        self.assertFalse(result["has_audio"])
        self.assertEqual(result["tracks"][0]["type"], "vide")

    def test_codec_and_data_handler_cannot_replace_missing_media_handler(self):
        result = inspect(movie([(None, b"hvc1", b"vide"), (None, b"mp4a", b"soun")]))
        self.assertFalse(result["has_video"])
        self.assertFalse(result["has_audio"])
        self.assertTrue(all("type" not in track for track in result["tracks"]))


if __name__ == "__main__":
    unittest.main()
