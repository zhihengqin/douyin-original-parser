"""Regressions for issued inline models and continued official-source discovery."""
import io
import json
import unittest
from unittest.mock import patch

from original_parser.client import OriginalParser, ParseError, check_url


WORK = "7700000000000000001"
VID = "v03033g10000testsource"
CDN = "https://v3-dy-o.zjcdn.com/"


def source_row(path="source.mp4", quality="original", size=1000):
    return {"main_url": CDN + path, "quality": quality, "size": size,
            "vtype": "mp4", "vwidth": 1920, "vheight": 1080,
            "bitrate": 4000, "file_id": VID}


def model(rows=None):
    return {"status": 10, "video_id": VID, "video_duration": 2,
            "video_list": rows or [], "fallback_api": {"fallback_api":
                f"https://vas-lf-x.snssdk.com/video/fplay/1/{'0' * 32}/{VID}?aid=392139"}}


def detail(rows=None):
    return {"aweme_id": WORK, "video": {"duration": 2000,
            "play_addr": {"uri": VID, "data_size": 500},
            "video_model": json.dumps(model(rows))}}


def payload(rows):
    return {"code": 0, "video_info": {"code": 0, "data": model(rows)}}


class Raw(io.BytesIO):
    def read(self, size=-1, **kwargs):
        return super().read(size)


class RangeResponse:
    def __init__(self, size=1000, status=206):
        self.status_code = status
        self.headers = {"Content-Range": f"bytes 0-15/{size}"}
        self.raw = Raw(b"\x00\x00\x00\x10ftypisom0000")
        self.url = CDN + "default.mp4"

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.raw.close()


