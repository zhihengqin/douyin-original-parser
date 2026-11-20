"""Identify media metadata in responses already received by a browser."""
from __future__ import annotations

import re
from collections.abc import Mapping
from urllib.parse import urlsplit

from original_parser.media import boxes, parse_moov


_MANIFEST_MIME = {
    "application/dash+xml", "application/vnd.apple.mpegurl", "application/x-mpegurl",
    "audio/mpegurl", "audio/x-mpegurl", "audio/vnd.apple.mpegurl",
}
_EXTENSIONS = {
    "manifest": {"mpd", "m3u", "m3u8"},
    "video": {"mp4", "m4v", "webm", "mov", "mpeg", "mpg", "ogv", "ts", "m2ts", "flv"},
    "audio": {"m4a", "aac", "mp3", "oga", "opus", "weba", "flac", "wav"},
    "media": {"m4s", "cmfv", "cmfa", "ogg"},
}
_RANGE = re.compile(r"bytes\s+([0-9]{1,20})-([0-9]{1,20})/([0-9]{1,20}|\*)", re.I)


def media_kind(resource_type: str, mime: str, url: str) -> str | None:
    """Classify likely media (including Fetch/XHR) without interpreting URL values.

    A video MIME or extension can still describe an audio-only MP4. Only the
    init segment's track handler establishes what a retrieved container holds.
    """
    m = (mime or "").partition(";")[0].strip().lower()
    if m in _MANIFEST_MIME:
        return "manifest"
    if m.startswith("video/"):
        return "video"
    if m.startswith("audio/"):
        return "audio"
    try:
        _, dot, ext = urlsplit(url or "").path.rsplit("/", 1)[-1].rpartition(".")
        suffix = ext.lower() if dot else ""
    except ValueError:
        suffix = ""
    for kind, extensions in _EXTENSIONS.items():
        if suffix in extensions:
            return kind
    if (resource_type or "").lower() == "media" or m in {"application/mp4", "application/ogg"}:
        return "media"
    return None


def response_extent(status: int, headers: Mapping, *, from_cache: bool = False) -> dict:
    """Separate declared object size from body length; never infer either from traffic volume."""
    fields = {str(k).lower(): str(v).strip() for k, v in headers.items()}
    length = fields.get("content-length", "")
    length = int(length) if re.fullmatch(r"[0-9]{1,20}", length) else None
    result = {
        "total_bytes": None, "range_start": None, "range_end": None,
        "content_length": length, "source": "unknown", "from_cache": from_cache,
    }
    if status == 304:
        result["source"] = "not_modified"
        return result
    if fields.get("content-encoding", "identity").strip().lower() not in {"", "identity"}:
        result["source"] = "encoded_representation"
        return result
    if status == 206:
        match = _RANGE.fullmatch(fields.get("content-range", ""))
        if match:
            start, end = map(int, match.groups()[:2])
            total = None if match[3] == "*" else int(match[3])
            if start <= end and (total is None or end < total) and (
                    length is None or length == end - start + 1):
                result.update(total_bytes=total, range_start=start, range_end=end,
                              source="content_range" if total is not None else "range_total_unknown")
    elif status == 200 and "content-range" not in fields and length is not None:
        result.update(total_bytes=length, source="content_length")
    return result


def mp4_tracks(data: bytes) -> list[dict]:
    """Read complete moov boxes in a small init segment; never fetch missing bytes."""
    if len(data) > 1024 * 1024:
        return []
    for kind, body in boxes(data):
        if kind == b"moov":
            try:
                tracks = parse_moov(body)["tracks"]
            except RecursionError:
                return []
            return [{"handler": t["type"],
                     **{k: t[k] for k in ("width", "height") if t["type"] == "vide" and t.get(k)}}
                    for t in tracks if t.get("type") in {"vide", "soun"}]
    return []
