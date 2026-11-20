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


def movie(track_specs, *, media_handler_first=True, sample_data=bytes(32)):
    """Simplified structure observed in official work 7698054262056552561."""
    mvhd = bytearray(100)
    struct.pack_into(">II", mvhd, 12, 1000, 46249)
    tracks = []
    for media_type, codec, data_type in track_specs:
        tkhd = bytearray(84)
        if codec == b"hvc1":
            struct.pack_into(">II", tkhd, 76, 1080 << 16, 1920 << 16)
        stsd = box(b"stsd", bytes(4) + struct.pack(">I", 1) + box(codec, sample_data))
        minf = box(b"minf", handler(b"dhlr", data_type) + box(b"stbl", stsd))
        media_handler = handler(b"mhlr", media_type) if media_type else b""
        mdia = media_handler + minf if media_handler_first else minf + media_handler
        tracks.append(box(b"trak", box(b"tkhd", tkhd) + box(b"mdia", mdia)))
    return (box(b"ftyp", b"qt  " + bytes(12)) + box(b"mdat", bytes(64))
            + box(b"moov", box(b"mvhd", mvhd) + b"".join(tracks)))


def inspect(data):
    return inspect_mp4(lambda offset, size: data[offset:offset + size], len(data))


def metadata(comment):
    keys = box(b"keys", struct.pack(">II", 0, 1) + struct.pack(">I", 15) + b"mdta" + b"comment")
    data = box(b"data", struct.pack(">II", 1, 0) + comment.encode("utf-8"))
    ilst = box(b"ilst", box(struct.pack(">I", 1), data))
    meta = box(b"meta", bytes(4) + box(b"hdlr", bytes(25)) + keys + ilst)
    return box(b"udta", meta)


class MediaHandlerTests(unittest.TestCase):
    def test_mdta_comment_tag_is_extracted_without_media_scan(self):
        mvhd = bytearray(100)
        struct.pack_into(">II", mvhd, 12, 1000, 2000)
        result = inspect(box(b"moov", box(b"mvhd", mvhd) + metadata("vid:alternate-source")))
        self.assertEqual(result["tags"], {"comment": "vid:alternate-source"})

    def test_quicktime_comment_item_is_extracted(self):
        item = box(b"\xa9cmt", box(b"data", struct.pack(">II", 1, 0) + b"vid:alternate-source"))
        result = inspect(box(b"moov", box(b"mvhd", bytes(100)) + box(b"udta", item)))
        self.assertEqual(result["tags"], {"comment": "vid:alternate-source"})

    def test_sample_dimensions_only_used_for_video_without_display_dimensions(self):
        sample = bytearray(78)
        struct.pack_into(">HH", sample, 24, 1280, 720)
        tracks = inspect(movie([(b"vide", b"avc1", b"url "), (b"vide", b"hvc1", b"url "),
                                (b"soun", b"mp4a", b"url ")], media_handler_first=False,
                               sample_data=sample))["tracks"]
        self.assertEqual((tracks[0]["width"], tracks[0]["height"]), (1280, 720))
        self.assertEqual((tracks[1]["width"], tracks[1]["height"]), (1080, 1920))
        self.assertNotIn("width", tracks[2])

    def test_truncated_visual_description_does_not_supply_dimensions(self):
        sample = bytearray(28)
        struct.pack_into(">HH", sample, 24, 1280, 720)
        track, = inspect(movie([(b"vide", b"avc1", b"url ")], sample_data=sample))["tracks"]
        self.assertNotIn("width", track)

    def test_unknown_duration_is_not_interpreted_as_a_long_movie(self):
        for version, unknown in ((0, 0xffffffff), (1, 0xffffffffffffffff)):
            mvhd = bytearray(100)
            mvhd[0] = version
            struct.pack_into(">IQ" if version else ">II", mvhd, 20 if version else 12, 1000, unknown)
            with self.subTest(version=version):
                self.assertIsNone(inspect(box(b"moov", box(b"mvhd", mvhd)))["duration_seconds"])

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
