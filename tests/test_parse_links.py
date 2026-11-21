import io
import json
import tempfile
import unittest
from contextlib import ExitStack, redirect_stderr, redirect_stdout
from pathlib import Path
from unittest.mock import patch

import parse_links
from original_parser import ParseError, cli


WORK = "7700000000000000001"
LINK = f"https://www.douyin.com/video/{WORK}"
MEDIA_URL = "https://media.invalid/file.mp4"


def original_result(evidence="official_quality"):
    row = {"url": MEDIA_URL, "urls": [MEDIA_URL], "size": 1024, "width": 1280, "height": 720,
           "source_evidence": evidence, "official_quality": "original", "quality": "source",
           "file_hash": "abcdef0123456789abcdef0123456789"}
    return {"code": 0, "data": {**row, "aweme_id": WORK, "source_selected": True, "fallback_used": False,
                                "desc": "test", "author": "author", "level": "原画", "size_bytes": 1024,
                                "duration_seconds": 2.0, "video_list": [row],
                                "probe": {"ok": True, "actual_size": 1024, "has_video": True, "has_audio": True,
                                          "duration_seconds": 2.0, "tracks": [{"type": "vide", "width": 1280,
                                                                               "height": 720}, {"type": "soun"}]}}}


class BatchCLITests(unittest.TestCase):
    def setUp(self):
        stack = ExitStack()
        self.addCleanup(stack.close)
        self.output = Path(stack.enter_context(tempfile.TemporaryDirectory())) / "output"
        stack.enter_context(patch.multiple(parse_links, OUTPUT_DIR=self.output, DOWNLOAD=False,
                                           COOKIE_FILE=None, ALLOW_EXTERNAL=None))
        self.stdout = stack.enter_context(redirect_stdout(io.StringIO()))
        self.stderr = stack.enter_context(redirect_stderr(io.StringIO()))
        self.factory = stack.enter_context(patch.object(parse_links, "OriginalParser"))
        self.parser = self.factory.return_value.__enter__.return_value

    def test_verified_identity_returns_only_a_url_without_creating_output_dir(self):
        self.parser.parse.return_value = original_result("official_play_hash")
        self.assertEqual(parse_links.main(["--allow-external", LINK]), 0)
        self.assertIs(self.factory.call_args.kwargs["allow_external_asset_recovery"], True)
        self.assertEqual(self.stdout.getvalue().splitlines(), [MEDIA_URL])
        self.assertEqual(self.stderr.getvalue(), "")
        self.assertFalse(self.output.exists())

    def test_unverified_playback_fails_even_with_download_enabled(self):
        self.parser.parse.return_value = original_result("official_web_pc_bitrate")
        with patch.object(parse_links, "DOWNLOAD", True):
            self.assertEqual(parse_links.main([LINK]), 2)
        self.parser.download.assert_not_called()
        self.assertFalse(self.output.exists())
        self.assertEqual(self.stdout.getvalue(), "")
        self.assertIn(WORK, self.stderr.getvalue())
        self.assertIn("source_unavailable", self.stderr.getvalue())

    def test_mixed_batch_keeps_going_without_echoing_the_signed_url(self):
        first = "https://v.douyin.com/example/?token=private"
        self.parser.parse.side_effect = [ParseError("network_error", f"cannot read {first}"), original_result()]
        self.assertEqual(parse_links.main([first, LINK]), 2)
        self.assertEqual(self.stdout.getvalue().splitlines(), [MEDIA_URL])
        self.assertIn("第 1 个输入", self.stderr.getvalue())
        self.assertNotIn("private", self.stderr.getvalue())
        self.assertFalse(self.output.exists())

    def test_download_prints_only_the_written_file_path(self):
        self.parser.parse.return_value = original_result()
        target = self.output / f"{WORK}_source.mp4"
        self.parser.download.return_value = {"path": str(target), "bytes": 1024}
        with patch.object(parse_links, "DOWNLOAD", True):
            self.assertEqual(parse_links.main([LINK]), 0)
        self.parser.download.assert_called_once_with(self.parser.parse.return_value, target)
        self.assertEqual(self.stdout.getvalue().splitlines(), [str(target)])
        self.assertEqual(self.stderr.getvalue(), "")

    def test_removed_retry_flag_is_rejected_without_side_effects(self):
        self.assertEqual(parse_links.main(["--retry-pending"]), 2)
        self.factory.assert_not_called()
        self.assertFalse(self.output.exists())
        self.assertEqual(self.stdout.getvalue(), "")


class SingleOriginalCLITests(unittest.TestCase):
    def test_legacy_split_result_is_neither_printed_saved_nor_downloaded(self):
        result = original_result()
        result["data"].update(dash_mux_required=True, audio_url="https://media.invalid/audio-only.mp4")
        with tempfile.TemporaryDirectory() as folder, patch.object(cli, "OriginalParser") as factory, \
                redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()) as errors:
            parser = factory.return_value.__enter__.return_value
            parser.parse.return_value = result
            target = Path(folder) / "result.json"
            status = cli.main([LINK, "--json", str(target), "--download", str(target.with_suffix(".mp4"))])
            self.assertEqual(status, 2)
            self.assertEqual(output.getvalue(), "")
            self.assertIsNone(json.loads(errors.getvalue())["data"])
            parser.download.assert_not_called()
            self.assertFalse(target.exists())

    def test_known_identity_detail_is_in_explicit_json_and_stdout_contains_just_url(self):
        with tempfile.TemporaryDirectory() as folder, patch.object(cli, "OriginalParser") as factory, \
                redirect_stdout(io.StringIO()) as output, \
                redirect_stderr(io.StringIO()):
            factory.return_value.__enter__.return_value.parse.return_value = original_result("official_play_hash")
            target = Path(folder) / "result.json"
            self.assertEqual(cli.main([LINK, "--json", str(target)]), 0)
            self.assertEqual(output.getvalue().splitlines(), [MEDIA_URL])
            self.assertEqual(json.loads(target.read_text(encoding="utf-8"))["data"]["source_evidence"],
                             "official_play_hash")

    def test_reference_mismatch_does_not_print_a_success_path(self):
        result = original_result()
        with tempfile.TemporaryDirectory() as folder, patch.object(cli, "OriginalParser") as factory, \
                redirect_stdout(io.StringIO()) as output, redirect_stderr(io.StringIO()):
            parser = factory.return_value.__enter__.return_value
            parser.parse.return_value = result
            path = Path(folder) / "video.mp4"

            def download(ret, dest, *, reference):
                ret["data"]["reference_match"] = False
                record = {"path": str(dest), "sha256": "a" * 64, "reference_match": False}
                ret["data"]["download"] = record
                return record

            parser.download.side_effect = download
            report_path = path.with_suffix(".json")
            self.assertEqual(cli.main([LINK, "--download", str(path), "--reference", str(path.with_suffix(".ref")),
                                       "--json", str(report_path)]), 3)
            self.assertEqual(output.getvalue(), "")
            self.assertFalse(report_path.exists())

    def test_removed_switches_cannot_skip_single_file_checks(self):
        for flag in ("--no-probe", "--allow-source-candidate"):
            with self.subTest(flag=flag), patch.object(cli, "OriginalParser") as factory, \
                    redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as exc:
                cli.main([LINK, flag])
            self.assertEqual(exc.exception.code, 2)
            factory.assert_not_called()
