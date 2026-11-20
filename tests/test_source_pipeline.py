"""Regressions for issued inline models and continued official-source discovery."""
import io
import json
import unittest
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

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
    def test_checked_original_in_unmodified_issued_catalog(self):
        work = detail()
        m = json.loads(work["video"]["video_model"])
        url = m["fallback_api"]["fallback_api"] + "&v=a%20b&v=c"
        m["fallback_api"]["fallback_api"] = url
        work["video"]["video_model"] = json.dumps(m)
        ordinary = payload([source_row(quality="normal")])
        with OriginalParser(auto_guest=False) as parser, \
                patch.object(parser, "detail", return_value=work), \
                patch.object(parser, "_json", side_effect=[ordinary, ordinary, payload([source_row()])]) as req, \
                patch.object(parser, "_catalog_original_candidate", return_value=None), \
                patch.object(parser, "_play_default_candidate", return_value=None), \
                patch.object(parser, "probe", return_value={"ok": True, "duration_seconds": 2}) as probe, \
                patch("original_parser.client._remember_original_record"):
            result = parser.parse(WORK)["data"]
            self.assertEqual(req.call_args.args[0], url)
            self.assertEqual(result["official_quality"], "original")
            self.assertEqual(result["source_evidence"], "official_quality")
            self.assertEqual(parser.web_catalog_observations[-1]["stage"], "issued")
            probe.assert_called_once()

    def test_issued_catalog_accepts_any_official_aid_and_path(self):
        work = detail()
        model = json.loads(work["video"]["video_model"])
        issued = (f"https://vas-lf-x.douyin.com/video/fplay/2/{'a' * 32}/{VID}"
                  "?aid=1128&stream_type=normal")
        model["fallback_api"]["fallback_api"] = issued
        work["video"]["video_model"] = json.dumps(model)
        with OriginalParser(auto_guest=False) as parser, \
                patch.object(parser, "_json", return_value=payload([source_row()])) as request:
            _, candidates = parser.source_streams(work)
        self.assertEqual(candidates[0]["official_quality"], "original")
        requested = urlsplit(request.call_args.args[0])
        self.assertEqual(requested.netloc, "vas-lf-x.douyin.com")
        self.assertEqual(requested.path, f"/video/fplay/2/{'a' * 32}/{VID}")
        query = parse_qs(requested.query, keep_blank_values=True)
        self.assertEqual(query["aid"], ["1128"])
        self.assertEqual(query["stream_type"], ["normal"])
        self.assertEqual(query["codec_type"], ["5"])
        self.assertEqual(query["force_fids"], ["b3JpZ2luYWw="])

    def test_original_quality_is_not_limited_to_original_bucket(self):
        row = source_row(path="tos-cn-ve-51/original.mp4", quality="original")
        with OriginalParser(auto_guest=False) as parser, \
                patch.object(parser, "_json", return_value=payload([row])):
            _, candidates = parser.source_streams(detail())
        self.assertEqual(candidates[0]["official_quality"], "original")
        self.assertIn("/tos-cn-ve-51/", candidates[0]["url"])

    def test_source_candidate_requires_opt_in_and_independent_container_vid(self):
        normal = payload([source_row(quality="normal")])
        media = {"ok": True, "duration_seconds": 2,
                 "tags": {"comment": f"vid:{VID}-alternate"}}
        with OriginalParser(auto_guest=False, allow_source_candidate=True) as parser, \
                patch.object(parser, "_json", side_effect=[normal, normal, normal]), \
                patch.object(parser, "probe", return_value=media) as probe:
            _, candidates = parser.source_streams(detail())
        candidate = candidates[0]
        self.assertTrue(candidate["source_candidate"])
        self.assertEqual(candidate["source_evidence"], "platform_source_candidate")
        self.assertEqual(candidate["source_vid"], f"{VID}-alternate")
        self.assertEqual(candidate["official_quality"], "normal")
        self.assertIn("源候选", candidate["level"])
        probe.assert_called_once()

    def test_source_candidate_is_not_returned_without_opt_in(self):
        normal = payload([source_row(quality="normal")])
        with OriginalParser(auto_guest=False, allow_source_candidate=False) as parser, \
                patch.object(parser, "_json", side_effect=[normal, normal, normal]), \
                patch.object(parser, "probe") as probe:
            with self.assertRaises(ParseError) as caught:
                parser.source_streams(detail())
        self.assertEqual(caught.exception.code, "source_unavailable")
        probe.assert_not_called()

    def test_source_candidate_requires_independent_container_vid(self):
        for comment in (f"vid:{VID}", "", "not-a-vid"):
            normal = payload([source_row(quality="normal")])
            media = {"ok": True, "duration_seconds": 2, "tags": {"comment": comment}}
            with self.subTest(comment=comment), \
                    OriginalParser(auto_guest=False, allow_source_candidate=True) as parser, \
                    patch.object(parser, "_json", side_effect=[normal, normal, normal]), \
                    patch.object(parser, "probe", return_value=media):
                with self.assertRaises(ParseError) as caught:
                    parser.source_streams(detail())
            self.assertEqual(caught.exception.code, "source_unavailable")

    def test_parse_marks_source_candidate_without_recording_original(self):
        normal = payload([source_row(quality="normal")])
        media = {"ok": True, "actual_size": 1000, "duration_seconds": 2,
                 "has_video": True, "has_audio": True,
                 "tags": {"comment": f"vid:{VID}-alternate"}}
        with OriginalParser(auto_guest=False, allow_source_candidate=True) as parser, \
                patch.object(parser, "detail", return_value=detail()), \
                patch.object(parser, "_json", side_effect=[normal, normal, normal]), \
                patch.object(parser, "probe", return_value=media) as probe, \
                patch("original_parser.client._remember_original_record") as remember:
            result = parser.parse(WORK)
        data = result["data"]
        self.assertTrue(data["source_candidate"])
        self.assertEqual(data["source_evidence"], "platform_source_candidate")
        self.assertEqual(data["source_vid"], f"{VID}-alternate")
        self.assertEqual(result["msg"], "返回源候选（非平台原画）")
        probe.assert_called_once()
        remember.assert_not_called()

    def test_pc_web_hidden_bitrate_is_used_with_dash_audio(self):
        mobile = detail()
        pc = {"aweme_id": WORK, "video": {
            "duration": 2000,
            "bit_rate": [
                {"play_addr": {"data_size": 500, "file_hash": "a" * 32, "width": 720,
                               "height": 1280, "url_list": [CDN + "known.mp4"]}},
                {"play_addr": {"data_size": 9000, "file_hash": "b" * 32, "width": 720,
                               "height": 1280, "url_key": "hidden",
                               "url_list": [CDN + "tos-cn-v-0051/hidden.mp4"]},
                 "bit_rate": 9000},
            ],
            "bit_rate_audio": [{"audio_meta": {
                "size": 1000, "file_hash": "c" * 32, "quality": "adapt",
                "url_list": {"main_url": CDN + "tos-cn-v-0051/audio.m4a"}}}],
        }}
        normal = payload([source_row(quality="normal")])
        with OriginalParser(auto_guest=False) as parser, \
                patch.object(parser, "detail", return_value=mobile), \
                patch.object(parser, "_pc_detail", return_value=pc), \
                patch.object(parser, "_json", side_effect=[normal, normal, normal]), \
                patch.object(parser, "probe_dash", return_value={
                    "ok": True, "dash": True, "actual_size": 10000,
                    "duration_seconds": 2}) as probe_dash:
            result = parser.parse(WORK)
        data = result["data"]
        self.assertEqual(data["source_evidence"], "official_web_pc_bitrate")
        self.assertIsNone(data["official_quality"])
        self.assertFalse(data["source_selected"])
        self.assertTrue(data["dash_mux_required"])
        self.assertEqual(data["url"], CDN + "tos-cn-v-0051/hidden.mp4")
        self.assertEqual(data["audio_url"], CDN + "tos-cn-v-0051/audio.m4a")
        self.assertEqual(data["size_bytes"], 10000)
        self.assertIn("原画身份未经确认", result["msg"])
        probe_dash.assert_called_once()

    def test_pc_web_known_mobile_tiers_are_excluded(self):
        mobile = detail()
        pc = {"aweme_id": WORK, "video": {
            "duration": 2000,
            "bit_rate": [
                {"play_addr": {"data_size": 500, "file_hash": "a" * 32, "width": 720,
                               "height": 1280, "url_list": [CDN + "known.mp4"]}},
                {"play_addr": {"data_size": 9000, "file_hash": "b" * 32, "width": 720,
                               "height": 1280, "url_key": "hidden",
                               "url_list": [CDN + "tos-cn-v-0051/hidden.mp4"]}},
            ],
        }}
        with OriginalParser(auto_guest=False) as parser, \
                patch.object(parser, "_pc_detail", return_value=pc):
            candidates = parser._pc_bitrate_candidates(mobile)
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["source_evidence"], "official_web_pc_bitrate")
        self.assertEqual(candidates[0]["size"], 9000)

    def test_issued_catalog_for_other_video_is_rejected(self):
        ordinary = payload([source_row(quality="normal")])
        wrong = payload([source_row()])
        wrong["video_info"]["data"]["video_id"] = "another-video"
        with OriginalParser(auto_guest=False) as parser, \
                patch.object(parser, "_json", side_effect=[ordinary, ordinary, wrong]), \
                patch.object(parser, "_catalog_original_candidate", return_value=None), \
                patch.object(parser, "_play_default_candidate", return_value=None):
            with self.assertRaises(ParseError) as error:
                parser.source_streams(detail())
            self.assertEqual(error.exception.code, "identity_mismatch")

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
