"""Audit video references outside video in a saved official Web batch response."""

import argparse
import hashlib
import json
import re
from collections import defaultdict
from pathlib import Path
from urllib.parse import parse_qsl, urlsplit


VID = re.compile(r"(?<![a-zA-Z0-9])v[0-9][a-z0-9]{19,40}(?![a-zA-Z0-9])")


def digest(value):
    return hashlib.sha256(value.encode()).hexdigest()[:20]


def inspect(item):
    video = item.get("video") or {}
    known = (video.get("play_addr") or {}).get("uri")
    results = defaultdict(set)
    urls = defaultdict(set)
    decoded = 0

    def walk(value, path, depth=0):
        nonlocal decoded
        if depth > 50:
            return
        if isinstance(value, dict):
            for key, child in value.items():
                walk(child, path + "." + str(key), depth + 1)
        elif isinstance(value, list):
            for child in value:
                walk(child, path + "[]", depth + 1)
        elif isinstance(value, str):
            text = value.strip()
            if text.startswith(("{", "[")):
                try:
                    parsed = json.loads(text)
                except (ValueError, RecursionError):
                    pass
                else:
                    decoded += 1
                    walk(parsed, path + "<json>", depth + 1)
            try:
                parts = urlsplit(text)
                hostname = parts.hostname
            except ValueError:
                parts = None
                hostname = None
            if parts and parts.scheme in ("http", "https") and hostname:
                if "/video/tos/" in parts.path or hostname.endswith(".douyinvod.com") or hostname == "douyinvod.com":
                    urls[path].add((hostname, "/video/tos/" in parts.path))
                values = [parts.path] + [v for _, v in parse_qsl(parts.query)]
            else:
                values = [text]
            for candidate in values:
                for match in VID.findall(candidate):
                    results[(digest(match), match == known)].add(path)

    for key, value in item.items():
        if key != "video":
            walk(value, "$.'" + key + "'")
    return {"work_id": str(item.get("aweme_id")), "known_video_id_present": bool(known),
            "decoded_json_strings": decoded,
            "video_ids": [{"sha256_prefix": identity, "matches_primary": matches,
                           "paths": sorted(paths)}
                          for (identity, matches), paths in sorted(results.items())],
            "media_url_fields": [{"path": path, "hosts": sorted({host for host, _ in pairs}),
                                  "tos_path_present": any(tos for _, tos in pairs)}
                                 for path, pairs in sorted(urls.items())]}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("response", type=Path)
    args = parser.parse_args()
    data = json.loads(args.response.read_text(encoding="utf-8"))
    items = data.get("aweme_details") or ([data["aweme_detail"]] if data.get("aweme_detail") else [])
    print(json.dumps({"status_code": data.get("status_code"), "items": [inspect(item) for item in items]},
                     ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
