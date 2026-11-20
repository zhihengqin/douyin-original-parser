import json
import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta
from pathlib import Path

from original_parser.web_attempts import WebAttemptJournal


class WebAttemptJournalTests(unittest.TestCase):
    FIRST = "7100000000000000001"
    SECOND = "7100000000000000002"

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "attempts.sqlite3"
        self.journal = WebAttemptJournal(self.path)

    def test_only_latest_decisive_outcome_controls_queue(self):
        record = self.journal.record
        self.assertEqual(self.journal.pending_ids(), [])
        record(self.FIRST, "error")
        self.assertEqual(self.journal.pending_ids(), [])
        record(self.SECOND, "only_transcodes")
        record(self.FIRST, "only_transcodes")
        record(self.FIRST, "only_transcodes")
        record(self.FIRST, "error", error_code="network_error")
        self.assertEqual(WebAttemptJournal(self.path).pending_ids(), [self.SECOND, self.FIRST])
        record(self.FIRST, "success", source_evidence="official_quality", file_size=321)
        record(self.FIRST, "error")
        self.assertEqual(self.journal.pending_ids(), [self.SECOND])
        record(self.FIRST, "only_transcodes")
        self.assertEqual(self.journal.pending_ids(), [self.SECOND, self.FIRST])

    def test_database_contains_only_redacted_typed_fields(self):
        secret = "https://example.invalid/?cookie=secret-value"
        self.journal.record(self.FIRST, "only_transcodes", error_code=secret, catalogs=[
            {"stage": "embedded", "valid": True, "rows": 3, "normal_rows": 3, "source_rows": 0,
             "source_evidence": secret, "max_size_bytes": 232, "unknown_rows": secret},
            {"stage": secret, "rows": 3}, {"stage": "source", "valid": secret, "rows": True},
        ], source_evidence=secret, file_size=123)
        self.journal.record(self.FIRST, "success", source_evidence="official_play_hash", file_size=300)
        self.journal.record(self.SECOND, "success", source_evidence=secret, file_size=secret)
        with closing(sqlite3.connect(self.path)) as db:
            self.assertNotIn(secret, " ".join(db.iterdump()))
            timestamp, code, catalog, evidence, size = db.execute(
                "SELECT attempted_utc,error_code,catalogs_json,source_evidence,file_size "
                "FROM web_attempts WHERE id=1"
            ).fetchone()
            self.assertEqual(datetime.fromisoformat(timestamp).utcoffset(), timedelta(0))
            self.assertEqual(code, "local_error")
            self.assertEqual(json.loads(catalog), [
                {"stage": "embedded", "valid": True, "rows": 3, "normal_rows": 3,
                 "source_rows": 0, "max_size_bytes": 232}, {"stage": "source", "max_size_bytes": None}
            ])
            self.assertEqual((evidence, size), (None, None))
            self.assertEqual(db.execute(
                "SELECT source_evidence,file_size FROM web_attempts WHERE id>=2 ORDER BY id"
            ).fetchall(), [("official_play_hash", 300), (None, None)])

    def test_invalid_ids_and_outcomes_are_rejected_before_database_creation(self):
        for bad_id in ("1" * 14, "1" * 23, "\uff11" * 19, self.FIRST + "\n", "https://" + self.FIRST):
            with self.subTest(id=bad_id), self.assertRaises(ValueError):
                self.journal.record(bad_id, "error")
        with self.assertRaises(ValueError):
            self.journal.record(self.FIRST, "already_in_cache")
        self.assertFalse(self.path.exists())

    def test_storage_errors_propagate(self):
        unavailable = WebAttemptJournal(self.path.parent / "missing" / "attempts.sqlite3")
        with self.assertRaises(sqlite3.Error):
            unavailable.pending_ids()
        with self.assertRaises(sqlite3.Error):
            unavailable.record(self.FIRST, "only_transcodes")
