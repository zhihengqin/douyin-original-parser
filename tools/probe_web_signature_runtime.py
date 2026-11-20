"""Capture the current anonymous web signing chain without exporting session data.

One page fetch per supplied work ID (at most two). This is a research probe, not
an original-media resolver. Loaded SDK sources are saved for offline inspection.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, parse_qsl, urlsplit

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
DETAIL_PATH = "/aweme/v1/web/aweme/detail/"
MAX_SOURCE_BYTES = 2 * 1024 * 1024
MAX_BODY_BYTES = 4 * 1024 * 1024
MAX_SCRIPTS = 32
UIFID_NAMES = {"uifid", "uifid_temp", "uifidtemp"}
SDK_NAMES = re.compile(r"^(?:runtime_bundler_\d+|webmssdk(?:\.es5)?|sdk-glue|bdms(?:_[\w.-]+)?)\.js$")

PAGE_FETCH = r"""({id, key, timeoutMs, maxBytes}) => {
  const state = {done: false, result: null};
  window[key] = state;
  setTimeout(() => {
    const controller = new AbortController();
    let timer, reader;
    let meta = {};
    const work = async () => {
      const response = await window.fetch(
        '/aweme/v1/web/aweme/detail/?aweme_id=' + id + '&aid=392139&device_platform=webapp',
        {credentials: 'include', redirect: 'error', signal: controller.signal});
      meta.http_status = response.status;
      const chunks = [];
      let size = 0;
      if (response.body) {
        reader = response.body.getReader();
        while (true) {
          const {value, done} = await reader.read();
          if (done) break;
          size += value.byteLength;
          if (size > maxBytes) return {...meta, error: 'body_budget_exceeded'};
          chunks.push(value);
        }
      }
      meta.body_bytes = size;
      const raw = new Uint8Array(size);
      let offset = 0;
      for (const chunk of chunks) {raw.set(chunk, offset); offset += chunk.byteLength;}
      let data;
      try {data = JSON.parse(new TextDecoder().decode(raw));}
      catch (_) {return {...meta, json_valid: false, error: 'non_json_response'};}
      const detail = data?.aweme_detail;
      return {...meta, json_valid: true,
        status_code: Number.isInteger(data?.status_code) ? data.status_code : null,
        matching_id: String(detail?.aweme_id) === id,
        has_video_model: !!detail?.video?.video_model};
    };
    const deadline = new Promise(resolve => {
      timer = setTimeout(() => resolve({...meta, error: 'request_timeout'}), timeoutMs);
    });
    Promise.race([Promise.resolve().then(work), deadline]).then(
      result => {state.result = result; state.done = true;},
      () => {state.result = {...meta, error: 'request_failed'}; state.done = true;}
    ).finally(() => {
      clearTimeout(timer);
      try {controller.abort();} catch (_) {}
      try {if (reader) Promise.resolve(reader.cancel()).catch(() => {});} catch (_) {}
    });
  }, 0);
  return true;
}"""


def safe_url(value: str) -> str:
    """Keep only HTTPS origin/path; omit credentials, queries and fragments."""
    try:
        parts = urlsplit(value)
        if parts.scheme != "https" or not parts.hostname:
            return ""
        port = ":" + str(parts.port) if parts.port else ""
        return f"https://{parts.hostname}{port}{parts.path}"
    except (TypeError, ValueError):
        return ""


def sdk_source_url(value: str) -> str | None:
    clean = safe_url(value)
    if clean and SDK_NAMES.fullmatch(urlsplit(clean).path.rsplit("/", 1)[-1]):
        return clean
    return None


def secsdk_match(url: str) -> bool | None:
    """Compare the observed signature using the exact original query bytes."""
    query = urlsplit(url).query
    chunks = query.split("&")
    signature_parts = [part for part in chunks if part.startswith("x-secsdk-web-signature=")]
    values = parse_qs(query)
    if (len(signature_parts) != 1 or len(values.get("uifid", [])) != 1
            or len(values.get("timestamp", [])) != 1):
        return None
    signature = signature_parts[0].partition("=")[2]
    if not re.fullmatch(r"[a-fA-F0-9]{32}", signature):
        return False
    unsigned = "&".join(part for part in chunks if not part.startswith("x-secsdk-web-signature="))
    text = (values["uifid"][0] + "_" + values["timestamp"][0]
            + "_A96D855A08C0A9707F8BEF0D9A527E4E_" + unsigned)
    return hashlib.md5(text.encode()).hexdigest() == signature.lower()


def safe_stack(stack: dict | None, depth: int = 0) -> dict:
    if not isinstance(stack, dict) or depth >= 4:
        return {}
    frames = []
    for frame in stack.get("callFrames", [])[:40]:
        frames.append({"function_name": str(frame.get("functionName", ""))[:160],
                       "script_id": str(frame.get("scriptId", ""))[:32],
                       "url": safe_url(frame.get("url", "")),
                       "line_0based": frame.get("lineNumber"),
                       "column_0based": frame.get("columnNumber")})
    result = {"frames": frames}
    if stack.get("parent"):
        result["parent"] = safe_stack(stack["parent"], depth + 1)
    return result


def request_summary(event: dict, work_ids: list[str]) -> dict | None:
    request = event.get("request", {})
    raw_url = request.get("url", "")
    parts = urlsplit(raw_url)
    if (parts.scheme != "https" or parts.hostname != "www.douyin.com"
            or parts.path != DETAIL_PATH):
        return None
    params = parse_qs(parts.query)
    work = params.get("aweme_id", [""])[0]
    if work not in work_ids or params.get("aid") != ["392139"]:
        return None
    names = [name for name, _ in parse_qsl(parts.query, keep_blank_values=True)]
    return {"work_id": work, "request_id": str(event.get("requestId", ""))[:64],
            "url": safe_url(raw_url), "method": request.get("method"),
            "query_keys": [name for name in names if re.fullmatch(r"[\w.-]{1,80}", name)],
            "header_names": sorted(name for name in request.get("headers", {})
                                   if re.fullmatch(r"[\w-]{1,80}", name)),
            "secsdk_formula_matches": secsdk_match(raw_url),
            "initiator_type": event.get("initiator", {}).get("type"),
            "initiator_stack": safe_stack(event.get("initiator", {}).get("stack"))}


def write_json(path: Path, value) -> None:
    with path.open("x", encoding="utf-8") as stream:
        json.dump(value, stream, ensure_ascii=False, indent=2)
        stream.write("\n")


def save_sdk_sources(session, scripts: dict[str, dict], destination: Path) -> list[dict]:
    saved = []
    for script in list(scripts.values()):
        item = dict(script)
        try:
            if isinstance(item["length_hint"], int) and item["length_hint"] > MAX_SOURCE_BYTES:
                item["error"] = "source_budget_exceeded"
            else:
                source = session.send("Debugger.getScriptSource", {
                    "scriptId": item["script_id"]})["scriptSource"].encode("utf-8")
                if len(source) > MAX_SOURCE_BYTES:
                    item["error"] = "source_budget_exceeded"
                else:
                    name = item["script_id"] + "-" + urlsplit(item["url"]).path.rsplit("/", 1)[-1]
                    with (destination / name).open("xb") as stream:
                        stream.write(source)
                    item.update(file=name, bytes=len(source), sha256=hashlib.sha256(source).hexdigest())
        except Exception as exc:
            item["error"] = type(exc).__name__
        saved.append(item)
    return saved


class BDMSTrace:
    """Observe two reviewed VM boundaries, only in the exact decoded SDK build."""

    def __init__(self, session):
        self.session = session
        self.metadata = {"status": "not_started", "hit_limit": 4, "errors": []}
        self.records = []
        self.script_id = None
        self.breakpoint_id = None
        self.active_id = None
        self.listening = False

    def prepare(self, scripts):
        from tools.decode_bdms_vm import EXPECTED_SHA256

        candidates = [item for item in scripts.values()
                      if (name := urlsplit(item["url"]).path.rsplit("/", 1)[-1]) == "bdms.js"
                      or name.startswith("bdms_")]
        if not candidates:
            self.metadata["status"] = "unsupported_no_bdms"
            return
        candidate = candidates[-1]
        source = self.session.send("Debugger.getScriptSource", {
            "scriptId": candidate["script_id"]})["scriptSource"]
        digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
        self.metadata.update(source_sha256=digest, expected_sha256=EXPECTED_SHA256,
                             script_id=candidate["script_id"])
        if digest != EXPECTED_SHA256:
            self.metadata["status"] = "unsupported_sdk_version"
            return
        self.script_id = candidate["script_id"]
        self.session.on("Debugger.paused", self.on_pause)
        self.listening = True
        self.metadata["status"] = "ready"

    def arm(self, work):
        self.disarm()
        self.active_id = work
        if not self.script_id or len(self.records) >= 4:
            return
        # The ID has already passed the CLI digit-only validation. JSON quoting
        # also keeps this safe when used through the Python API.
        marker = json.dumps("aweme_id=" + work)
        generator = ("o.length===1834 && a===144 && typeof s[1][3]==='string'"
                     f" && s[1][3].includes({marker}) && s[1][3].includes('aid=392139')")
        wrapper = ("o.length===305 && a===304 && typeof e[0]==='string'"
                   f" && e[0].includes({marker}) && e[0].includes('aid=392139')")
        reply = self.session.send("Debugger.setBreakpoint", {
            "location": {"scriptId": self.script_id, "lineNumber": 1, "columnNumber": 131911},
            "condition": f"({generator}) || ({wrapper})"})
        self.breakpoint_id = reply["breakpointId"]
        self.metadata["actual_location"] = reply.get("actualLocation")
        expected = {"scriptId": self.script_id, "lineNumber": 1, "columnNumber": 131911}
        if reply.get("actualLocation") != expected:
            self.disarm()
            self.script_id = None
            self.metadata["status"] = "unsupported_breakpoint_location"

    def on_pause(self, event):
        try:
            if (self.breakpoint_id not in event.get("hitBreakpoints", [])
                    or len(self.records) >= 4):
                return
            frame = event["callFrames"][0]
            reply = self.session.send("Debugger.evaluateOnCallFrame", {
                "callFrameId": frame["callFrameId"], "returnByValue": True,
                "expression": """JSON.stringify({pc:a, bytecode:o, exceptions:u, strict:i,
                  native_callee_name: typeof n === 'function' ? n.name : '',
                  native_callee_source_length: String(n).length,
                  native_argument_count:e.length,
                  query_ends_with_dhzx: a===144 ?
                    typeof e[0]==='string' && e[0].endsWith('dhzx') : null})"""})
            if reply.get("exceptionDetails"):
                self.metadata["errors"].append("frame_evaluation_failed")
                return
            snapshot = json.loads(reply["result"]["value"])
            if (snapshot.get("pc") not in (144, 304)
                    or not isinstance(snapshot.get("bytecode"), list)
                    or len(snapshot["bytecode"]) not in (1834, 305)
                    or not all(type(word) is int for word in snapshot["bytecode"])):
                self.metadata["errors"].append("unexpected_vm_shape")
                return
            snapshot["native_callee_name"] = str(snapshot.get("native_callee_name", ""))[:160]
            snapshot["work_id"] = self.active_id
            snapshot["frames"] = [
                {"name": str(item.get("functionName", ""))[:160],
                 "scriptId": item["location"].get("scriptId"),
                 "lineNumber": item["location"].get("lineNumber"),
                 "columnNumber": item["location"].get("columnNumber")}
                for item in event["callFrames"][:6]]
            self.records.append(snapshot)
            if len(self.records) >= 4:
                self.disarm()
        except Exception as exc:
            self.metadata["errors"].append(type(exc).__name__)
        finally:
            try:
                self.session.send("Debugger.resume")
            except Exception as exc:
                self.metadata["errors"].append("resume_" + type(exc).__name__)

    def disarm(self):
        if self.breakpoint_id:
            key, self.breakpoint_id = self.breakpoint_id, None
            try:
                self.session.send("Debugger.removeBreakpoint", {"breakpointId": key})
            except Exception as exc:
                self.metadata["errors"].append("remove_" + type(exc).__name__)

    def close(self, work_ids):
        self.disarm()
        if self.listening:
            try:
                self.session.remove_listener("Debugger.paused", self.on_pause)
            except Exception as exc:
                self.metadata["errors"].append("listener_" + type(exc).__name__)
        if self.script_id:
            complete = all({record["pc"] for record in self.records
                            if record["work_id"] == work} == {144, 304} for work in work_ids)
            self.metadata["status"] = ("captured" if complete and not self.metadata["errors"]
                                       else "incomplete")
        self.metadata["hits"] = len(self.records)
        return self.metadata


def run_probe(work_ids: list[str], destination: Path, timeout_seconds: int,
              *, trace_bdms: bool = False) -> dict:
    # Import lazily so --help and offline helpers do not require a browser.
    from playwright.sync_api import TimeoutError as BrowserTimeout, sync_playwright

    browsers = ROOT / ".browsers"
    if browsers.is_dir():
        os.environ.setdefault("PLAYWRIGHT_BROWSERS_PATH", str(browsers))
    report = {"schema_version": 1,
              "recorded_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
              "outcome": "inconclusive", "work_ids": work_ids,
              "explicit_fetch_budget": len(work_ids), "requests": [], "results": [],
              "sdk_sources": [], "errors": [],
              "limits": ["video page initialization and background requests are additional",
                         "no original-media discovery or media verification",
                         "signature equality does not establish server enforcement"]}
    scripts: dict[str, dict] = {}
    attempted_ids: set[str] = set()
    stage = "browser_launch"
    with sync_playwright() as playwright:
        browser = None
        session = None
        trace = None
        try:
            browser = playwright.chromium.launch(headless=True, channel="chromium", timeout=20000)
            context = browser.new_context(locale="zh-CN", timezone_id="Asia/Shanghai",
                                          viewport={"width": 1440, "height": 900})
            page = context.new_page()
            session = context.new_cdp_session(page)

            def on_script(event):
                source_url = sdk_source_url(event.get("url", ""))
                script_id = str(event.get("scriptId", ""))
                if (source_url and script_id.isdigit()
                        and (script_id in scripts or len(scripts) < MAX_SCRIPTS)):
                    scripts[script_id] = {"url": source_url, "script_id": script_id,
                                          "length_hint": event.get("length"),
                                          "start_line_0based": event.get("startLine"),
                                          "start_column_0based": event.get("startColumn")}
                elif source_url and script_id not in scripts:
                    report["script_capture_truncated"] = True

            def on_request(event):
                summary = request_summary(event, work_ids)
                if summary and len(report["requests"]) < 16:
                    report["requests"].append(summary)
                elif summary:
                    report["request_capture_truncated"] = True

            session.on("Debugger.scriptParsed", on_script)
            session.on("Network.requestWillBeSent", on_request)
            session.send("Network.enable")
            session.send("Debugger.enable")
            stage = "entry_navigation"
            report["entry_url"] = "https://www.douyin.com/video/" + work_ids[0]
            response = page.goto(report["entry_url"], wait_until="domcontentloaded", timeout=30000)
            report["entry_http_status"] = response.status if response else None
            if response and response.status in (403, 429, 444):
                report["errors"].append({"stage": stage, "error": "entry_rejected"})
            else:
                stage = "sdk_ready"
                page.wait_for_function("""() => typeof window.bdms === 'object'
                    && typeof window.fetch === 'function'
                    && document.cookie.split(';').some(part =>
                      /^(uifid|uifid_temp|uifidtemp)$/i.test(part.trim().split('=')[0]))""",
                                       timeout=30000, polling=250)
                jar_names = {cookie["name"].lower()
                             for cookie in context.cookies("https://www.douyin.com/")}
                report["uifid_present"] = bool(jar_names & UIFID_NAMES)
                report["bdms_ready"] = True
                if trace_bdms:
                    stage = "trace_setup"
                    trace = BDMSTrace(session)
                    trace.prepare(scripts)
                stage = "page_fetch"
                for work in work_ids:
                    if trace:
                        trace.arm(work)
                    key = "__signatureProbe_" + uuid.uuid4().hex
                    attempted_ids.add(work)
                    page.evaluate(PAGE_FETCH, {"id": work, "key": key,
                                               "timeoutMs": timeout_seconds * 1000,
                                               "maxBytes": MAX_BODY_BYTES})
                    try:
                        handle = page.wait_for_function(
                            "key => window[key]?.done ? window[key].result : false",
                            arg=key, timeout=timeout_seconds * 1000 + 5000, polling=100)
                        result = handle.json_value()
                        handle.dispose()
                    except BrowserTimeout:
                        result = {"error": "browser_wait_timeout"}
                    result["work_id"] = work
                    result["accepted"] = bool(result.get("http_status") == 200
                                               and result.get("status_code") == 0
                                               and result.get("matching_id"))
                    report["results"].append(result)
                    if not result["accepted"]:
                        break
        except Exception as exc:
            # Browser errors can embed full URLs; only report the class and stage.
            report["errors"].append({"stage": stage, "error": type(exc).__name__})
        finally:
            try:
                if trace:
                    report["bdms_trace"] = trace.close(work_ids)
                    write_json(destination / "executed-vm.json", trace.records)
                elif trace_bdms:
                    report["bdms_trace"] = {"status": "not_started", "hits": 0}
                if session:
                    report["sdk_sources"] = save_sdk_sources(session, scripts, destination)
            finally:
                if browser:
                    try:
                        browser.close()
                    except Exception as exc:
                        report["errors"].append({"stage": "browser_close", "error": type(exc).__name__})
    captured_ids = {request["work_id"] for request in report["requests"]}
    report["explicit_fetch_attempts"] = len(attempted_ids)
    report["not_requested"] = [work for work in work_ids if work not in attempted_ids]
    if (len(report["results"]) == len(work_ids)
            and all(result["accepted"] for result in report["results"])
            and captured_ids == set(work_ids) and report["sdk_sources"]
            and not report["errors"]
            and not report.get("script_capture_truncated")
            and not report.get("request_capture_truncated")
            and (not trace_bdms or report["bdms_trace"]["status"] == "captured")
            and not any(item.get("error") for item in report["sdk_sources"])):
        report["outcome"] = "captured_matching_details"
    return report


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("work_ids", nargs="+", help="one or two public work IDs")
    parser.add_argument("--out", required=True, type=Path, help="new output directory; must not exist")
    parser.add_argument("--timeout", type=int, default=20, help="fetch deadline in seconds (5-45)")
    parser.add_argument("--trace-bdms", action="store_true",
                        help="capture two VM boundaries only for the reviewed SDK SHA-256")
    args = parser.parse_args(argv)
    if not 1 <= len(args.work_ids) <= 2 or len(set(args.work_ids)) != len(args.work_ids):
        parser.error("provide one or two distinct work IDs")
    if not all(re.fullmatch(r"\d{15,22}", value) for value in args.work_ids):
        parser.error("work IDs must contain 15-22 digits")
    if not 5 <= args.timeout <= 45:
        parser.error("--timeout must be between 5 and 45")
    try:
        args.out.mkdir(parents=True, exist_ok=False)
    except FileExistsError:
        parser.error("--out already exists; use a new directory")
    try:
        report = run_probe(args.work_ids, args.out, args.timeout, trace_bdms=args.trace_bdms)
    except Exception as exc:
        report = {"outcome": "inconclusive", "errors": [{"error": type(exc).__name__}]}
    write_json(args.out / "summary.json", report)
    print(json.dumps({"outcome": report["outcome"], "report": str(args.out / "summary.json")},
                     ensure_ascii=False))
    return 0 if report["outcome"] == "captured_matching_details" else 2


if __name__ == "__main__":
    sys.exit(main())
