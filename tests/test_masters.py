"""Check the local link-to-master workflow without a platform response."""

import hashlib
import tempfile
import unittest
from pathlib import Path

from original_parser.client import ParseError
from original_parser.masters import MasterArchive
from tests.test_parser import mp4


WORK = "7700000000000000011"
LINK = f"https://www.douyin.com/video/{WORK}"


class MasterArchiveTests(unittest.TestCase):
    def test_round_trip_uses_only_the_link_and_preserves_the_original_bytes(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / "before-upload.mp4"
            body = mp4()
            source.write_bytes(body)
            archive = MasterArchive(base / "archive")
            archive.add(LINK, source)
            source.unlink()

            output = base / "recovered.mp4"
            record = MasterArchive(base / "archive").fetch(LINK + "?from=share", output)
            self.assertEqual(output.read_bytes(), body)
            self.assertEqual(record["sha256"], hashlib.sha256(body).hexdigest())
            self.assertEqual(record["source_evidence"], "operator_archived_master")

            with self.assertRaises(ParseError) as unavailable:
                archive.fetch("7700000000000000022", base / "other.mp4")
            self.assertEqual(unavailable.exception.code, "source_unavailable")

    def test_damaged_archive_does_not_publish_an_output_or_overwrite_an_existing_file(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / "master.mp4"
            body = mp4()
            source.write_bytes(body)
            archive = MasterArchive(base / "archive")
            archive.add(LINK, source)
            entry = base / "archive" / WORK / "master.mp4"
            entry.write_bytes(body[:-1] + bytes((body[-1] ^ 1,)))

            output = base / "recovered.mp4"
            with self.assertRaises(ParseError) as damaged:
                archive.fetch(LINK, output)
            self.assertEqual(damaged.exception.code, "hash_mismatch")
            self.assertFalse(output.exists())

            output.write_bytes(b"existing")
            with self.assertRaises(ParseError) as conflict:
                archive.fetch(LINK, output)
            self.assertEqual(conflict.exception.code, "file_exists")
            self.assertEqual(output.read_bytes(), b"existing")

    def test_incomplete_media_does_not_reserve_the_work_id(self):
        with tempfile.TemporaryDirectory() as folder:
            base = Path(folder)
            source = base / "before-upload.mp4"
            source.write_bytes(mp4(audio=False))
            archive = MasterArchive(base / "archive")
            with self.assertRaises(ParseError) as incomplete:
                archive.add(LINK, source)
            self.assertEqual(incomplete.exception.code, "incomplete_media")
            source.write_bytes(mp4())
            archive.add(LINK, source)
            with self.assertRaises(ParseError) as duplicate:
                archive.add(LINK, source)
            self.assertEqual(duplicate.exception.code, "master_exists")
