"""Read-only documentation of two Web parses. Retain no credentials or full URLs."""

from collections import Counter, defaultdict
from datetime import datetime, timezone, timedelta
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys
import time
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from original_parser import OriginalParser, ParseError


def clock():
    return datetime.now(timezone(timedelta(hours=8))).isoformat(timespec="milliseconds")


def shape(node):
    paths = defaultdict(Counter)

    def walk(n, p):
        paths[p][type(n).__name__] += 1
        if isinstance(n, dict):
            for k, v in n.items():
                k = k if re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]{0,48}", k) else "*"
                walk(v, p + "." + k)
        elif isinstance(n, list):
            for child in n:
                walk(child, p + "[]")
    walk(node, "$")
    return paths


def compare_fields(a, b):
    return {k: "only_success_work" if k not in b else "only_hard_work" if k not in a else
            "same" if a[k] == b[k] else "different" for k in sorted(a.keys() | b.keys())}


def leaves(obj, path="$"):
    if isinstance(obj, dict):
        for key, val in obj.items():
            name = key if re.fullmatch(r"[a-zA-Z_][a-zA-Z0-9_]{0,48}", key) else "*"
            yield from leaves(val, path + "." + name)
        if not obj:
            yield path, {}
    elif isinstance(obj, list):
        for i, val in enumerate(obj):
            yield from leaves(val, f"{path}[{i}]")
        if not obj:
            yield path, []
    else:
        yield path, obj


def observe(p, work, private):
    row = dict(work=work, started=clock(), requests=[])
    read_catalog = p._read_catalog

    def wrapped(url, stage):
        entry = dict(stage=stage, host=urlsplit(url).hostname, started=clock(),
                     initiator=sys._getframe(1).f_code.co_name + " -> _json (Python)")
        row["requests"].append(entry)
        buf = {}
        started = time.perf_counter()

        def received(response, *args, **kw):
            req = response.request
            request_headers = {k.lower(): v for k, v in req.headers.items()}
            response_headers = {k.lower(): v for k, v in response.headers.items()}
            query = parse_qs(urlsplit(req.url).query, keep_blank_values=True)
            entry.update(status=response.status_code, method=req.method,
                         query_keys=sorted(query), has_body=req.body is not None,
                         request_header_names=sorted(request_headers), response_header_names=sorted(response_headers),
                         response_headers={k: response_headers[k] for k in
                         ("content-length","content-type","content-encoding","date","cache-control","age","vary")
                         if k in response_headers}, headers_at_ms=round((time.perf_counter()-started)*1000, 2))
            buf.update(query=query, request_headers=request_headers, response_headers=response_headers)
            # Digest exactly the decoded entity bytes already consumed by the parser, without reading again.
            iterator = response.iter_content
            def tapped(*a, **kw):
                h = hashlib.sha256()
                length = 0
                for chunk in iterator(*a, **kw):
                    h.update(chunk)
                    length += len(chunk)
                    yield chunk
                entry.update(decoded_body_bytes=length, decoded_body_sha256=h.hexdigest(),
                             body_end_ms=round((time.perf_counter()-started)*1000, 2))
            response.iter_content = tapped

        p.session.hooks["response"].append(received)
        try:
            body = read_catalog(url, stage)
            info = body.get("video_info") or {}
            d = info.get("data") or {}
            vs = p._video_rows(d)
            entry.update(code=body.get("code"), inner_code=info.get("code"), catalog_status=d.get("status"),
                         shape=shape(body), rows=[
                         {k: v for k, v in x.items() if
                          (k in ("quality","codec_type","vtype") and isinstance(v,str) and re.fullmatch(r"[a-zA-Z0-9_]{1,30}",v)) or
                          (k in ("size","vwidth","vheight","bitrate") and type(v) is int) or
                          (k=="file_hash" and isinstance(v,str) and re.fullmatch("[0-9a-fA-F]{32}",v))}
                         for x in vs])
            if stage == "original" and buf:
                # Retain values only until both parses finish; write comparisons, not private data.
                buf["response_leaves"] = dict(leaves(body))
                buf["work_specific_path"] = {"path":urlsplit(url).path, "host":urlsplit(url).hostname}
                private[work] = buf
            return body
        finally:
            p.session.hooks["response"].remove(received)
            entry["json_call_ms"] = round((time.perf_counter()-started)*1000, 2)

    with patch.object(p, "_read_catalog", wrapped):
        try:
            data = p.parse(work)["data"]
            row.update(outcome=data["source_evidence"], probe_ok=data["probe"]["ok"])
        except ParseError as e:
            row["outcome"] = e.code
    return row


if __name__ == "__main__":
    cli = argparse.ArgumentParser(description=__doc__)
    cli.add_argument("output", type=Path)
    args = cli.parse_args()
    works = ("7707954213745085746", "7708052871413075238")
    raw, result = {}, dict(works=[], start=clock(), scope="unchanged anonymous Web parser; decoded body digest; no raw credential values; elapsed ms monotonic, not a browser waterfall")
    with args.output.open("x", encoding="utf-8") as f:
        with OriginalParser(refresh_guest_on_rejection=False, allow_external_asset_recovery=False) as parser, \
                patch.object(parser, "_catalog_original_candidate", return_value=None), \
                patch("original_parser.client._remember_original_record"):
            for w in works:
                observed = observe(parser, w, raw)
                result["works"].append(observed)
                print(w, observed["outcome"], len(observed["requests"]), flush=True)
                if observed["outcome"] in ("upstream_rate_limited","upstream_forbidden","credentials_rejected"):
                    break
        if all(w in raw for w in works):
            result["original_request_pair"] = {k: compare_fields(raw[works[0]][k], raw[works[1]][k])
                                               for k in ("work_specific_path","query","request_headers",
                                                         "response_headers","response_leaves")}
        json.dump(result, f, indent=2)
