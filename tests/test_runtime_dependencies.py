"""Dependency failures must be actionable and must never masquerade as no source."""

import builtins
import io
import sys
import unittest
from unittest.mock import patch

from original_parser import check_runtime
from original_parser.client import OriginalParser, ParseError


class RuntimeDependencyTests(unittest.TestCase):
    def test_missing_signer_dependency_identifies_the_service_interpreter(self):
        original_import = builtins.__import__

        def missing_signer(name, *args, **kwargs):
            if name == "abogus":
                raise ModuleNotFoundError("No module named 'gmssl'", name="gmssl")
            return original_import(name, *args, **kwargs)

        with OriginalParser(auto_guest=False) as parser, \
                patch("builtins.__import__", side_effect=missing_signer), \
                patch.object(parser, "_get", side_effect=AssertionError("unexpected HTTP")):
            with self.assertRaises(ParseError) as caught:
                parser._a_bogus_query({"aid": "6383"})
        self.assertEqual(caught.exception.code, "dependency_missing")
        self.assertIn("gmssl", str(caught.exception))
        self.assertIn(sys.executable, str(caught.exception))
        self.assertIn("-m pip install -r", str(caught.exception))

    def test_runtime_check_exercises_signing_without_network_or_catalog(self):
        with patch("requests.sessions.Session.request", side_effect=AssertionError("unexpected HTTP")), \
                patch("original_parser.client._read_original_records", side_effect=AssertionError("unexpected catalog")), \
                patch("original_parser.client.get_guest", side_effect=AssertionError("unexpected browser")):
            check_runtime.check_runtime()

    def test_failed_startup_check_returns_nonzero(self):
        with patch.object(check_runtime, "check_runtime", side_effect=ParseError("dependency_missing", "gmssl")), \
                patch("sys.stderr", new_callable=io.StringIO) as stderr:
            result = check_runtime.main()
        self.assertEqual(result, 1)
        self.assertIn("dependency_missing", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
