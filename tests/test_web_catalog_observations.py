import unittest
from unittest.mock import patch

from original_parser.client import OriginalParser, ParseError


WORK = "7700000000000000001"
VID = "test-video-id"


def response(rows, vid=VID, code=0):
    return {"code": code, "video_info": {"code": 0, "data": {
        "status": 10, "video_id": vid, "video_list": rows}}}


class WebCatalogObservationsTests(unittest.TestCase):
    def setUp(self):
        self.parser = OriginalParser(auto_guest=False)
        self.addCleanup(self.parser.session.close)
        self.normal = {"quality": "normal", "size": 35, "main_url": "SECRET_url"}
        self.detail = {"aweme_id": WORK, "video": {"play_addr": {"uri": VID}, "video_model": {
            "status": 10, "video_id": VID, "video_list": [self.normal]}}}

    def attempt(self, replies, stages=("one", "two")):
        with (patch.object(self.parser, "detail", return_value=self.detail),
              patch.object(self.parser, "_fallback_source_urls", return_value=list(stages)),
              patch.object(self.parser, "_catalog_original_candidate", return_value=None),
              patch.object(self.parser, "_play_default_candidate", return_value=None),
              patch.object(self.parser, "_json", side_effect=replies) as request,
              self.assertRaises(ParseError)):
            self.parser.parse(WORK)
        return request.call_count

    def test_ordinary_selector_evidence_is_counted_and_redacted(self):
        nested = {"video_meta": {"quality": "adapt", "size": "50"}, "backup_url": "SECRET"}
        self.assertEqual(self.attempt([response([nested, self.normal]), response({"a": self.normal})]), 2)
        obs = self.parser.web_catalog_observations
        self.assertEqual([o["stage"] for o in obs], ["embedded", "original", "source"])
        self.assertEqual(obs[1], {"stage": "original", "valid": True, "rows": 2, "normal_rows": 2,
                                  "original_rows": 0, "source_rows": 0, "unknown_rows": 0,
                                  "max_size_bytes": 50})
        self.assertTrue(self.parser.web_catalog_only_transcodes)
        self.assertNotIn("SECRET", str(obs))
        self.assertNotIn(VID, str(obs))
        obs[1]["rows"] = -1
        self.assertTrue(self.parser.web_catalog_only_transcodes)
        self.assertEqual(self.parser.web_attempt_work_id, WORK)
        with self.assertRaises(ParseError):
            self.parser.parse("")
        self.assertIsNone(self.parser.web_attempt_work_id)
        self.assertEqual(self.parser.web_catalog_observations, [])
        self.assertFalse(self.parser.web_catalog_only_transcodes)

    def test_incomplete_selectors_or_invalid_rows_never_mean_only_transcodes(self):
        cases = (
            (response([None, self.normal]),),
            (response([{"quality": "normal", "size": -1}]),),
            (response([{"quality": "unrecognized", "size": 5}]),),
            (response([{"quality": "normal", "size": 3, "video_meta": {"quality": "source"}}]),),
            (response([], code=1),),
            (response([]),),
            (response([self.normal], vid="another-video"),),
            (ParseError("upstream_empty_response", "sensitive upstream error"),),
        )
        for (second,) in cases:
            with self.subTest(second=type(second)):
                self.attempt([response([self.normal]), second])
                self.assertEqual(self.parser.web_catalog_observations[-1]["stage"], "source")
                self.assertFalse(self.parser.web_catalog_only_transcodes)
        self.assertEqual(self.attempt([], stages=()), 0)
        self.assertFalse(self.parser.web_catalog_only_transcodes)
        self.assertEqual(self.attempt([response([self.normal])], stages=("one",)), 1)
        self.assertFalse(self.parser.web_catalog_only_transcodes)

    def test_seen_web_transcode_grades_are_revisitable(self):
        rows = [{"quality": quality, "size": 50} for quality in
                ("normal", "normal", "low", "low", "adapt", "adapt_low", "adapt_lower", "adapt_lowest")]
        self.detail["video"]["video_model"]["video_list"] = rows
        self.attempt([response(rows), response(rows)])
        self.assertTrue(self.parser.web_catalog_only_transcodes)
        self.assertEqual([s["normal_rows"] for s in self.parser.web_catalog_observations], [8, 8, 8])

    def test_declared_original_is_preserved_even_if_unplayable(self):
        self.attempt([response([{"quality": "source"}, {"quality": "original", "size": 500}]),
                      response([self.normal])])
        first_selector = self.parser.web_catalog_observations[1]
        self.assertEqual((first_selector["source_rows"], first_selector["original_rows"]), (1, 1))
        self.assertEqual(first_selector["max_size_bytes"], 500)
        self.assertFalse(self.parser.web_catalog_only_transcodes)
