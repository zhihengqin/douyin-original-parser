import hashlib
import unittest
from unittest.mock import patch

from tools.probe_web_signature_runtime import BDMSTrace, sdk_source_url


class FakeSession:
    def __init__(self, source, *, shift_location=False):
        self.source = source
        self.shift_location = shift_location
        self.calls = []
        self.listeners = []

    def send(self, method, params):
        self.calls.append((method, params))
        if method == "Debugger.getScriptSource":
            return {"scriptSource": self.source}
        if method == "Debugger.setBreakpoint":
            location = dict(params["location"])
            if self.shift_location:
                location["columnNumber"] += 1
            return {"breakpointId": "synthetic-breakpoint", "actualLocation": location}
        if method == "Debugger.removeBreakpoint":
            return {}
        raise AssertionError("unexpected CDP method")

    def on(self, event, callback):
        self.listeners.append((event, callback))


class WebSignatureSdkAliasTests(unittest.TestCase):
    def setUp(self):
        self.alias = "https://example.invalid/web/stable/1.0.1.19-fix.01/bdms.js"
        self.source = "synthetic reviewed SDK bytes"
        self.source_hash = hashlib.sha256(self.source.encode()).hexdigest()
        blocker = patch("requests.sessions.Session.send",
                        side_effect=AssertionError("offline tests must not send HTTP"))
        blocker.start()
        self.addCleanup(blocker.stop)

    def test_bare_and_versioned_bdms_names_are_captured_without_query(self):
        for name in ("bdms.js", "bdms_1.0.1.19_fix.js"):
            with self.subTest(name=name):
                url = "https://example.invalid/web/" + name
                self.assertEqual(sdk_source_url(url + "?token=private#private"), url)
        for name in ("bdms.js.map", "not-bdms.js", "bdms-other.js", "bdms_.js"):
            with self.subTest(name=name):
                self.assertIsNone(sdk_source_url("https://example.invalid/web/" + name))

    def test_alias_keeps_reviewed_hash_and_exact_breakpoint_gate(self):
        session = FakeSession(self.source)
        trace = BDMSTrace(session)
        with patch("tools.decode_bdms_vm.EXPECTED_SHA256", self.source_hash):
            trace.prepare({"7": {"url": self.alias, "script_id": "7"}})
            trace.arm("7700000000000000001")
        self.assertEqual(trace.metadata["status"], "ready")
        self.assertEqual(trace.metadata["source_sha256"], self.source_hash)
        self.assertEqual(trace.metadata["expected_sha256"], self.source_hash)
        method, params = session.calls[-1]
        self.assertEqual(method, "Debugger.setBreakpoint")
        self.assertEqual(params["location"], {
            "scriptId": "7", "lineNumber": 1, "columnNumber": 131911})
        self.assertIn("aid=392139", params["condition"])
        self.assertIn("aweme_id=7700000000000000001", params["condition"])

    def test_alias_with_unknown_source_hash_never_arms(self):
        session = FakeSession(self.source)
        trace = BDMSTrace(session)
        with patch("tools.decode_bdms_vm.EXPECTED_SHA256", "0" * 64):
            trace.prepare({"7": {"url": self.alias, "script_id": "7"}})
            trace.arm("7700000000000000001")
        self.assertEqual(trace.metadata["status"], "unsupported_sdk_version")
        self.assertIsNone(trace.script_id)
        self.assertEqual([method for method, _ in session.calls], ["Debugger.getScriptSource"])
        self.assertEqual(session.listeners, [])

    def test_alias_with_shifted_coordinate_removes_breakpoint(self):
        session = FakeSession(self.source, shift_location=True)
        trace = BDMSTrace(session)
        with patch("tools.decode_bdms_vm.EXPECTED_SHA256", self.source_hash):
            trace.prepare({"7": {"url": self.alias, "script_id": "7"}})
            trace.arm("7700000000000000001")
        self.assertEqual(trace.metadata["status"], "unsupported_breakpoint_location")
        self.assertIsNone(trace.script_id)
        self.assertIsNone(trace.breakpoint_id)
        self.assertEqual(session.calls[-1], (
            "Debugger.removeBreakpoint", {"breakpointId": "synthetic-breakpoint"}))


if __name__ == "__main__":
    unittest.main()
