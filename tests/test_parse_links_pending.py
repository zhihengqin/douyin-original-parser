import io
import json
import tempfile
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import parse_links
from original_parser import ParseError
from original_parser.web_attempts import WebAttemptJournal


WORK = "7700000000000000001"
LINK = f"https://www.douyin.com/video/{WORK}"


class PendingCLITests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.output = Path(stack.enter_context(tempfile.TemporaryDirectory()))
        self.journal = WebAttemptJournal(self.output / "web_attempts.sqlite3")
        stack.enter_context(patch.multiple(parse_links, OUTPUT_DIR=self.output, DOWNLOAD=False,
                                           COOKIE_FILE=None, ALLOW_EXTERNAL=True))
        stack.enter_context(redirect_stdout(io.StringIO()))
        stack.enter_context(redirect_stderr(io.StringIO()))
        self.factory = stack.enter_context(patch.object(parse_links, "OriginalParser"))
        self.parser = self.factory.return_value.__enter__.return_value
        self.parser.web_attempt_work_id = WORK
        self.parser.web_catalog_only_transcodes = True
        self.parser.web_catalog_observations = [
            dict(stage=stage, valid=True, rows=1, normal_rows=1,
                 original_rows=0, source_rows=0, unknown_rows=0, max_size_bytes=1000)
            for stage in ("original", "source")
        ]

    def test_retry_after_transcode_only_result_saves_file_and_drains_queue(self):
        self.parser.parse.side_effect = ParseError("source_unavailable", "only normal rows")
        self.assertEqual(parse_links.main([LINK]), 2)
        self.assertEqual(self.journal.pending_ids(), [WORK])
        self.assertFalse((self.output / f"{WORK}.json").exists())

        result = {"data": {"aweme_id": WORK, "source_evidence": "official_quality",
                           "official_quality": "original", "level": "original", "width": 1280,
                           "height": 720, "size_bytes": 1024, "url": "https://media.invalid/file.mp4"}}
        self.parser.parse.side_effect = None
        self.parser.parse.return_value = result
        self.assertEqual(parse_links.main(["--retry-pending"]), 0)
        self.assertIs(self.factory.call_args.kwargs["allow_external_asset_recovery"], False)
        self.parser.parse.assert_called_with(WORK)
        self.assertEqual(json.loads((self.output / f"{WORK}.json").read_text("utf-8")), result)
        self.assertEqual(self.journal.pending_ids(), [])

    def test_probe_failure_is_not_queued(self):
        self.parser.web_catalog_only_transcodes = False
        self.parser.web_catalog_observations = [
            dict(stage="original", valid=True, rows=1, normal_rows=0, original_rows=1)
        ]
        self.parser.parse.side_effect = ParseError("probe_failed", "media was incomplete")
        self.assertEqual(parse_links.main([WORK]), 2)
        self.assertEqual(self.journal.pending_ids(), [])
        self.assertFalse((self.output / f"{WORK}.json").exists())

    def test_pc_playback_success_leaves_original_discovery_pending(self):
        checked = {"data": {"aweme_id": WORK, "source_evidence": "official_web_pc_bitrate",
                            "official_quality": None, "level": "PC Web 独有播放档",
                            "width": 720, "height": 1280, "size_bytes": 1024,
                            "url": "https://media.invalid/file.mp4"}}
        self.parser.parse.return_value = checked
        self.assertEqual(parse_links.main([LINK]), 0)
        self.assertEqual(self.journal.pending_ids(), [WORK])
        self.assertEqual(parse_links.main(["--retry-pending"]), 0)
        self.assertEqual(self.journal.pending_ids(), [WORK])

    def test_empty_retry_does_not_open_a_parser(self):
        self.assertEqual(parse_links.main(["--retry-pending"]), 0)
        self.factory.assert_not_called()

    def test_retry_rejects_explicit_targets_and_external_assets(self):
        for extra in (WORK, LINK, "--allow-external"):
            with self.subTest(extra=extra):
                self.assertEqual(parse_links.main(["--retry-pending", extra]), 2)
                self.factory.assert_not_called()
