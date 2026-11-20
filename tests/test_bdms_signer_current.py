"""Compare the Python reconstruction to synthetic vectors from the browser VM."""

import json
import contextlib
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.bdms_signer_current import (
    RandomTape, RuntimeInputs, SOURCE_SHA256, main, normalize_browser_fixture,
    sign_current, sm3_bytes, utf16_units,
)


class CurrentBdmsVectorTests(unittest.TestCase):
    def test_current_browser_vectors_and_intermediate_stages(self):
        vectors = json.loads(Path(__file__).with_name("bdms_current_vectors.json").read_text(
            encoding="utf-8"))["vectors"]
        self.assertTrue(vectors)
        for fixture in vectors:
            with self.subTest(vector=fixture["name"]):
                self.assertEqual(fixture["source_sha256"], SOURCE_SHA256)
                tape = RandomTape(fixture["random_values"])
                result = sign_current(
                    fixture["query"], fixture["body"], page_id=fixture["page_id"],
                    aid=fixture["aid"], version=fixture["version"],
                    runtime=RuntimeInputs.from_dict(fixture["runtime"]), random=tape)
                self.assertEqual(result.signature, fixture["expected_signature"])
                self.assertEqual(tape.position, len(fixture["random_values"]))
                for slot, expected in fixture["expected_slots"].items():
                    if slot in {"89", "91", "92"} and isinstance(expected, str):
                        expected = utf16_units(expected)
                    with self.subTest(slot=slot):
                        self.assertEqual(result.intermediates["vm_slots"][slot], expected)

    def test_standard_sm3_reference_vector(self):
        self.assertEqual(bytes(sm3_bytes("abc")).hex(),
                         "66c7f0f462eeedd9d1f2d46bdc10e4e24167c4875cf2f7a2297da02b8f4ba8e0")

    def test_missing_recorded_randomness_fails_instead_of_inventing_state(self):
        tape = RandomTape([0.25])
        self.assertEqual(tape(), 0.25)
        with self.assertRaisesRegex(ValueError, "exhausted"):
            tape()

    def test_raw_capture_normalization_requires_observed_clock_and_provenance(self):
        fixture = json.loads(Path(__file__).with_name("bdms_current_vectors.json").read_text(
            encoding="utf-8"))["vectors"][0]
        runtime = fixture["runtime"]
        dimensions = runtime["dimensions"]
        names = {"innerWidth": "inner_width", "innerHeight": "inner_height",
                 "outerWidth": "outer_width", "outerHeight": "outer_height",
                 "availWidth": "avail_width", "availHeight": "avail_height",
                 "sizeWidth": "screen_width", "sizeHeight": "screen_height", "platform": "platform"}
        slots = dict(fixture["expected_slots"])
        slots.update({"12": runtime["wheel_marker"], "14": runtime["now_ms"],
                      "16": runtime["ua_environment_bits"], "17": runtime["tracking_bits"],
                      "22": runtime["vendor_ink"],
                      "75": {key: dimensions[value] for key, value in names.items()}})
        captured_input = {key: fixture[key] for key in ("query", "body", "page_id", "aid", "version")}
        captured_input.update(signature=fixture["expected_signature"], fixedMs=runtime["date_ms"],
                              randomTape=fixture["random_values"], userAgent=runtime["navigator_user_agent"],
                              before={"browser": runtime["browser_name"],
                                      "previous": runtime["previous_timestamp_ms"],
                                      "counter": runtime["call_count_before"]},
                              permissions={"own": "granted", "ownWritable": False,
                                           "proto": "grnated", "protoWritable": False})
        raw = {"input": captured_input, "captures": [
            {"pc": 1834, "result": fixture["expected_signature"], "slots": slots}]}
        normalized = normalize_browser_fixture(raw, 0, prefix_observation_source="recorded-version-block")
        self.assertEqual(normalized["runtime"], runtime)
        self.assertEqual(normalized["random_values"], fixture["random_values"])
        with self.assertRaisesRegex(ValueError, "provenance"):
            normalize_browser_fixture(raw, 0, prefix_observation_source="")
        with self.assertRaisesRegex(ValueError, "integer"):
            normalize_browser_fixture(raw, None, prefix_observation_source="recorded")
        captured_input.pop("fixedMs")
        with self.assertRaisesRegex(ValueError, "cannot be inferred"):
            normalize_browser_fixture(raw, 0, prefix_observation_source="recorded")

    def test_cli_keeps_signatures_in_explicit_file_and_refuses_overwrite(self):
        fixture = json.loads(Path(__file__).with_name("bdms_current_vectors.json").read_text(
            encoding="utf-8"))["vectors"][0]
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "fixture.json"
            destination = Path(tmp) / "result.json"
            source.write_text(json.dumps(fixture), encoding="utf-8")
            stdout = io.StringIO()
            with patch("sys.argv", ["signer", str(source), "--out", str(destination)]), \
                    contextlib.redirect_stdout(stdout):
                self.assertEqual(main(), 0)
            self.assertNotIn(fixture["expected_signature"], stdout.getvalue())
            self.assertTrue(json.loads(stdout.getvalue())["equal"])
            output = destination.read_text(encoding="utf-8")
            self.assertEqual(json.loads(output)["signature"], fixture["expected_signature"])
            with patch("sys.argv", ["signer", str(source), "--out", str(destination)]), \
                    contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(main(), 2)
            self.assertEqual(destination.read_text(encoding="utf-8"), output)


if __name__ == "__main__":
    unittest.main()
