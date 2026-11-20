"""Local, redacted attempt history for Web original discovery."""

import json
import re
import sqlite3
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path


_WORK_ID = re.compile(r"[0-9]{15,22}")
_STAGES = ("embedded", "original", "source", "issued")
_COUNTS = ("rows", "normal_rows", "original_rows", "source_rows", "unknown_rows")
_EVIDENCE = ("official_quality", "official_play_hash", "official_play_default")
_ERROR_CODES = frozenset("""
    credentials_rejected credentials_required dependency_missing detail_unavailable
    download_failed file_exists hash_mismatch identity_mismatch incomplete_media
    invalid_input invalid_url local_error network_error network_tls_error
    probe_failed size_mismatch source_unavailable upstream_empty_response
    upstream_error upstream_forbidden upstream_non_json upstream_rate_limited
""".split())
_SCHEMA = """
    CREATE TABLE IF NOT EXISTS web_attempts (
        id INTEGER PRIMARY KEY,
        work_id TEXT NOT NULL,
        attempted_utc TEXT NOT NULL,
        outcome TEXT NOT NULL CHECK (outcome IN ('success', 'only_transcodes', 'error')),
        error_code TEXT,
        catalogs_json TEXT NOT NULL,
        source_evidence TEXT,
        file_size INTEGER
    )
"""


def _size(value):
    return value if type(value) is int and 0 < value < 2**63 else None


def _redact_catalogs(catalogs):
    result = []
    for row in catalogs:
        if not isinstance(row, dict) or row.get("stage") not in _STAGES:
            continue
        safe = {"stage": row["stage"]}
        if type(row.get("valid")) is bool:
            safe["valid"] = row["valid"]
        for field in _COUNTS:
            value = row.get(field)
            if type(value) is int and 0 <= value < 2**63:
                safe[field] = value
        safe["max_size_bytes"] = _size(row.get("max_size_bytes"))
        result.append(safe)
    return json.dumps(result, separators=(",", ":"))


class WebAttemptJournal:
    def __init__(self, path):
        self.path = Path(path)

    def record(self, work_id, outcome, *, error_code=None, catalogs=(),
               source_evidence=None, file_size=None):
        if not isinstance(work_id, str) or not _WORK_ID.fullmatch(work_id):
            raise ValueError("invalid work ID")
        if outcome not in ("success", "only_transcodes", "error"):
            raise ValueError("invalid attempt outcome")
        success = outcome == "success"
        error = None
        if not success and error_code is not None:
            error = error_code if isinstance(error_code, str) and error_code in _ERROR_CODES else "local_error"
        evidence = source_evidence if success and source_evidence in _EVIDENCE else None
        values = (work_id, datetime.now(timezone.utc).isoformat(), outcome, error,
                  _redact_catalogs(catalogs), evidence, _size(file_size) if success else None)
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(_SCHEMA)
            db.execute("""
                INSERT INTO web_attempts
                (work_id, attempted_utc, outcome, error_code, catalogs_json, source_evidence, file_size)
                VALUES (?, ?, ?, ?, ?, ?, ?)
            """, values)

    def pending_ids(self):
        """IDs whose last conclusive result had only transcodes, oldest first."""
        with closing(sqlite3.connect(self.path)) as db, db:
            db.execute(_SCHEMA)
            rows = db.execute("""
                SELECT work_id FROM web_attempts WHERE outcome = 'only_transcodes' AND id IN (
                    SELECT MAX(id) FROM web_attempts WHERE outcome != 'error' GROUP BY work_id
                ) ORDER BY id
            """)
            return [work_id for work_id, in rows if isinstance(work_id, str) and _WORK_ID.fullmatch(work_id)]
