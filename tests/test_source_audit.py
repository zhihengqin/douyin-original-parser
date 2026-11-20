import json
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

import requests

from original_parser.client import ParseError
from tools.audit_official_sources import (AuditParser, CandidateCollector, audit,
                                          collect_audio_fields, report_candidate,
                                          url_identity, web_pc_params)


class SourceAuditTests(unittest.TestCase):
    def test_nested_model_preserves_quality_and_deduplicates_mirrors(self):
        fid = "a" * 32
        model = {"video_list": [{"video_meta": {"quality": "original", "file_id": fid, "size": 100},
                                 "main_url": "https://v1.douyinvod.com/sign/time/video/tos/cn/bucket/object/?secret=one",
                                 "backup_url": "https://v5.zjcdn.com/other/time/video/tos/cn/bucket/object/?secret=two"}]}
        collector = CandidateCollector()
        collector.collect({"video_model": json.dumps(model)}, "web")
        collector.collect({"play_addr": {"url_list": ["https://api.amemv.com/aweme/v1/play/?file_id=" + fid],
                                                  "file_hash": "b" * 32}}, "app")
        groups = collector.candidates()
        self.assertEqual(len(groups), 1)
        report = report_candidate(groups[0])
        self.assertTrue(report["explicit_original"])
        self.assertFalse(report["original_verified"])
        self.assertEqual(len(report["addresses"]), 3)
        serialized = json.dumps(report)
        self.assertNotIn("secret=", serialized)
        self.assertNotIn("https://", serialized)
        self.assertIn("#json", serialized)

    def test_big_unknown_file_is_not_classified_as_original(self):
        collector = CandidateCollector()
        collector.collect({"url_list": ["https://v1.douyinvod.com/a.mp4"], "data_size": 987654321}, "web")
        self.assertFalse(report_candidate(collector.candidates()[0])["explicit_original"])

    def test_cover_variants_do_not_become_media_or_decode_failures(self):
        collector = CandidateCollector()
        collector.collect({
            "format": "mp4",
            "cover_original_scale": {"url_list": [
                "https://p3-sign.douyinpic.com/cover.jpeg?signature=private",
                "https://v1.douyinvod.com/cover.jpeg"]},
            "gaussian_cover": {"url_list": [
                "https://p3-sign.douyinpic.com/blurred.jpeg?signature=private",
                "https://v1.douyinvod.com/blurred.jpeg"]},
            "play_addr": {"data_size": 100, "url_list": [
                "https://v1.douyinvod.com/video.mp4"]},
        }, "native_detail")
        groups = collector.candidates()
        self.assertEqual(len(groups), 1)
        self.assertEqual(collector.decode_failures, 0)
        self.assertEqual(groups[0]["observations"][0]["path"], "video.play_addr")
        self.assertNotIn("cover_original_scale", json.dumps(report_candidate(groups[0])))
        self.assertNotIn("gaussian_cover", json.dumps(report_candidate(groups[0])))

    def test_dictionary_url_list_preserves_identity_without_claiming_original(self):
        collector = CandidateCollector()
        collector.collect({"audio_meta": {"file_id": "a" * 32, "file_hash": "b" * 32,
                                           "format": "dash", "size": 100,
                                           "url_list": {
                                               "main_url": "https://v1.douyinvod.com/sign/video/tos/cn/bucket/audio/?private=one",
                                               "backup_url": "https://v5.zjcdn.com/sign/video/tos/cn/bucket/audio/?private=two"}}},
                          "official-audio")
        groups = collector.candidates()
        self.assertEqual(len(groups), 1)
        self.assertEqual(groups[0]["observations"][0]["metadata"]["file_hash"], "b" * 32)
        report = report_candidate(groups[0])
        self.assertEqual(len(report["addresses"]), 2)
        self.assertFalse(report["explicit_original"])
        self.assertFalse(report["original_verified"])
        self.assertIn("audio_meta.url_list.main_url", json.dumps(report))
        self.assertNotIn("private=", json.dumps(report))

    def test_audio_candidates_keep_audio_file_id_and_never_verify_as_original(self):
        video = CandidateCollector()
        audio = CandidateCollector(audio=True)
        payload = {"video_model": json.dumps({"audio_list": [{
            "quality": "source", "audio_file_id": "a" * 32, "size": 1234,
            "play_addr": {"url_list": ["https://v1.douyinvod.com/audio"]}}]}),
            "bit_rate_audio": [{"audio_meta": {"audio_file_id": "b" * 32,
                                                   "format": "dash", "size": 5678,
                                                   "url_list": {"main_url": "https://v1.douyinvod.com/other-audio"}}}]}
        video.collect(payload, "web_detail")
        collect_audio_fields(payload, audio, "web_detail", "video")

        self.assertEqual(video.candidates(), [])
        reports = [report_candidate(group, audio=True) for group in audio.candidates()]
        self.assertEqual(len(reports), 2)
        self.assertTrue(all(row["media_type"] == "audio" for row in reports))
        self.assertTrue(all(not row["explicit_original"] and not row["original_verified"]
                            and not row["audio_probe_performed"] for row in reports))
        metadata = [row["metadata"] for report in reports for row in report["observations"]]
        self.assertEqual({row["audio_file_id"] for row in metadata}, {"a" * 32, "b" * 32})

    def test_web_pc_is_opt_in_and_follows_each_returned_fplay_model(self):
        work = "7708319942491344154"
        ua = "Mozilla/5.0 Chrome/142.0.7444.48 Safari/537.36"
        params = web_pc_params(work, ua)
        self.assertEqual(params["browser_version"], "142.0.7444.48")
        self.assertEqual(params["engine_version"], "142.0.7444.48")
        self.assertEqual(params["screen_width"], "1920")
        with self.assertRaises(ParseError) as caught:
            web_pc_params(work, "Mozilla/5.0 Firefox/140.0")
        self.assertEqual(caught.exception.code, "unsupported_profile")

        class FakeParser:
            user_agent = ua
            cookies = {}
            stop_reason = None
            request_count = 0

            def __init__(self):
                self.calls = []

            def resolve_id(self, _text):
                return work

            def detail(self, _work):
                return {"aweme_id": work, "video": {"duration": 1000,
                    "video_model": {"video_id": "primary", "fallback_api":
                        "https://v1.snssdk.com/aweme/v1/play/?video_id=primary&token=a%2fb&blank=&logo_type=x"}}}

            def _json(self, url, *, headers=None, stage=None):
                self.request_count += 1
                self.calls.append(url)
                if "/aweme/v1/web/aweme/detail/" in url:
                    return {"aweme_detail": {"aweme_id": work, "video": {
                        "video_model": {"video_id": "secondary", "fallback_api":
                            "https://v1.snssdk.com/aweme/v1/play/?video_id=secondary"}}}}
                vid = parse_qs(urlsplit(url).query)["video_id"][0]
                videos = ([{"file_hash": "a" * 32, "quality": "original",
                            "main_url": "https://v1.douyinvod.com/pc-only"}]
                          if vid == "secondary" else [])
                return {"code": 0, "video_info": {"data": {
                    "video_id": vid, "status": 10, "video_list": videos}}}

        baseline = FakeParser()
        baseline_report = audit(work, baseline, app_detail=False)
        self.assertFalse(baseline_report["web_pc_enabled"])
        self.assertEqual(len(baseline.calls), 3)
        self.assertFalse(any("aweme/v1/web/aweme/detail" in url for url in baseline.calls))
        self.assertEqual(baseline_report["candidate_count"], 0)
        self.assertEqual(baseline.calls[0], baseline.detail(work)["video"]["video_model"]["fallback_api"])

        extended = FakeParser()
        extended_report = audit(work, extended, app_detail=False, web_pc=True)
        self.assertTrue(extended_report["web_pc_enabled"])
        self.assertEqual(len(extended.calls), 7)
        self.assertIn("browser_version=142.0.7444.48", extended.calls[0])
        self.assertTrue(all("video_id=primary" in url for url in extended.calls[1:4]))
        self.assertTrue(all("video_id=secondary" in url for url in extended.calls[4:]))
        self.assertEqual(extended.calls[1], baseline.calls[0])
        self.assertEqual(extended_report["routes"][0]["name"], "web_detail_minimal")
        self.assertEqual(extended_report["routes"][1]["name"], "web_detail_web_pc")
        self.assertEqual(extended_report["fplay_context_count"], 2)
        self.assertEqual(extended_report["candidate_count"], 1)
        self.assertTrue(extended_report["candidates"][0]["explicit_original"])
        self.assertFalse(extended_report["original_verified"])
        self.assertTrue(all(row["origin"].endswith("@web_detail_web_pc")
                            for row in extended_report["candidates"][0]["observations"]))
        self.assertTrue(all(row["outcome"] == "received" and row["attempted_routes"] == 3
                            for row in extended_report["model_contexts"]))
        self.assertFalse(extended_report["incomplete"])

    def test_app_same_vid_keeps_distinct_contexts_and_its_user_agent(self):
        work = "7708319942491344154"
        shared = "https://v1.snssdk.com/video?video_id=shared&token=web-private"

        class FakeParser:
            cookies = {}
            stop_reason = None

            def __init__(self, same_fallback):
                self.same_fallback = same_fallback
                self.calls = []
                self.request_count = 0
                self.session = SimpleNamespace(cookies=requests.cookies.RequestsCookieJar())

            def resolve_id(self, _text):
                return work

            def detail(self, _work):
                return {"aweme_id": work, "video": {"duration": 1000,
                    "play_addr": {"uri": "shared"},
                    "video_model": {"video_id": "shared", "fallback_api": shared}}}

            def _json(self, url, *, headers=None):
                self.calls.append((url, headers))
                self.request_count += 1
                if "api.amemv.com/aweme/v1/aweme/detail/" in url:
                    app = self.detail(work)
                    if not self.same_fallback:
                        app["video"]["video_model"]["fallback_api"] = shared.replace("web-private", "app-private")
                    return {"aweme_detail": app}
                videos = ([{"file_hash": "b" * 32, "main_url": "https://v1.douyinvod.com/context-video"}]
                          if headers and headers.get("User-Agent", "").startswith("com.ss.android.ugc.aweme/") else [])
                return {"video_info": {"data": {"video_id": "shared", "status": 10,
                                                 "video_list": videos}}}

        for same_fallback in (False, True):
            with self.subTest(same_fallback=same_fallback):
                parser = FakeParser(same_fallback)
                report = audit(work, parser)
                self.assertEqual(len(parser.calls), 7)
                self.assertEqual(report["fplay_context_count"], 2)
                self.assertEqual(report["candidate_count"], 1)
                self.assertFalse(report["incomplete"])
                origins = [row["context_origins"] for row in report["routes"]
                           if row["name"].startswith("fplay_")]
                self.assertEqual(origins, [["web_detail_minimal"]] * 3 + [["app_detail"]] * 3)
                self.assertTrue(all(row["origin"].endswith("@app_detail")
                                    for row in report["candidates"][0]["observations"]))
                app_headers = parser.calls[0][1]
                self.assertTrue(app_headers["User-Agent"].startswith("com.ss.android.ugc.aweme/"))
                self.assertTrue(all(headers is None for _url, headers in parser.calls[1:4]))
                self.assertTrue(all(headers == app_headers for _url, headers in parser.calls[4:]))
                if same_fallback:
                    self.assertEqual([url for url, _headers in parser.calls[1:4]],
                                     [url for url, _headers in parser.calls[4:]])
                self.assertEqual({row["origin"] for row in report["model_contexts"]},
                                 {"web_detail_minimal", "app_detail"})
                self.assertTrue(all(row["attempted_routes"] == 3 for row in report["model_contexts"]))
                self.assertNotIn("web-private", json.dumps(report))
                self.assertNotIn("app-private", json.dumps(report))

    def test_web_and_pc_identical_fallback_deduplicates_and_preserves_both_origins(self):
        work = "7708319942491344154"
        shared = "https://v1.snssdk.com/video?video_id=shared&token=private-value"

        class FakeParser:
            user_agent = "Mozilla/5.0 Chrome/142.0.7444.48"
            cookies = {}
            stop_reason = None

            def __init__(self):
                self.calls = []
                self.request_count = 0

            def resolve_id(self, _text):
                return work

            def detail(self, _work):
                return {"aweme_id": work, "video": {
                    "play_addr": {"uri": "shared"},
                    "video_model": {"video_id": "shared", "fallback_api": shared}}}

            def _json(self, url, *, headers=None, stage=None):
                self.calls.append(url)
                self.request_count += 1
                if "/aweme/v1/web/aweme/detail/" in url:
                    return {"aweme_detail": self.detail(work)}
                return {"video_info": {"data": {"video_id": "shared", "status": 10,
                    "video_list": [{"main_url": "https://v1.douyinvod.com/shared-file"}]}}}

        parser = FakeParser()
        report = audit(work, parser, app_detail=False, web_pc=True)
        self.assertEqual(len(parser.calls), 4)
        self.assertEqual(report["fplay_context_count"], 1)
        self.assertEqual(report["candidate_count"], 1)
        self.assertFalse(report["incomplete"])
        fplay_routes = [row for row in report["routes"] if row["name"].startswith("fplay_")]
        self.assertEqual([row["context_origins"] for row in fplay_routes],
                         [["web_detail_minimal", "web_detail_web_pc"]] * 3)
        self.assertTrue(all("web_detail_minimal+web_detail_web_pc" in row["origin"]
                            for row in report["candidates"][0]["observations"]))
        self.assertEqual({row["origin"] for row in report["model_contexts"]},
                         {"web_detail_minimal", "web_detail_web_pc"})
        self.assertTrue(all(row["attempted_routes"] == 3 for row in report["model_contexts"]))
        self.assertNotIn("private-value", json.dumps(report))

    def test_later_fplay_context_stop_preserves_earlier_candidates(self):
        work = "7708319942491344154"

        def response(payload=None, status=200):
            result = requests.Response()
            result.status_code = status
            result._content = json.dumps(payload).encode() if payload is not None else b""
            result._content_consumed = True
            return result

        def detail(vid):
            return response({"aweme_detail": {"aweme_id": work, "video": {
                "duration": 1000, "play_addr": {"uri": vid},
                "video_model": {"video_id": vid,
                                "fallback_api": f"https://v1.snssdk.com/video?video_id={vid}"}}}})

        first_payload = {"video_info": {"data": {"video_id": "primary", "status": 10,
            "video_list": [{"file_hash": "c" * 32, "quality": "original",
                            "main_url": "https://v1.douyinvod.com/retained?private=one"}]}}}
        for reason in ("upstream_http_429", "request_budget_exhausted"):
            for probe_all in (False, True):
                with self.subTest(reason=reason, probe_all=probe_all):
                    replies = [detail("primary"), detail("secondary")]
                    replies.extend(response(first_payload) for _ in range(3))
                    replies.append(response(status=429))
                    with patch.object(requests.Session, "send", side_effect=replies) as send, \
                            patch("tools.audit_official_sources.range_probe") as range_call, \
                            patch("tools.audit_official_sources.media_probe") as media_call:
                        with AuditParser(cookies={}, auto_guest=False,
                                         max_requests=5 if reason == "request_budget_exhausted" else 10,
                                         user_agent="Mozilla/5.0 Chrome/142.0.7444.48") as parser:
                            report = audit(work, parser, app_detail=False, web_pc=True, probe_all=probe_all)
                    self.assertEqual(send.call_count, 5 if reason == "request_budget_exhausted" else 6)
                    range_call.assert_not_called()
                    media_call.assert_not_called()
                    self.assertEqual(report["fplay_context_count"], 2)
                    self.assertEqual(report["candidate_count"], 1)
                    self.assertEqual(report["omitted_candidate_count"], 0)
                    self.assertTrue(report["incomplete"])
                    self.assertEqual(report["incomplete_reason"], reason)
                    self.assertFalse(report["original_verified"])
                    self.assertEqual(report["model_contexts"][0]["outcome"], "received")
                    self.assertEqual(report["model_contexts"][0]["attempted_routes"], 3)
                    self.assertEqual(report["model_contexts"][1]["outcome"], "incomplete")
                    self.assertEqual(report["model_contexts"][1]["attempted_routes"], 1)
                    candidate = report["candidates"][0]
                    self.assertEqual(candidate["incomplete_reason"], reason)
                    self.assertEqual(candidate["observations"][0]["metadata"]["file_hash"], "c" * 32)
                    self.assertNotIn("private=", json.dumps(report))

    def test_audit_rejects_mismatched_work_and_model_without_collecting_candidates(self):
        work = "7708319942491344154"
        cases = [
            {"aweme_id": "another-work", "video": {"play_addr": {"url_list": ["https://v1.douyinvod.com/bad"]}}},
            {"aweme_id": work, "video": {"play_addr": {"uri": "primary", "url_list": ["https://v1.douyinvod.com/bad"]},
                                           "video_model": {"video_id": "wrong"}}},
        ]
        for detail in cases:
            with self.subTest(detail=detail):
                parser = SimpleNamespace(resolve_id=lambda text: work, detail=lambda work: detail,
                                         stop_reason=None, request_count=0)
                report = audit(work, parser, app_detail=False)
                self.assertEqual(report["candidate_count"], 0)
                self.assertEqual(report["audio_candidate_count"], 0)
                self.assertEqual(report["routes"][0]["error_code"], "identity_mismatch")
                self.assertTrue(report["incomplete"])

    def test_audio_model_inherits_key_seed_and_fplay_mismatch_is_rejected(self):
        fixture = json.loads((Path(__file__).parent / "codec_vector.json").read_text(encoding="utf-8"))
        collector = CandidateCollector(audio=True)
        collect_audio_fields({"video_model": json.dumps({"key_seed": fixture["key_seed"],
                             "audio": {"audio_list": [{"main_url": fixture["encoded_url"]}]}})},
                             collector, "web", "video")
        self.assertEqual(collector.observations[0]["urls"][0]["url"], fixture["decoded_url"])
        self.assertIn("video_model#json.audio.audio_list", collector.observations[0]["path"])

        work = "7708319942491344154"
        parser = SimpleNamespace(resolve_id=lambda text: work,
            detail=lambda work: {"aweme_id": work, "video": {"play_addr": {"uri": "primary"},
                "video_model": {"video_id": "primary", "fallback_api": "https://v1.snssdk.com/video"}}},
            _json=lambda url: {"video_info": {"data": {"video_id": "wrong", "status": 10,
                "video_list": [{"main_url": "https://v1.douyinvod.com/bad"}],
                "audio_list": [{"main_url": "https://v1.douyinvod.com/bad-audio"}]}}},
            stop_reason=None, request_count=0)
        report = audit(work, parser, app_detail=False)
        self.assertEqual(report["candidate_count"], 0)
        self.assertEqual(report["audio_candidate_count"], 0)
        self.assertEqual(len(report["failed_routes"]), 3)
        self.assertTrue(all(route.get("error_code") == "identity_mismatch" for route in report["routes"][1:]))

    def test_video_extra_quality_and_cover_exclusion(self):
        collector = CandidateCollector()
        collector.collect({"bit_rate": [{"video_extra": json.dumps({"quality": "normal"}),
                                          "play_addr": {"url_list": ["https://v1.douyinvod.com/movie"]}}],
                           "origin_cover": {"url_list": ["https://v1.douyinvod.com/cover"]},
                           "token_auth": {"play_auth_token": "secret"}}, "web")
        report = report_candidate(collector.candidates()[0])
        self.assertEqual(report["qualities"], ["normal"])
        self.assertEqual(len(collector.candidates()), 1)
        self.assertNotIn("secret", json.dumps(report))

    def test_different_file_ids_in_same_video_are_not_merged(self):
        prefix = "https://api.amemv.com/aweme/v1/play/?video_id=same&file_id="
        self.assertNotEqual(url_identity(prefix + "a" * 32), url_identity(prefix + "b" * 32))

    def test_untrusted_hosts_and_bad_encoding_are_rejected(self):
        collector = CandidateCollector()
        collector.collect({"main_url": "https://douyinvod.com.example.org/private",
                           "backup_url": "not-base64"}, "web")
        self.assertEqual(collector.candidates(), [])
        self.assertEqual(collector.decode_failures, 2)

    def test_nested_key_seed_decodes_official_address_vector(self):
        fixture = json.loads((Path(__file__).parent / "codec_vector.json").read_text(encoding="utf-8"))
        collector = CandidateCollector()
        collector.collect({"video_model": json.dumps({"key_seed": fixture["key_seed"],
                                                       "video_list": [{"main_url": fixture["encoded_url"]}]})}, "web")
        self.assertEqual(collector.observations[0]["urls"][0]["url"], fixture["decoded_url"])

    def test_original_requires_valid_metadata_and_complete_media(self):
        collector = CandidateCollector()
        collector.collect({"main_url": "https://v1.douyinvod.com/movie", "quality": "original",
                           "size": "broken", "vwidth": 1280, "vheight": 720}, "web")
        media = {"actual_size": 100, "verified_complete_mp4": True,
                 "tracks": [{"type": "vide", "width": 1280, "height": 720}]}
        parser = SimpleNamespace(stop_reason=None)
        with patch("tools.audit_official_sources.range_probe", return_value=({"mp4": True, "actual_size": 100}, "https://v1.douyinvod.com/movie")), \
                patch("tools.audit_official_sources.media_probe", return_value=media):
            report = report_candidate(collector.candidates()[0], parser, 10)
        self.assertFalse(report["original_verified"])
        self.assertFalse(report["media"]["declared_size_matches"])

    def test_rate_limit_stops_transport_before_next_request(self):
        for status in (429, 444):
            with self.subTest(status=status):
                response = requests.Response()
                response.status_code = status
                with patch.object(requests.Session, "send", return_value=response) as send:
                    with AuditParser(cookies={}, auto_guest=False) as parser:
                        parser.session.get("https://www.douyin.com/one")
                        with self.assertRaises(ParseError):
                            parser.session.get("https://www.douyin.com/two")
                        self.assertEqual(parser.request_count, 1)
                        self.assertEqual(send.call_count, 1)
                        self.assertEqual(parser.stop_reason, "upstream_http_" + str(status))

    def test_web_pc_rate_limit_keeps_minimal_candidates_without_further_requests(self):
        work = "7708319942491344154"
        detail = {"aweme_id": work, "video": {
            "duration": 1000,
            "play_addr": {"uri": "primary", "file_hash": "a" * 32,
                          "quality": "source", "data_size": 100,
                          "url_list": ["https://v1.douyinvod.com/minimal?private=one"]},
            "video_model": {"video_id": "primary",
                            "fallback_api": "https://v1.snssdk.com/video"},
        }}
        for status in (429, 444):
            for probe_all in (False, True):
                with self.subTest(status=status, probe_all=probe_all):
                    minimal = requests.Response()
                    minimal.status_code = 200
                    minimal._content = json.dumps({"aweme_detail": detail}).encode()
                    minimal._content_consumed = True
                    limited = requests.Response()
                    limited.status_code = status
                    limited._content = b""
                    limited._content_consumed = True
                    with patch.object(requests.Session, "send", side_effect=[minimal, limited]) as send, \
                            patch("tools.audit_official_sources.range_probe") as range_call, \
                            patch("tools.audit_official_sources.media_probe") as media_call:
                        with AuditParser(cookies={}, auto_guest=False,
                                         user_agent="Mozilla/5.0 Chrome/142.0.7444.48") as parser:
                            report = audit(work, parser, web_pc=True, probe_all=probe_all)

                    self.assertEqual(send.call_count, 2)
                    range_call.assert_not_called()
                    media_call.assert_not_called()
                    self.assertEqual(report["request_count"], 2)
                    self.assertEqual(report["candidate_count"], 1)
                    self.assertEqual(report["discovered_candidate_count"], 1)
                    self.assertEqual(report["omitted_candidate_count"], 0)
                    self.assertEqual(report["address_count"], 1)
                    self.assertTrue(report["incomplete"])
                    self.assertEqual(report["incomplete_reason"], f"upstream_http_{status}")
                    self.assertFalse(report["original_verified"])
                    candidate = report["candidates"][0]
                    self.assertFalse(candidate["original_verified"])
                    self.assertEqual(candidate["incomplete_reason"], f"upstream_http_{status}")
                    self.assertEqual(candidate["observations"][0]["metadata"]["file_hash"], "a" * 32)
                    self.assertEqual(candidate["observations"][0]["origin"], "web_detail_minimal")
                    self.assertNotIn("private=", json.dumps(report))

    def test_request_budget_marks_incomplete_without_transport(self):
        with patch.object(requests.Session, "send") as send:
            with AuditParser(cookies={}, auto_guest=False, max_requests=0) as parser:
                with self.assertRaises(ParseError):
                    parser.session.get("https://www.douyin.com/one")
                self.assertEqual(parser.stop_reason, "request_budget_exhausted")
                send.assert_not_called()


if __name__ == "__main__":
    unittest.main()
