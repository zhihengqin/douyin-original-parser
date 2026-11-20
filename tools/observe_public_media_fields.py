"""Observe media and completed JSON fetches during an ordinary public page visit.

Only the browser navigates. Never fetch discovered URLs. Reports contain field
paths, short identity digests and counts, not media addresses or raw bodies.
"""

import argparse
from collections import Counter, defaultdict
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from playwright.sync_api import Error, sync_playwright


ROOT = Path(__file__).resolve().parents[1]
MAX_BODY = 4 * 1024 * 1024
ID_KEYS = ("aweme_id", "awemeId", "item_id", "itemId")
TOS = re.compile(r"/video/tos/([^/?#]+/[^/?#]+/[^/?#]+)")
EXT = re.compile(r"\.(?:mp4|webm|m4s|mp3|aac|m4a|m3u8|mpd|ts)$", re.I)


def digest(text):
    return hashlib.sha256(text.encode()).hexdigest()[:24]


def locator(url):
    if not url.startswith(("https://", "http://", "//")):
        return None
    try:
        u = urlsplit(url)
        if not u.hostname:
            return None
    except ValueError:
        return None
    obj = TOS.search(u.path)
    # Exact-URL equality and weaker object-path equality are kept separate.
    return digest(url), digest(obj[1]) if obj else None, bool(obj or EXT.search(u.path))


def field(key):
    return key if re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]{0,48}", key) else "*"


def family(url):
    path = urlsplit(url).path
    return "/".join(field(s) for s in path.split("/") if s)[:140]


def visit(node, work, found, stats, scope="unattributed", path="$", depth=0):
    if depth > 64:
        stats["depth_limit"] += 1
        return
    if isinstance(node, dict):
        ids = {str(node[k]) for k in ID_KEYS if str(node.get(k, "")).isdecimal() and len(str(node[k])) >= 15}
        if ids:
            scope = "target" if ids == {work} else "other_or_mixed"
        for key, value in node.items():
            visit(value, work, found, stats, scope, path + "." + field(key), depth + 1)
    elif isinstance(node, list):
        for value in node:
            visit(value, work, found, stats, scope, path + "[]", depth + 1)
    elif isinstance(node, str):
        val = node.strip()
        loc = locator(val)
        if loc:
            found.add((scope, path, *loc))
        elif val.startswith(("{", "[")):
            try:
                child = json.loads(val)
            except (ValueError, RecursionError):
                return
            stats["nested_json"] += 1
            visit(child, work, found, stats, scope, path + "#json", depth + 1)


def media_kind(mime):
    return mime.startswith(("video/", "audio/")) or mime in {
        "application/dash+xml", "application/vnd.apple.mpegurl", "application/x-mpegurl",
    }


def observe(browser, work, seconds):
    context = browser.new_context(locale="zh-CN", timezone_id="Asia/Shanghai")
    page = context.new_page()
    finished, media = [], set()
    stats, records = Counter(), []
    page_result = {}
    hints = {}

    def response_seen(r):
        mime = r.headers.get("content-type", "").split(";")[0].strip().lower()
        if not media_kind(mime) and r.request.resource_type != "media":
            return
        loc = locator(r.url)
        if loc:
            cr = re.fullmatch(r"bytes \d+-\d+/(\d+)", r.headers.get("content-range", ""))
            key = (loc[0], loc[1], mime, r.status, int(cr[1]) if cr else None)
            media.add(key)
            url = urlsplit(r.url)
            length = r.headers.get("content-length", "")
            hints[key] = dict(
                host=url.hostname, resource_type=r.request.resource_type,
                declared_full_length=int(length) if r.status == 200 and length.isdecimal() else None,
                extension=Path(url.path).suffix.lower() if EXT.search(url.path) else None,
            )

    def completed(req):
        if req.resource_type in {"xhr", "fetch"}:
            finished.append(req)

    page.on("response", response_seen)
    page.on("requestfinished", completed)
    try:
        try:
            doc = page.goto("https://www.douyin.com/video/" + work, wait_until="commit", timeout=30000)
            page_result["navigation_status"] = doc.status if doc else None
        except Error:
            stats["navigation_error"] += 1
        page.wait_for_timeout(seconds * 1000)
        states = page.locator("video").evaluate_all(
            "vs => vs.map(v => ({w:v.videoWidth,h:v.videoHeight,ready:v.readyState,played:v.currentTime>0}))"
        )
        page_result["verification_in_title"] = "\u9a8c\u8bc1" in page.title()
        page_result["on_requested_work_path"] = urlsplit(page.url).path.rstrip("/") == "/video/" + work
        page.remove_listener("requestfinished", completed)
        page.remove_listener("response", response_seen)
        for req in finished:
            stats["completed_fetch_xhr"] += 1
            try:
                response = req.response()
                if not response or not 200 <= response.status < 300:
                    stats["no_success_body"] += 1
                    continue
                mime = response.headers.get("content-type", "").split(";")[0].strip().lower()
                if mime.startswith(("video/", "audio/", "image/", "font/")) or media_kind(mime):
                    stats["media_or_binary_mime"] += 1
                    continue
                size = req.sizes()["responseBodySize"]
                if not 0 <= size <= MAX_BODY:
                    stats["wire_size_limit"] += 1
                    continue
                raw = response.body()
                if len(raw) > MAX_BODY:
                    stats["decoded_size_limit"] += 1
                    continue
                parsed = json.loads(raw)
            except (ValueError, UnicodeError, RecursionError):
                stats["not_json"] += 1
                continue
            except Error:
                stats["body_unavailable"] += 1
                continue
            stats["json_bodies"] += 1
            found = set()
            visit(parsed, work, found, stats)
            records.append((family(req.url), found))
    finally:
        context.close()

    observed_urls = {m[0] for m in media if 200 <= m[3] < 300}
    observed_objects = {m[1] for m in media if m[1] and 200 <= m[3] < 300}
    groups = defaultdict(lambda: defaultdict(set))
    for route, found in records:
        for scope, path, exact, obj, shape in found:
            if shape or exact in observed_urls or (obj and obj in observed_objects):
                g = groups[(route, scope, path)]
                g["identities"].add(obj or exact)
                if exact in observed_urls:
                    g["exact_media_url"].add(exact)
                if obj and obj in observed_objects:
                    g["played_path_only_or_better"].add(obj)
    return {
        "work": work, "window_seconds": seconds, "page": page_result, "stats": stats, "video_elements": states,
        "media": [dict(url_digest=u, object_digest=o, mime=m, status=s, range_total=n, **hints[(u, o, m, s, n)])
                  for u, o, m, s, n in sorted(media, key=str)],
        "json_routes": dict(Counter(r for r, _ in records)),
        "fields": [dict(response_path=r, scope=s, field=p, **{k: sorted(v) for k, v in g.items()})
                   for (r, s, p), g in sorted(groups.items())],
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work", nargs="+", type=str)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--seconds", type=int, default=18, choices=range(5, 61), metavar="5..60")
    args = parser.parse_args()
    if not all(re.fullmatch(r"\d{15,22}", w, re.ASCII) for w in args.work):
        parser.error("expected a numeric work ID")
    args.out.mkdir(parents=True, exist_ok=True)
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".browsers"))
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        try:
            for work in args.work:
                report = observe(browser, work, args.seconds)
                with (args.out / (work + ".json")).open("x", encoding="utf-8") as out:
                    json.dump(report, out, ensure_ascii=True, indent=2)
                print(work, dict(report["stats"]), flush=True)
        finally:
            browser.close()


if __name__ == "__main__":
    main()
