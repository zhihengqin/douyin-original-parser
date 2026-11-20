"""Summarize saved JSON catalogs offline without emitting URLs or credentials."""

import argparse
import hashlib
import json
from pathlib import Path


QUALITIES = frozenset({"original", "source", "normal", "low", "high", "adapt",
                      "adapt_low", "adapt_lowest", "adapt_lower", "adapt_high"})


def audit(payload, *, work_id, video_id, expected_size):
    catalogs = []

    def walk(value, path="$", identity="unverified"):
        if isinstance(value, list):
            for index, entry in enumerate(value):
                walk(entry, f"{path}[{index}]", identity)
            return
        if not isinstance(value, dict):
            return
        for key, target in (("aweme_id", work_id), ("video_id", video_id)):
            if value.get(key):
                identity = "matched" if str(value[key]) == target else "different"
        rows = value.get("video_list")
        if isinstance(rows, (dict, list)):
            entries = list(rows.values()) if isinstance(rows, dict) else rows
            summary = []
            for index, row in enumerate(entries):
                if not isinstance(row, dict):
                    continue
                meta = row.get("video_meta")
                metadata = {**row, **meta} if isinstance(meta, dict) else row
                size = metadata.get("size")
                size = size if type(size) is int and size >= 0 else None
                quality = metadata.get("quality")
                quality = quality if isinstance(quality, str) and quality in QUALITIES else "other"
                summary.append({"index": index, "quality": quality, "size": size,
                                "expected_size_match": size == expected_size})
            catalogs.append({"path": path + ".video_list", "identity": identity,
                             "rows": summary})
        for key, entry in value.items():
            if key == "video_model" and isinstance(entry, str):
                try:
                    entry = json.loads(entry)
                except (ValueError, RecursionError):
                    continue
            # Only fixed field names are emitted; arbitrary keys may contain secrets.
            child_path = path + ("." + key if key in {"aweme_detail", "video", "video_model",
                                                     "video_info", "data"} else ".<field>")
            if isinstance(entry, (dict, list)):
                walk(entry, child_path, identity)

    walk(payload)
    return catalogs


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", type=Path, nargs="+")
    parser.add_argument("--work-id", required=True)
    parser.add_argument("--video-id", required=True)
    parser.add_argument("--expected-size", type=int, required=True)
    args = parser.parse_args(argv)
    results = []
    for path in args.files:
        raw = path.read_bytes()
        try:
            payload = json.loads(raw)
        except (ValueError, UnicodeError, RecursionError):
            results.append({"file": str(path), "error": "invalid_json"})
            continue
        catalogs = audit(payload, work_id=args.work_id, video_id=args.video_id,
                         expected_size=args.expected_size)
        results.append({"file": str(path), "sha256": hashlib.sha256(raw).hexdigest(),
                        "catalogs": catalogs})
    print(json.dumps({"network_requests": 0, "files": results}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