class SourcePipelineTests(unittest.TestCase):
    def test_inline_original_works_without_fallback_or_extra_request(self):
        row = source_row()
        nested = {"main_url": row.pop("main_url"), "video_meta": row}
        work = detail()
        inline = model([nested])
        del inline["fallback_api"]
        work["video"]["video_model"] = json.dumps(inline)
        with OriginalParser(auto_guest=False) as parser, patch.object(parser, "_json") as request:
            _, candidates = parser.source_streams(work)
        self.assertEqual(candidates[0]["official_quality"], "original")
        self.assertEqual(candidates[0]["size"], 1000)
        self.assertEqual(candidates[0]["url"], CDN + "source.mp4")
        request.assert_not_called()

    def test_outer_encryption_and_conflicting_quality_cannot_be_overridden(self):
        cases = [{"encrypt": True}, {"spade_a": "secret"}, {"quality": "normal"}]
        for outer in cases:
            row = {"main_url": CDN + "source.mp4",
                   "video_meta": {**source_row(), "encrypt": 0}, **outer}
            with self.subTest(outer=outer), OriginalParser(auto_guest=False) as parser:
                with self.assertRaises(ParseError):
                    parser._source_candidates(payload([row]), VID)

    def test_model_video_identity_must_match_even_with_original_row(self):
        work = detail([source_row()])
        inline = json.loads(work["video"]["video_model"])
        inline["video_id"] = "another_video"
        work["video"]["video_model"] = inline
        with OriginalParser(auto_guest=False) as parser, patch.object(parser, "_json") as request:
            with self.assertRaises(ParseError) as caught:
                parser.source_streams(work)
        self.assertEqual(caught.exception.code, "identity_mismatch")
        request.assert_not_called()

    def test_transcode_sizes_include_wrapped_model_but_exclude_declared_original(self):
        work = detail([{"video_meta": source_row(quality="low", size=700)},
                       {"video_meta": source_row(size=900)}])
        self.assertEqual(OriginalParser._transcode_sizes(work["video"]), {500, 700})

    def test_default_matching_extra_fplay_transcode_is_rejected(self):
        with OriginalParser(auto_guest=False) as parser, \
                patch.object(parser, "_json", return_value=payload([source_row(quality="low", size=700)])), \
                patch.object(parser, "_catalog_original_candidate", return_value=None), \
                patch.object(parser, "_a_bogus_query", return_value="ratio=default"), \
                patch.object(parser, "_get", return_value=RangeResponse(700)):
            with self.assertRaises(ParseError) as caught:
                parser.source_streams(detail())
        self.assertEqual(caught.exception.code, "source_unavailable")
        self.assertIn("转码档字节数完全相同", str(caught.exception))

    def test_missing_model_does_not_prevent_independent_default_dispatch(self):
        work = detail()
        del work["video"]["video_model"]
        with OriginalParser(auto_guest=False) as parser, \
                patch.object(parser, "_json") as request, \
                patch.object(parser, "_catalog_original_candidate", return_value=None), \
                patch.object(parser, "_a_bogus_query", return_value="ratio=default"), \
                patch.object(parser, "_get", return_value=RangeResponse()):
            _, candidates = parser.source_streams(work)
        self.assertEqual(candidates[0]["source_evidence"], "official_play_default")
        request.assert_not_called()

    def test_parse_continues_from_broken_inline_and_first_route_to_second(self):
        responses = [payload([source_row("expired.mp4")]), payload([source_row("valid.mp4")])]
        media = {"ok": True, "duration_seconds": 2, "has_video": True, "has_audio": True}
        with OriginalParser(auto_guest=False) as parser, \
                patch.object(parser, "detail", return_value=detail([source_row("inline-expired.mp4")])), \
                patch.object(parser, "_json", side_effect=responses) as request, \
                patch.object(parser, "probe", side_effect=[ParseError("probe_failed", "expired inline"),
                    ParseError("probe_failed", "expired fplay"), media]) as probe, \
                patch("original_parser.client._remember_original_record"):
            result = parser.parse(WORK)
        self.assertEqual(result["data"]["url"], CDN + "valid.mp4")
        self.assertEqual(len(result["data"]["video_list"]), 1)
        self.assertEqual(request.call_count, 2)
        self.assertEqual(probe.call_count, 3)

    def test_failed_exact_url_is_not_probed_again_across_routes(self):
        response = payload([source_row()])
        media = {"ok": True, "duration_seconds": 2}
        with OriginalParser(auto_guest=False) as parser, \
                patch.object(parser, "detail", return_value=detail([source_row()])), \
                patch.object(parser, "_json", side_effect=[response, payload([source_row("fresh.mp4")])]), \
                patch.object(parser, "probe", side_effect=[ParseError("probe_failed", "expired"), media]) as probe, \
                patch("original_parser.client._remember_original_record"):
            result = parser.parse(WORK)
        self.assertEqual(result["data"]["url"], CDN + "fresh.mp4")
        self.assertEqual(probe.call_count, 2)

    def test_current_original_identity_can_refresh_without_catalog(self):
        row = {**source_row(), "file_hash": "b" * 32}
        media = {"ok": True, "duration_seconds": 2}
        with OriginalParser(auto_guest=False) as parser, \
                patch.object(parser, "detail", return_value=detail([row])), \
                patch.object(parser, "_json", return_value=payload([row])), \
                patch.object(parser, "probe", side_effect=[ParseError("probe_failed", "expired"), media]), \
                patch.object(parser, "_dispatch_official_original", return_value=CDN + "renewed.mp4") as dispatch, \
                patch.object(parser, "_catalog_original_candidate", side_effect=AssertionError("catalog used")), \
                patch("original_parser.client._remember_original_record"):
            result = parser.parse(WORK)
        self.assertEqual(result["data"]["url"], CDN + "renewed.mp4")
        self.assertEqual(result["data"]["source_evidence"], "official_quality")
        dispatch.assert_called_once()
        self.assertEqual(dispatch.call_args.args[0]["file_hash"], "b" * 32)

    def test_original_identity_without_usable_url_can_refresh_without_catalog(self):
        for origin in ("inline", "fallback"):
            for address in ("", "not-a-valid-encoded-url"):
                with self.subTest(origin=origin, address=address):
                    row = {**source_row(), "main_url": address, "file_hash": "b" * 32}
                    inline = [row] if origin == "inline" else []
                    fallback = [row] if origin == "fallback" else [source_row(quality="normal")]
                    with OriginalParser(auto_guest=False) as parser, \
                            patch.object(parser, "detail", return_value=detail(inline)), \
                            patch.object(parser, "_json", return_value=payload(fallback)), \
                            patch.object(parser, "probe", return_value={"ok": True, "duration_seconds": 2}) as probe, \
                            patch.object(parser, "_dispatch_official_original", return_value=CDN + "renewed.mp4") as dispatch, \
                            patch.object(parser, "_catalog_original_candidate", side_effect=AssertionError("catalog used")), \
                            patch("original_parser.client._remember_original_record"):
                        result = parser.parse(WORK)
                    self.assertEqual(result["data"]["url"], CDN + "renewed.mp4")
                    self.assertEqual(result["data"]["source_evidence"], "official_quality")
                    dispatch.assert_called_once()
                    probe.assert_called_once()
                    self.assertEqual(probe.call_args.args[0]["urls"], [CDN + "renewed.mp4"])

    def test_missing_url_mode_still_rejects_non_original_or_invalid_metadata(self):
        cases = ({"quality": "normal"}, {"vtype": "dash"}, {"encrypt": True},
                 {"spade_a": "secret"}, {"encryption_method": "encrypted"},
                 {"size": 0}, {"vwidth": 0}, {"vheight": 0}, {"bitrate": -1})
        for overrides in cases:
            with self.subTest(overrides=overrides), OriginalParser(auto_guest=False) as parser:
                row = {**source_row(), "main_url": "", "file_hash": "b" * 32, **overrides}
                with self.assertRaises(ParseError):
                    parser._source_candidates(payload([row]), VID, allow_missing_urls=True)
        for key, value in (("video_id", "another-video"), ("status", 2002)):
            with self.subTest(key=key), OriginalParser(auto_guest=False) as parser:
                response = payload([{**source_row(), "main_url": "", "file_hash": "b" * 32}])
                response["video_info"]["data"][key] = value
                with self.assertRaises(ParseError):
                    parser._source_candidates(response, VID, allow_missing_urls=True)

    def test_inline_playable_candidate_is_preferred_to_identity_without_url(self):
        identity = {**source_row(), "main_url": "", "file_hash": "b" * 32}
        with OriginalParser(auto_guest=False) as parser, \
                patch.object(parser, "_json") as request, \
                patch.object(parser, "_dispatch_official_original") as dispatch:
            _, candidates = parser.source_streams(detail([identity, source_row("ready.mp4")]))
        self.assertEqual([candidate["url"] for candidate in candidates], [CDN + "ready.mp4"])
        request.assert_not_called()
        dispatch.assert_not_called()

    def test_media_throttling_stops_routes_and_preserves_error(self):
        with OriginalParser(auto_guest=False) as parser, \
                patch.object(parser, "detail", return_value=detail([source_row()])), \
                patch.object(parser, "_json") as request, \
                patch.object(parser, "_get", return_value=RangeResponse(status=429)) as get:
            with self.assertRaises(ParseError) as caught:
                parser.parse(WORK)
        self.assertEqual(caught.exception.code, "upstream_rate_limited")
        request.assert_not_called()
        get.assert_called_once()

    def test_media_accepts_new_cdn_without_domain_allowlist(self):
        for url in (CDN + "source.mp4", "https://new-media.example/source.mp4"):
            with self.subTest(url=url), OriginalParser(auto_guest=False) as parser:
                self.assertEqual(check_url(url), url)
                _, candidates = parser._source_candidates(payload([{**source_row(), "main_url": url}]), VID)
                self.assertEqual(candidates[0]["url"], url)
        for url in ("file:///source.mp4", "https:///source.mp4", "https://user:password@media.example/source.mp4"):
            with self.subTest(url=url), self.assertRaises(ParseError):
                check_url(url)


if __name__ == "__main__":
    unittest.main()
