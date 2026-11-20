"""Compare ordinary Web playback in two isolated browser contexts. Passive requests only."""

import argparse
import asyncio
from collections import Counter
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
from urllib.parse import urlsplit

from playwright.async_api import Error, async_playwright


ROOT = Path(__file__).resolve().parents[1]
WORKS = ("7708052871413075238", "7707954213745085746")


def stamp():
    return datetime.now().astimezone().isoformat(timespec="seconds")


def object_id(url):
    m = re.search(r"/video/tos/([^/?]+/[^/?]+/[^/?]+)", urlsplit(url).path)
    return hashlib.sha256(m[1].encode()).hexdigest()[:24] if m else None


async def observe(ctx, name, work):
    page = await ctx.new_page()
    row = dict(context=name, work=work, started_at=stamp(), details=[], catalogs=[], media=[])
    reqs = Counter()
    replies = []
    vids = set()
    media = set()

    def route(url):
        path = urlsplit(url).path
        if path.rstrip("/").endswith("/aweme/detail"):
            return "detail"
        if "/video/fplay/" in path:
            return "catalog"

    def request(q):
        if k := route(q.url):
            reqs[k] += 1

    def response(r):
        if k := route(r.url):
            replies.append((k, r))
        mime = r.headers.get("content-type", "").lower()
        if mime.startswith(("video/", "audio/")):
            total = re.fullmatch(r"bytes \d+-\d+/(\d+)", r.headers.get("content-range", ""))
            media.add((object_id(r.url), int(total[1]) if total else None, r.status))

    page.on("request", request)
    page.on("response", response)
    try:
        try:
            doc = await page.goto("https://www.douyin.com/video/"+work, wait_until="commit", timeout=30000)
            row["document_status"] = doc.status if doc else None
        except Error as exc:
            row["navigation_error"] = type(exc).__name__
        await page.wait_for_timeout(24000)
        row["ended_at"] = stamp()
        page.remove_listener("request", request)
        page.remove_listener("response", response)
        row["requests"] = dict(reqs)
        row["verification_title"] = "验证" in await page.title()
        row["on_work_path"] = urlsplit(page.url).path.rstrip("/") == "/video/" + work
        row["players"] = await page.locator("video").evaluate_all(
            "(vs)=>vs.map(v=>({w:v.videoWidth,h:v.videoHeight,played:v.currentTime>0}))")
        for k, r in sorted(replies, key=lambda x: x[0] != "detail"):
            item = {"http": r.status}
            row["details" if k == "detail" else "catalogs"].append(item)
            try:
                obj = await asyncio.wait_for(r.json(), 4)
            except (ValueError, Error, asyncio.TimeoutError):
                item["body_readable"] = False
                continue
            if not isinstance(obj, dict):
                continue
            if k == "catalog":
                data = (obj.get("video_info") or {}).get("data") or {}
                item.update(code=obj.get("code"), status=data.get("status"), matches_detail_vid=data.get("video_id") in vids)
                rs = data.get("video_list")
                rs = rs.values() if isinstance(rs, dict) else (rs or [])
                item["explicit_original_rows"] = sum(isinstance(x,dict) and x.get("quality") in ("source","original") for x in rs)
                continue
            detail = obj.get("aweme_detail") or {}
            item.update(code=obj.get("status_code"), work_matches=str(detail.get("aweme_id")) == work)
            if not item["work_matches"] or item["code"] != 0:
                continue
            v = detail.get("video") or {}
            vid = (v.get("play_addr") or {}).get("uri")
            if vid:
                vids.add(vid)
            model = v.get("video_model")
            item["model_nonempty"] = bool(model)
            if isinstance(model,str) and model:
                try:
                    model = json.loads(model)
                except ValueError:
                    pass
            item["model_points_to_fallback"] = bool(model.get("fallback_api")) if isinstance(model,dict) else None
            item["bitrates"] = []
            for br in v.get("bit_rate") or []:
                addr = br.get("play_addr") or {}
                ids = {h for url in addr.get("url_list") or [] if (h := object_id(url))}
                size = addr.get("data_size")
                item["bitrates"].append(dict(
                    gear=br.get("gear_name"), size=size, declared_hash=addr.get("file_hash"),
                    played_object_and_size=any(h in ids and n == size and s == 206 for h,n,s in media)))
        row["media"] = [dict(object_digest=h, range_total=n, status=s) for h,n,s in sorted(media,key=str)]
    finally:
        await page.close()
    return row


async def main(dest):
    os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(ROOT/".browsers"))
    async with async_playwright() as pw:
        browser = await pw.chromium.launch()
        try:
            contexts = [await browser.new_context(locale="zh-CN",timezone_id="Asia/Shanghai",
                                                  viewport={"width":1440,"height":960}) for _ in range(2)]
            rows = []
            for work in WORKS:
                rows.extend(await asyncio.gather(*(observe(c,n,work) for c,n in zip(contexts,("A","B")))))
                print(work,[(r["context"],r["requests"],r["players"]) for r in rows[-2:]],flush=True)
        finally:
            await browser.close()
    with dest.open("x",encoding="utf-8") as f:
        json.dump({"mode":"ordinary desktop navigation, fresh isolated anonymous contexts, no manual API calls",
                   "observations":rows},f,indent=2,ensure_ascii=True)


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output",type=Path)
    asyncio.run(main(cli.parse_args().output))
