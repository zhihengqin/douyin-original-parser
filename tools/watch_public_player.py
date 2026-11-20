"""Observe one anonymous public player through one normal reload, without replaying requests.

Example (from the project root, with the project's Playwright environment):
  python -m tools.watch_public_player --seconds 120 --reload-after 50 --output observation.json

Use --work 7707954213745085746 for the known positive control. Each run requires
a new output filename. Browser caching stays enabled. The main report does not
write raw URLs, query values, or header values. Query names and keyed value labels
support comparisons within this run, while URL and path labels compare object
addresses. The optional --candidate-output file contains a raw URL when a
candidate is found and should be kept private.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
from collections import Counter, defaultdict, deque
from datetime import datetime, timezone
import hashlib
import hmac
import json
import os
from pathlib import Path
import re
import sys
import time
from urllib.parse import parse_qsl, urlsplit

ROOT = Path(__file__).resolve().parents[1]
if __package__ in (None, ""):
    sys.path.insert(0, str(ROOT))

from playwright.async_api import Error, async_playwright
from tools.public_player_media_signals import media_kind, mp4_tracks, response_extent
from tools.public_player_reference_mentions import REFERENCES, scan_body


TEXT_LIMIT = 4 * 1024 * 1024
INIT_LIMIT = 64 * 1024
PLAYING_MARK = """(() => {
    if (window !== window.top) return;
    window.__publicPlayerFirst = null;
    document.addEventListener('playing', e => {
      let v = e.target;
      if (window.__publicPlayerFirst || !(v instanceof HTMLVideoElement)) return;
      let r = v.getBoundingClientRect();
      window.__publicPlayerFirst = {epoch_ms: performance.timeOrigin + performance.now(),
        width: v.videoWidth, height: v.videoHeight, has_area: r.width > 0 && r.height > 0};
    }, true);
})()"""


class Capture:
    def __init__(self, client, work):
        self.cdp, self.work = client, work
        self.rows, self.requests, self.detail, self.tasks = [], {}, [], set()
        self.snapshot, self.errors = {}, {}
        self.main_frame = None
        self.navigation, self.loaders = "initial", {}
        self.extra_wait, self.early_extra = defaultdict(deque), defaultdict(deque)
        self.key = os.urandom(32)
        self.sem = asyncio.Semaphore(4)
        self.sealed = False

    def label(self, category, value):
        return hmac.new(self.key, (category + "\0" + value).encode("utf8", "replace"),
                        hashlib.sha256).hexdigest()[:20]

    def query_fingerprints(self, url):
        values = defaultdict(list)
        for name, value in parse_qsl(urlsplit(url).query, keep_blank_values=True):
            values[name].append(self.label("query-value:" + name, value))
        return {name: sorted(tags) for name, tags in sorted(values.items())}

    def start(self, e):
        if self.sealed:
            return
        rid, request = e["requestId"], e["request"]
        previous = self.requests.get(rid) if e.get("redirectResponse") else None
        if previous is not None:
            self.apply_response(previous, e["redirectResponse"])
            previous["outcome"] = "redirect"
            if e.get("redirectHasExtraInfo"):
                self.expect_extra(rid, self.requests[rid])
        url = request.get("url", "")
        u = urlsplit(url)
        # Embedded data is never a new HTTP object.
        if u.scheme not in ("https", "http"):
            self.requests.pop(rid, None)
            return
        loader = e.get("loaderId")
        kind = e.get("type", "Other")
        if (kind == "Document" and e.get("frameId") == self.main_frame
                and loader and loader not in self.loaders):
            n = sum(v.split(":")[0] == self.navigation for v in self.loaders.values()) + 1
            self.loaders[loader] = self.navigation if n == 1 else f"{self.navigation}:{n}"
        row = {"n": len(self.rows) + 1, "doc": self.loaders.get(loader, "unattributed"),
               "type": kind, "start_epoch_ms": round(e["wallTime"] * 1000, 2),
               "path": self.label("path", u.path), "address": self.label("address", url),
               "query_fingerprints": self.query_fingerprints(url),
               "kind": media_kind(kind, "", url), "outcome": "pending", "_bytes": 0,
               "_request_id": rid, "_loader_id": loader, "_raw_url": url}
        if previous is not None:
            row["redirected_from"] = previous["n"]
            previous["redirected_to"] = row["n"]
        # Opaque path fields and relative lifetimes don't establish an expiry instant.
        expires = {int(value) for key, value in parse_qsl(u.query)
                   if key.lower() in {"x-expires", "expires", "url_expire", "expire"}
                   and re.fullmatch(r"[1-9][0-9]{9}", value)}
        row["_declared_expiry"] = ("not_explicit" if not expires else "conflicting" if len(expires) != 1
                                   else "past" if next(iter(expires)) <= e["wallTime"] else "future")
        self.rows.append(row)
        self.requests[rid] = row

    def apply_response(self, row, resp):
        headers = resp.get("headers") or {}
        mime = resp.get("mimeType", "").split(";", 1)[0].strip().lower()
        status = int(resp["status"])
        row.update(status=status, mime=mime if re.fullmatch(r"[a-z0-9.+-]+/[a-z0-9.+-]+", mime) else "",
                   service_worker=bool(resp.get("fromServiceWorker")),
                   kind=media_kind(row["type"], mime, resp.get("url", "")) or row["kind"])
        cached = bool(row.get("cache_event") or resp.get("fromDiskCache") or resp.get("fromPrefetchCache"))
        row["extent"] = response_extent(status, headers, from_cache=cached)

    def response(self, e):
        if (row := self.requests.get(e["requestId"])) is not None:
            self.apply_response(row, e["response"])
            if e.get("hasExtraInfo"):
                self.expect_extra(e["requestId"], row)

    def expect_extra(self, rid, row):
        if self.early_extra.get(rid):
            row["wire_status"] = self.early_extra[rid].popleft()
            if not self.early_extra[rid]:
                del self.early_extra[rid]
        else:
            self.extra_wait[rid].append(row)

    def extra(self, e):
        # Chromium can emit this before the effective response; redirect hops
        # share a request id but each hop has its own FIFO entry.
        rid, status = e["requestId"], int(e["statusCode"])
        if self.extra_wait.get(rid):
            self.extra_wait[rid].popleft()["wire_status"] = status
            if not self.extra_wait[rid]:
                del self.extra_wait[rid]
        elif not self.sealed:
            self.early_extra[rid].append(status)

    def cache(self, e):
        if (row := self.requests.get(e["requestId"])) is not None:
            row["cache_event"] = True
            if "extent" in row:
                row["extent"]["from_cache"] = True

    def data(self, e):
        if (row := self.requests.get(e["requestId"])) is not None:
            row["_bytes"] += max(0, e.get("dataLength", 0))

    def fail(self, e):
        if (row := self.requests.get(e["requestId"])) is not None:
            row["outcome"] = "cancelled" if e.get("canceled") else "failed"

    def finish(self, e):
        rid = e["requestId"]
        row = self.requests.get(rid)
        if not row:
            return
        row["outcome"] = "finished"
        mime = row.get("mime", "")
        extent = row.get("extent", {})
        if mime in ("text/html", "application/xhtml+xml", "application/json", "text/json") or mime.endswith("+json"):
            purpose, limit = "text", TEXT_LIMIT
        elif ((row.get("kind") or mime == "application/octet-stream") and
              (extent.get("range_start") == 0 or row.get("status") == 200)):
            purpose, limit = "init", INIT_LIMIT
        else:
            return
        row["body_purpose"] = purpose
        if row.get("status") not in (200, 206):
            row["body_status"] = "skipped_http_status"
            return
        if max(row["_bytes"], extent.get("content_length") or 0) > limit:
            row["body_status"] = "over_limit"
            return
        if self.sealed:
            row["body_status"] = "after_stop"
            return
        task = asyncio.create_task(self.scan(rid, row, purpose, limit))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)

    async def scan(self, rid, row, purpose, limit):
        try:
            async with self.sem:
                res = await asyncio.wait_for(self.cdp.send("Network.getResponseBody", {"requestId": rid}), 3)
            body = (base64.b64decode(res["body"], validate=True) if res.get("base64Encoded")
                    else res["body"].encode("utf8"))
            if len(body) > limit:
                row["body_status"] = "over_limit"
                return
            row["body_status"] = "scanned"
            if purpose == "init":
                tracks = mp4_tracks(body)
                if tracks:
                    row["tracks"] = tracks
                    row["kind"] = row.get("kind") or "media"
            else:
                hints = scan_body(body, **REFERENCES[self.work])
                if hints["classification"] != "none":
                    row["reference_mentions"] = hints
                if row.get("mime", "").endswith("json") and b'"aweme_detail"' in body:
                    payload = json.loads(body)
                    detail = payload.get("aweme_detail") if isinstance(payload, dict) else None
                    if isinstance(detail, dict) and str(detail.get("aweme_id")) == self.work:
                        self.store_detail(row, detail)
        except (Error, ValueError, TypeError, KeyError, RecursionError, asyncio.TimeoutError) as err:
            row["body_status"] = "unreadable_" + type(err).__name__

    def store_detail(self, row, detail):
        video = detail.get("video")
        if not isinstance(video, dict) or not isinstance(video.get("bit_rate"), list):
            return
        items = []
        for item in video["bit_rate"]:
            if not isinstance(item, dict) or not isinstance(item.get("play_addr"), dict):
                continue
            addr = item["play_addr"]
            paths = {self.label("path", urlsplit(u).path) for u in addr.get("url_list") or []
                     if isinstance(u, str) and u.startswith(("http://", "https://"))}
            gear = item.get("gear_name")
            items.append({"gear": gear if isinstance(gear, str) and re.fullmatch(r"[a-z0-9_]{1,64}", gear) else None,
                          "size": addr.get("data_size") if type(addr.get("data_size")) is int else None,
                          "paths": sorted(paths)})
        self.detail.append({"request": row["n"], "doc": row["doc"], "rows": items})

    def report(self):
        visible, coverage, errors, types, unmatched_opaque = [], Counter(), Counter(), Counter(), 0
        not_modified = 0
        for raw in self.rows:
            row = {k: v for k, v in raw.items() if not k.startswith("_")}
            types[row["type"]] += 1
            coverage[(row.get("body_purpose") or "not_selected") + ":" +
                     (row.get("body_status") or row["outcome"])] += 1
            extent = row.get("extent", {})
            total = extent.get("total_bytes")
            if row.get("mime") == "application/octet-stream" and not row["kind"]:
                unmatched_opaque += 1
            status = row.get("wire_status", row.get("status"))
            if status == 304:
                not_modified += 1
                row["wire_body"] = "not_modified_no_new_body"
            if status in (401, 403, 410):
                errors[str(status)] += 1
            if not (row["kind"] or row.get("reference_mentions") or
                    total == REFERENCES[self.work]["size"] or status in (401, 403, 410)):
                continue
            if row["kind"]:
                row["explicit_url_expiry_at_request"] = raw["_declared_expiry"]
            first = (self.snapshot.get(row["doc"]) or {}).get("first_playing")
            delta = None if not first else round(row["start_epoch_ms"] - first["epoch_ms"], 2)
            row["request_vs_first_playing_ms"] = delta
            row["playback_phase"] = ("unknown" if delta is None else
                                     "indeterminate_near_boundary" if abs(delta) <= 2 else
                                     "before_first_playing" if delta < 0 else "after_first_playing")
            row["reference_size_match"] = total == REFERENCES[self.work]["size"]
            row["same_document_detail_matches"] = sorted({(dr["gear"] or "unlabelled")
                for detail in self.detail if detail["doc"] == row["doc"] and row["doc"] != "unattributed"
                for dr in detail["rows"] if row["path"] in dr["paths"] and total == dr["size"] and total})
            visible.append(row)
        return {"work": self.work, "documents": self.snapshot, "navigation_errors": self.errors,
                "request_counts": dict(types), "body_coverage": dict(coverage),
                "browser_redirect_hops": [
                    {key: row[key] for key in ("n", "doc", "type", "status", "wire_status",
                                                "redirected_from", "redirected_to") if key in row}
                    for row in self.rows if row["outcome"] == "redirect"],
                "unclassified_octet_stream": unmatched_opaque, "wire_or_effective_304": not_modified,
                "http_401_403_410": dict(errors),
                "target_details": self.detail, "observations": visible,
                "limits": "Main-page CDP HTTP(S) only. No replay, no upstream traffic visibility. "
                "The first top-document video playing event is not necessarily the target; inspect dimensions. "
                "Negative delta means before playing, not necessarily speculative preload. "
                "A size match or JSON mention is not a verified original. Path labels exclude host and query; "
                "address labels compare exact addresses within this run only. Status alone does not prove expiry."}

    def candidate_records(self):
        """Return explicit candidate URLs only after body and same-document checks."""
        references = REFERENCES[self.work]
        candidates = []
        for row in self.rows:
            if (not row.get("tracks") or not any(track.get("handler") == "vide"
                                                 for track in row["tracks"])
                    or row.get("status") not in (200, 206)
                    or row.get("wire_status") == 304
                    or row.get("body_status") != "scanned"):
                continue
            total = (row.get("extent") or {}).get("total_bytes")
            if type(total) is not int:
                continue
            ordinary_rows = [
                detail_row
                for detail in self.detail
                if detail["doc"] == row["doc"] and row["doc"] != "unattributed"
                for detail_row in detail["rows"]
            ]
            ordinary_match = any(row["path"] in detail_row["paths"]
                                 and total == detail_row["size"]
                                 for detail_row in ordinary_rows)
            if ordinary_match:
                continue
            ordinary_sizes = [detail_row["size"] for detail_row in ordinary_rows
                              if type(detail_row.get("size")) is int]
            known_original_size = total == references["size"]
            exceeds_all_detail_sizes = bool(ordinary_sizes) and total > max(ordinary_sizes)
            if not (known_original_size or exceeds_all_detail_sizes):
                continue
            candidates.append({
                "url": row["_raw_url"],
                "request_id": row["_request_id"],
                "document_id": row["_loader_id"],
                "size": total,
                "status": row["status"],
                "track": row["tracks"],
                "expiry_assessment": row.get("_declared_expiry", "not_explicit"),
            })
        return candidates


async def run(work, seconds, reload_after):
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT / ".browsers"))
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            ctx = await browser.new_context(locale="zh-CN", timezone_id="Asia/Shanghai",
                                            viewport={"width": 1440, "height": 960})
            await ctx.add_init_script(PLAYING_MARK)
            page = await ctx.new_page()
            client = await ctx.new_cdp_session(page)
            c = Capture(client, work)
            c.main_frame = (await client.send("Page.getFrameTree"))["frameTree"]["frame"]["id"]
            for event, handler in (("requestWillBeSent", c.start), ("responseReceived", c.response),
                                   ("responseReceivedExtraInfo", c.extra),
                                   ("requestServedFromCache", c.cache), ("dataReceived", c.data),
                                   ("loadingFinished", c.finish), ("loadingFailed", c.fail)):
                client.on("Network." + event, handler)
            await client.send("Network.enable", {"maxResourceBufferSize": TEXT_LIMIT,
                                                  "maxTotalBufferSize": TEXT_LIMIT * 8})
            start_time = time.monotonic()
            started = datetime.now(timezone.utc).isoformat()
            for label, deadline in (("initial", reload_after), ("reload", seconds)):
                c.navigation = label
                try:
                    if label == "initial":
                        await page.goto("https://www.douyin.com/video/" + work, wait_until="commit", timeout=20000)
                    else:
                        await page.reload(wait_until="commit", timeout=20000)
                except Error as err:
                    c.errors[label] = type(err).__name__
                await asyncio.sleep(max(0, start_time + deadline - time.monotonic()))
                try:
                    tree = await client.send("Page.getFrameTree")
                    live_doc = c.loaders.get(tree["frameTree"]["frame"].get("loaderId"))
                    state = await page.evaluate("""work => ({on_target: location.pathname === '/video/' + work,
                        verification_title: document.title.includes('\u9a8c\u8bc1'),
                        first_playing: window.__publicPlayerFirst,
                        videos: [...document.querySelectorAll('video')].map(v => ({
                          width: v.videoWidth,height: v.videoHeight,paused: v.paused,
                          seconds: Math.round(v.currentTime)}))})""", work)
                    if label in c.errors or not state["on_target"] or state["verification_title"]:
                        state["first_playing"] = None
                    if live_doc and live_doc.split(":")[0] == label:
                        c.snapshot[live_doc] = state
                    else:
                        c.snapshot[label] = {"unattributed_document": True}
                except Error as err:
                    c.snapshot[label] = {"read_error": type(err).__name__}
            c.sealed = True
            if c.tasks:
                await asyncio.gather(*list(c.tasks))
            result = c.report()
            result.update(started_at_utc=started, seconds_requested=seconds, reload_after=reload_after)
            return result, c.candidate_records()
        finally:
            await browser.close()


def write_outputs(main_path, result, candidate_path=None, candidates=()):
    if main_path.exists():
        raise FileExistsError(main_path)
    if candidate_path is not None and candidate_path.exists():
        raise FileExistsError(candidate_path)
    if candidate_path is not None and candidate_path.resolve() == main_path.resolve():
        raise ValueError("candidate output must differ from main output")
    main_path.parent.mkdir(parents=True, exist_ok=True)
    with main_path.open("x", encoding="utf8") as stream:
        json.dump(result, stream, indent=2, ensure_ascii=True)
        stream.write("\n")
    if candidate_path is not None and candidates:
        candidate_path.parent.mkdir(parents=True, exist_ok=True)
        with candidate_path.open("x", encoding="utf8") as stream:
            json.dump(list(candidates), stream, indent=2, ensure_ascii=True)
            stream.write("\n")
        return True
    return False


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--work", choices=list(REFERENCES), default="7708052871413075238")
    parser.add_argument("--seconds", type=int, default=120, help="total observation time including the reload")
    parser.add_argument("--reload-after", type=int, default=50, help="time from first navigation to normal reload")
    parser.add_argument("--output", type=Path, required=True, help="new path for sanitized JSON")
    parser.add_argument("--candidate-output", type=Path,
                        help="optional separate file for candidate media URLs")
    args = parser.parse_args()
    if not 1 <= args.reload_after < args.seconds <= 86400:
        parser.error("require 1 <= --reload-after < --seconds <= 86400")
    try:
        if args.output.exists():
            parser.error("output already exists")
        if args.candidate_output and args.candidate_output.exists():
            parser.error("candidate output already exists")
        if args.candidate_output and args.candidate_output.resolve() == args.output.resolve():
            parser.error("candidate output must differ from main output")
    except OSError as err:
        parser.error(str(err))
    result, candidates = asyncio.run(run(args.work, args.seconds, args.reload_after))
    has_candidates = write_outputs(args.output, result, args.candidate_output, candidates)
    print("Saved sanitized observation:", args.output.resolve())
    if has_candidates:
        print("Saved candidate media URLs:", args.candidate_output.resolve())


if __name__ == "__main__":
    main()
