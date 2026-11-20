import json
from pathlib import Path
import tempfile
import unittest

from tools.watch_public_player import Capture, write_outputs


class CandidateCaptureTest(unittest.TestCase):
    def test_query_fingerprints_show_rotating_values_without_raw_tokens(self):
        capture = Capture(None, "7708052871413075238")
        initial = capture.query_fingerprints(
            "https://media.example/video.mp4?X-Signature=secret-one&expires=1999999999&tag=a"
        )
        refreshed = capture.query_fingerprints(
            "https://media.example/video.mp4?X-Signature=secret-two&expires=1999999999&tag=a"
        )

        self.assertEqual(set(initial), {"X-Signature", "expires", "tag"})
        self.assertNotEqual(initial["X-Signature"], refreshed["X-Signature"])
        self.assertEqual(initial["expires"], refreshed["expires"])
        self.assertEqual(initial["tag"], refreshed["tag"])
        self.assertNotIn("secret-one", json.dumps(initial))
        self.assertNotIn("secret-two", json.dumps(refreshed))

        duplicate_values = capture.query_fingerprints(
            "https://media.example/video.mp4?tag=first&tag=second"
        )
        reordered_duplicates = capture.query_fingerprints(
            "https://media.example/video.mp4?tag=second&tag=first"
        )
        self.assertEqual(len(duplicate_values["tag"]), 2)
        self.assertEqual(duplicate_values, reordered_duplicates)

    def test_ordinary_match_excluded_and_larger_video_candidate_is_separate(self):
        capture = Capture(None, "7708052871413075238")
        document = "loader-1"
        ordinary_path = capture.label("path", "/ordinary.mp4")
        candidate_path = capture.label("path", "/high-quality.mp4")
        capture.detail.append({
            "doc": "initial",
            "rows": [
                {"gear": "low_720_0", "size": 41_979_651, "paths": [ordinary_path]},
                {"gear": "normal_540_0", "size": 45_992_041, "paths": ["other-path"]},
            ],
        })
        ordinary_url = "https://media.example/ordinary.mp4?signature=ordinary-secret"
        candidate_url = "https://media.example/high-quality.mp4?signature=candidate-secret"
        common = {
            "doc": "initial", "type": "Media", "kind": "video", "status": 200,
            "wire_status": 200, "body_status": "scanned", "tracks": [{"handler": "vide"}],
            "extent": {"total_bytes": 41_979_651},
            "_loader_id": document, "_request_id": "request-ordinary",
            "_declared_expiry": "future", "_bytes": 20,
        }
        capture.rows.append({**common, "n": 1, "path": ordinary_path, "address": "hash-1",
                             "_raw_url": ordinary_url, "outcome": "finished"})
        capture.rows.append({
            **common, "n": 2, "path": candidate_path, "address": "hash-2",
            "extent": {"total_bytes": 120_000_000},
            "_raw_url": candidate_url, "_request_id": "request-candidate",
            "tracks": [{"handler": "vide", "width": 1280, "height": 720}],
            "outcome": "finished",
        })

        candidates = capture.candidate_records()
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0], {
            "url": candidate_url, "request_id": "request-candidate", "document_id": document,
            "size": 120_000_000, "status": 200,
            "track": [{"handler": "vide", "width": 1280, "height": 720}],
            "expiry_assessment": "future",
        })
        main_report = json.dumps(capture.report())
        self.assertNotIn(ordinary_url, main_report)
        self.assertNotIn(candidate_url, main_report)
        self.assertNotIn("candidate-secret", main_report)
        self.assertIn("low_720_0", main_report)

    def test_candidate_output_is_separate_and_only_written_when_nonempty(self):
        candidate = {"url": "https://media.example/high.mp4?sig=raw",
                     "request_id": "request-1", "document_id": "loader-1",
                     "size": 120_000_000, "status": 206,
                     "track": [{"handler": "vide"}], "expiry_assessment": "future"}
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main_path, candidate_path = root / "main.json", root / "candidate.json"
            wrote = write_outputs(main_path, {"observations": []}, candidate_path, [candidate])
            self.assertTrue(wrote)
            main_text = main_path.read_text(encoding="utf8")
            self.assertNotIn(candidate["url"], main_text)
            self.assertEqual(set(json.loads(candidate_path.read_text(encoding="utf8"))[0]),
                             set(candidate))

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main_path, candidate_path = root / "main.json", root / "candidate.json"
            wrote = write_outputs(main_path, {}, candidate_path, [])
            self.assertFalse(wrote)
            self.assertTrue(main_path.exists())
            self.assertFalse(candidate_path.exists())

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            main_path, candidate_path = root / "main.json", root / "candidate.json"
            candidate_path.write_text("occupied", encoding="utf8")
            with self.assertRaises(FileExistsError):
                write_outputs(main_path, {}, candidate_path, [])
            self.assertFalse(main_path.exists())

    def test_reference_sized_mp4_can_be_candidate_without_detail_sizes(self):
        capture = Capture(None, "7708052871413075238")
        capture.rows.append({
            "doc": "initial", "n": 3, "path": "path", "kind": "video",
            "status": 206, "wire_status": 206, "body_status": "scanned",
            "tracks": [{"handler": "vide"}],
            "extent": {"total_bytes": 140_778_272},
            "_raw_url": "https://media.example/original.mp4?expires=1999999999",
            "_request_id": "request-reference", "_loader_id": "loader-1",
            "_declared_expiry": "future",
        })
        self.assertEqual(capture.candidate_records()[0]["size"], 140_778_272)


if __name__ == "__main__":
    unittest.main()
