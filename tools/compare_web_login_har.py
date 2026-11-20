"""Offline comparison of ordinary Douyin Web network captures. No network access."""

import argparse
import base64
import binascii
import hashlib
import json
import re
from pathlib import Path
from urllib.parse import parse_qs, urlsplit


BODY_LIMIT = 8 * 1024 * 1024


def _body(entry):
    response = entry.get("response", {})
    content = response.get("content", {})
    raw = content.get("text")
    if response.get("status") != 200 or not isinstance(raw, str) or len(raw) > BODY_LIMIT:
        return {}
    try:
        if content.get("encoding") == "base64":
            raw = base64.b64decode(raw, validate=True)
        value = json.loads(raw)
        return value if isinstance(value, dict) else {}
    except (ValueError, UnicodeError, binascii.Error, RecursionError):
        return {}


def _issued_digest(video, vid):
    model = video.get("video_model")
    if isinstance(model, str):
        try:
            model = json.loads(model)
        except (ValueError, RecursionError):
            return None
    if not isinstance(model, dict) or model.get("video_id", vid) != vid:
        return None
    url = model.get("fallback_api")
    if isinstance(url, dict):
        url = url.get("fallback_api")
    if isinstance(url, str) and url:
        return hashlib.sha256(url.encode("utf-8", "surrogatepass")).digest()
    return None


def _selector(query):
    original = query.get("force_fids", [])
    source = query.get("stream_type", [])
    if len(original) > 1 or len(source) > 1:
        return "unspecified"
    is_original, is_source = original == ["b3JpZ2luYWw="], source == ["source"]
    if is_original != is_source:
        return "original" if is_original else "source"
    return "unspecified"


def summarize(har, work):
    """Attribute catalogs to a work via its detail VID; retain no addresses or headers."""
    vids, issued, candidates, catalogs = set(), set(), [], []
    for entry in har["log"]["entries"]:
        try:
            u = urlsplit(entry["request"]["url"])
            host = (u.hostname or "").lower()
        except (ValueError, KeyError, TypeError):
            continue
        if u.scheme != "https":
            continue
        if host in ("www.douyin.com", "douyin.com") and u.path.rstrip("/") == "/aweme/v1/web/aweme/detail":
            body = _body(entry)
            detail = body.get("aweme_detail")
            if isinstance(detail, dict) and body.get("status_code") == 0 and str(detail.get("aweme_id")) == work:
                video = detail.get("video")
                addr = video.get("play_addr") if isinstance(video, dict) else None
                vid = addr.get("uri") if isinstance(addr, dict) else None
                if isinstance(vid, str) and vid:
                    vids.add(vid)
                    digest = _issued_digest(video, vid)
                    if digest is not None:
                        issued.add((vid, digest))
        elif host == "snssdk.com" or host.endswith(".snssdk.com"):
            m = re.fullmatch(r"/video/fplay/1/[0-9a-fA-F]{32}/([\w-]{10,128})/?", u.path)
            if m:
                candidates.append((m[1], parse_qs(u.query, keep_blank_values=True), entry))

    unreadable = 0
    requests = {}
    for vid, query, entry in candidates:
        if vid not in vids:
            continue
        digest = hashlib.sha256(entry["request"]["url"].encode("utf-8", "surrogatepass")).digest()
        selector = "issued" if (vid, digest) in issued else _selector(query)
        counts = requests.setdefault(selector, {"total": 0, "unreadable": 0})
        counts["total"] += 1
        body = _body(entry)
        if not body:
            unreadable += 1
            counts["unreadable"] += 1
            continue
        info = body.get("video_info") or {}
        data = info.get("data") if isinstance(info, dict) else None
        if not isinstance(data, dict):
            continue
        codes = (body.get("code"), info.get("code"), data.get("status"))
        if not all(type(code) is int for code in codes) or codes != (0, 0, 10) or data.get("video_id") != vid:
            continue
        rows = data.get("video_list")
        rows = list(rows.values()) if isinstance(rows, dict) else rows
        if not isinstance(rows, list) or not rows:
            continue
        hashes, originals, n, complete = set(), set(), 0, True
        for r in rows:
            if not isinstance(r, dict):
                complete = False
                continue
            meta = r.get("video_meta") or {}
            if not isinstance(meta, dict):
                complete = False
                continue
            outer, inner = r.get("quality"), meta.get("quality")
            outer = outer.lower() if isinstance(outer, str) else None
            inner = inner.lower() if isinstance(inner, str) else None
            known = bool(inner or outer) and not (inner and outer and inner != outer)
            is_original = known and (inner or outer) in ("original", "source")
            n += int(is_original)
            declarations = [h for h in (r.get("file_hash"), meta.get("file_hash")) if h is not None and h != ""]
            if (not declarations or not all(isinstance(h, str) and re.fullmatch(r"[0-9a-fA-F]{32}", h)
                                            for h in declarations)
                    or len({h.lower() for h in declarations}) != 1):
                complete = False
                continue
            h = declarations[0].lower()
            hashes.add(h)
            if is_original:
                originals.add(h)
            complete &= known
        catalogs.append(dict(selector=selector, rows=len(rows), originals=n, hash_complete=complete,
                             hashes=sorted(hashes), original_hashes=sorted(originals)))
    return dict(work=work, detail_matched=bool(vids), catalog_requests_in_capture=len(candidates),
                matched_requests_unreadable=unreadable, selector_requests=requests, catalogs=catalogs,
                verdict="matched_catalog" if catalogs else "no_matched_catalog" if candidates else "no_catalog_request")


def compare(guest, login):
    comparisons = []
    for selector in ("issued", "original", "source"):
        a, b = ([c for c in s["catalogs"] if c["selector"] == selector] for s in (guest, login))
        request_counts = [s["selector_requests"].get(selector, {"total": 0, "unreadable": 0})
                          for s in (guest, login)]
        complete = all(counts["total"] == len(cats) for counts, cats in zip(request_counts, (a, b)))
        ok = bool(a and b and complete and guest["work"] == login["work"] and all(c["hash_complete"] for c in a+b))
        known = {h for c in a for h in c["hashes"]}
        old_originals = {h for c in a for h in c["original_hashes"]}
        new_originals = {h for c in b for h in c["original_hashes"]}
        comparisons.append(dict(selector=selector, status="comparable" if ok else "no_paired_catalog",
                                guest_requests=request_counts[0], logged_requests=request_counts[1],
                                added_original_hashes=sorted(new_originals - known) if ok else [],
                                relabeled_original_hashes=sorted((new_originals & known) - old_originals) if ok else []))
    return comparisons


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("guest_har", type=Path)
    cli.add_argument("logged_har", type=Path)
    cli.add_argument("work_id", nargs="+", help="Works to compare in both captures")
    args = cli.parse_args()
    captures = [json.loads(p.read_text(encoding="utf-8-sig")) for p in (args.guest_har, args.logged_har)]
    for work in args.work_id:
        if not re.fullmatch(r"[0-9]{15,22}", work):
            cli.error("expected a numeric work ID")
        guest, login = (summarize(c, work) for c in captures)
        print(json.dumps(dict(work=work, guest=guest, logged_in=login, comparison=compare(guest, login))))
