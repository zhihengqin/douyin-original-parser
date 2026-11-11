import base64
import copy
import concurrent.futures
import hashlib
import io
import json
import struct
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
from urllib.parse import parse_qs, urlsplit

from original_parser.client import (OriginalParser, ParseError, id_from_url, load_credentials,
                                    signed_headers, signed_query)
from original_parser import guest
from original_parser.codec import decode_url
from original_parser.media import inspect_mp4

FIXTURE = json.loads((Path(__file__).parent / "codec_vector.json").read_text(encoding="utf-8"))
AWEME = "7685326449011608873"
VID = "v03033g10000dajrmtvog65gsbhbphj0"


def box(kind, data):
    return struct.pack(">I4s", len(data) + 8, kind) + data


def mp4(audio=True):
    mvhd = bytearray(100)
    struct.pack_into(">II", mvhd, 12, 1000, 2000)

    def track(kind, codec, dims):
        tkhd = bytearray(84)
        struct.pack_into(">II", tkhd, 76, dims[0] * 65536, dims[1] * 65536)
        hdlr = bytes(8) + kind + bytes(12)
        stsd = bytes(4) + struct.pack(">I", 1) + box(codec, bytes(32))
        return box(b"trak", box(b"tkhd", tkhd) + box(b"mdia", box(b"hdlr", hdlr)
                   + box(b"minf", box(b"stbl", box(b"stsd", stsd)))))

    moov = box(b"mvhd", mvhd) + track(b"vide", b"avc1", (1920, 1080))
    if audio:
        moov += track(b"soun", b"mp4a", (0, 0))
    return box(b"ftyp", b"isom" + bytes(12)) + box(b"mdat", bytes(2048)) + box(b"moov", moov)


class Raw(io.BytesIO):
    def read(self, size=-1, **_):
        return super().read(size)


class Response:
    def __init__(self, body, *, status=200, headers=None, url=FIXTURE["decoded_url"]):
        self.body, self.status_code = body, status
        self.raw = Raw(body)
        self.headers = headers or {}
        self.url = url

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()

    def close(self):
        self.raw.close()

    def iter_content(self, size):
        for start in range(0, len(self.body), size):
            yield self.body[start:start + size]


def payload():
    row = {"quality": "original", "vtype": "mp4", "size": 61314387,
           "vwidth": 1920, "vheight": 1080, "bitrate": 2800574,
           "file_hash": "3392768053d7ba907f0551218347f768", "main_url": FIXTURE["encoded_url"]}
    return {"code": 0, "video_info": {"code": 0, "data": {
        "status": 10, "video_id": VID, "key_seed": FIXTURE["key_seed"],
        "video_duration": 175.148, "video_list": {"video_1": row}}}}


def detail():
    return {"aweme_id": AWEME, "video": {"play_addr": {"uri": VID}, "video_model": json.dumps({
        "video_id": VID, "fallback_api": {"fallback_api":
            f"https://vas-lf-x.snssdk.com/video/fplay/1/{'0' * 32}/{VID}?aid=392139&stream_type=normal"}
    })}}


class CodecTests(unittest.TestCase):
    def test_official_captured_vector(self):
        self.assertEqual(decode_url(FIXTURE["encoded_url"], FIXTURE["key_seed"]), FIXTURE["decoded_url"])

    def test_plain_and_base64_urls(self):
        url = FIXTURE["decoded_url"]
        self.assertEqual(decode_url(url), url)
        self.assertEqual(decode_url(base64.b64encode(url.encode()).decode()), url)

    def test_invalid_seed_header_and_padding(self):
        for encoded, seed in [(FIXTURE["encoded_url"], ""),
                              (base64.b64encode(b"\xa8\x00\x02\x00" + bytes(16)).decode(), FIXTURE["key_seed"]),
                              (FIXTURE["encoded_url"], base64.b64encode(bytes(32)).decode())]:
            with self.subTest(encoded=encoded[:12]), self.assertRaises(ValueError):
                decode_url(encoded, seed)


class GuestTests(unittest.TestCase):
    def setUp(self):
        for name, value in (("_cached_cookies", {}), ("_expires_at", 0.0),
                            ("_failure", None), ("_retry_after", 0.0)):
            patcher = patch.object(guest, name, value)
            patcher.start()
            self.addCleanup(patcher.stop)

    def test_signature_headers_use_same_timestamp(self):
        with patch("original_parser.client.time.time", side_effect=[1000, 1001]) as clock:
            query = signed_query({"aweme_id": AWEME}, {"UIFID_TEMP": "visitor", "s_v_web_id": "fp"})
            headers = signed_headers(query)
        self.assertEqual(clock.call_count, 1)
        self.assertEqual(headers["x-secsdk-web-expire"], "1000")
        self.assertIn("timestamp=1000", query)
        self.assertTrue(query.endswith("x-secsdk-web-signature=" + headers["x-secsdk-web-signature"]))

    def test_first_detail_initializes_guest_and_signs(self):
        with patch.object(guest, "_earn_guest", return_value={"UIFID_TEMP": "new", "ttwid": "guest"}) as earn:
            with OriginalParser() as parser, patch.object(parser, "_json", return_value={"aweme_detail": detail()}) as request:
                self.assertEqual(parser.detail(AWEME)["aweme_id"], AWEME)
                self.assertIn("uifid=new", request.call_args.args[0])
                self.assertEqual(request.call_args.kwargs["headers"]["uifid"], "new")
            with OriginalParser() as parser:
                self.assertEqual(parser.cookies["UIFID_TEMP"], "new")
            earn.assert_called_once()

    def test_rejected_cached_guest_refreshes_once(self):
        guest._cached_cookies = {"UIFID_TEMP": "old", "ttwid": "guest"}
        guest._expires_at = time.monotonic() + 60
        with patch.object(guest, "_earn_guest", return_value={"UIFID_TEMP": "new", "ttwid": "guest"}) as earn:
            with OriginalParser() as parser, patch.object(parser, "_json", side_effect=[
                    ParseError("credentials_rejected", "拒绝"), {"aweme_detail": detail()}]) as request:
                parser.detail(AWEME)
                self.assertEqual(request.call_count, 2)
                self.assertEqual(parser.cookies["UIFID_TEMP"], "new")
            earn.assert_called_once()

    def test_external_cookie_error_is_preserved(self):
        with patch.object(guest, "_earn_guest") as earn:
            with OriginalParser(cookies={"UIFID_TEMP": "external"}, user_agent="custom") as parser:
                with patch.object(parser, "_json", side_effect=ParseError("detail_unavailable", "不可见")) as request:
                    with self.assertRaises(ParseError) as caught:
                        parser.detail(AWEME)
                    self.assertEqual(caught.exception.code, "detail_unavailable")
                    self.assertEqual(request.call_count, 1)
                    self.assertEqual(request.call_args.kwargs["headers"]["User-Agent"], "custom")
            earn.assert_not_called()

    def test_forbidden_response_classification(self):
        for body, code in ((b"Blocked by ArgusSecurityPlugin Uifid Not Found", "credentials_required"),
                           (b"Blocked by ArgusSecurityPlugin Signature Not Found", "credentials_rejected"),
                           (b"Forbidden", "upstream_forbidden")):
            with self.subTest(code=code), OriginalParser(auto_guest=False) as parser:
                with patch.object(parser, "_get", return_value=Response(body, status=403)):
                    with self.assertRaises(ParseError) as caught:
                        parser._json("https://www.douyin.com/")
                    self.assertEqual(caught.exception.code, code)

    def test_concurrent_guest_initialization_is_shared(self):
        with patch.object(guest, "_earn_guest", return_value={"UIFID_TEMP": "shared", "ttwid": "guest"}) as earn:
            with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
                results = list(pool.map(lambda _: guest.get_guest(), range(6)))
            self.assertTrue(all(cookies["UIFID_TEMP"] == "shared" for cookies, _ in results))
            earn.assert_called_once()
            results[0][0]["UIFID_TEMP"] = "changed"
            self.assertEqual(guest.cached_guest()[0]["UIFID_TEMP"], "shared")

    def test_failed_initialization_has_cooldown(self):
        with patch.object(guest, "_earn_guest", side_effect=ParseError("guest_setup_required", "缺少浏览器")) as earn:
            for _ in range(3):
                with self.assertRaises(ParseError):
                    guest.get_guest()
            earn.assert_called_once()

    def test_credentials_json_preserves_user_agent(self):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "credentials.json"
            path.write_text(json.dumps({"cookies": {"UIFID_TEMP": "guest"}, "user_agent": "custom"}), encoding="utf-8")
            self.assertEqual(load_credentials(path), ({"UIFID_TEMP": "guest"}, "custom"))

    def test_script_reports_failed_exit_code(self):
        import parse_links
        with patch.object(parse_links, "OriginalParser") as parser:
            parser.return_value.__enter__.return_value.parse.side_effect = ParseError("upstream_forbidden", "拒绝")
            with patch("sys.stdout", io.StringIO()):
                self.assertEqual(parse_links.main(), 2)


class ParserTests(unittest.TestCase):
    def test_link_id(self):
        with OriginalParser() as parser:
            for value in (AWEME, f"https://www.douyin.com/video/{AWEME}",
                          f"复制打开抖音 https://www.douyin.com/?modal_id={AWEME}。"):
                self.assertEqual(parser.resolve_id(value), AWEME)

    def test_host_boundary_and_credentials(self):
        for url in (f"https://douyin.com.evil.test/video/{AWEME}",
                    f"https://evil.test/douyin.com/video/{AWEME}",
                    f"https://user:pass@www.douyin.com/video/{AWEME}",
                    f"https://www.douyin.com:9999/video/{AWEME}"):
            with self.subTest(url=url), self.assertRaises(ParseError):
                id_from_url(url)

    def test_source_selection_and_decoding(self):
        with OriginalParser() as parser, patch.object(parser, "_json", return_value=payload()) as call:
            _, candidates = parser.source_streams(detail())
            self.assertEqual(candidates[0]["url"], FIXTURE["decoded_url"])
            query = parse_qs(urlsplit(call.call_args.args[0]).query)
            self.assertEqual(query["stream_type"], ["normal"])
            self.assertEqual(query["force_fids"], [base64.b64encode(b"original").decode()])
            self.assertEqual(query["codec_type"], ["5"])
            call.assert_called_once()
            self.assertEqual(call.call_args.kwargs["stage"], "原画接口")
            self.assertEqual(candidates[0]["size"], 61314387)

    def test_original_selection_preserves_issued_path_and_query_context(self):
        item = detail()
        model = json.loads(item["video"]["video_model"])
        issued = model["fallback_api"]["fallback_api"] + (
            "&codec_type=1&force_fids=old&logo_type=watermarked"
            "&encode_user_tag=tag%2Bvalue&device_id=123&vquality=&imp=a&imp=b")
        model["fallback_api"]["fallback_api"] = issued
        item["video"]["video_model"] = json.dumps(model)
        with OriginalParser(auto_guest=False) as parser:
            with patch.object(parser, "_json", return_value=payload()) as call:
                parser.source_streams(item)
        requested = urlsplit(call.call_args.args[0])
        self.assertEqual((requested.scheme, requested.netloc, requested.path),
                         (urlsplit(issued).scheme, urlsplit(issued).netloc, urlsplit(issued).path))
        query = parse_qs(requested.query, keep_blank_values=True)
        self.assertEqual(query["encode_user_tag"], ["tag+value"])
        self.assertEqual(query["device_id"], ["123"])
        self.assertEqual(query["vquality"], [""])
        self.assertEqual(query["imp"], ["a", "b"])
        self.assertNotIn("logo_type", query)
        self.assertEqual(query["codec_type"], ["5"])
        self.assertEqual(query["force_fids"], ["b3JpZ2luYWw="])
        call.assert_called_once()

    def test_original_selection_can_fall_back_once_to_legacy_source(self):
        normal = payload()
        normal_row = normal["video_info"]["data"]["video_list"]["video_1"]
        normal_row["quality"] = "normal"
        normal_row["main_url"] = FIXTURE["decoded_url"].replace(
            "/tos-cn-v-0000c2287/", "/tos-cn-ve-51-ce/")
        with OriginalParser(auto_guest=False) as parser:
            with patch.object(parser, "_json", side_effect=[normal, payload()]) as call:
                _, candidates = parser.source_streams(detail())
        self.assertEqual(candidates[0]["official_quality"], "original")
        self.assertEqual(call.call_count, 2)
        query = parse_qs(urlsplit(call.call_args.args[0]).query)
        self.assertEqual(query["aid"], ["392139"])
        self.assertEqual(query["stream_type"], ["source"])

    def test_identity_and_upstream_rejections_do_not_trigger_legacy_request(self):
        wrong = payload()
        wrong["video_info"]["data"]["video_id"] = "another_video"
        for response in (wrong, ParseError("upstream_rate_limited", "限流"),
                         ParseError("upstream_forbidden", "拒绝"),
                         ParseError("network_error", "网络失败")):
            with self.subTest(response=type(response).__name__), OriginalParser(auto_guest=False) as parser:
                with patch.object(parser, "_json", side_effect=[response]) as call:
                    with self.assertRaises(ParseError):
                        parser.source_streams(detail())
                call.assert_called_once()

    def test_normal_only_response_is_rejected_without_decoding(self):
        response = payload()
        row = response["video_info"]["data"]["video_list"]["video_1"]
        row.update({"quality": "normal", "vwidth": 3840, "vheight": 2160,
                    "bitrate": 20000000})
        row["main_url"] = FIXTURE["decoded_url"].replace(
            "/tos-cn-v-0000c2287/", "/tos-cn-v-0051/")
        with OriginalParser(auto_guest=False) as parser:
            with patch.object(parser, "_json", return_value=response) as request, \
                    patch("original_parser.client.decode_url") as decode:
                with self.assertRaises(ParseError) as caught:
                    parser.source_streams(detail())
        self.assertEqual(caught.exception.code, "source_unavailable")
        self.assertIn("获取原画失败", str(caught.exception))
        self.assertIn("未返回 original/source 原画档位", str(caught.exception))
        self.assertEqual(request.call_count, 2)
        decode.assert_not_called()

    def test_source_failure_diagnostics_distinguish_selection_and_address_failures(self):
        cases = {
            "empty": (None, "未返回有效的视频档位"),
            "container": ({"vtype": "dash"}, "非 MP4 格式"),
            "encrypted": ({"encrypt": True}, "带媒体加密标记"),
            "missing_url": ({"main_url": ""}, "缺少播放地址"),
            "decode": ({"main_url": "not-a-valid-encoded-url"}, "地址解码失败"),
            "host": ({"main_url": "https://untrusted.example/video.mp4"}, "地址校验未通过"),
        }
        messages = {}
        for reason, (fields, expected) in cases.items():
            response = payload()
            rows = response["video_info"]["data"]["video_list"]
            if fields is None:
                rows.clear()
            else:
                rows["video_1"].update(fields)
            with self.subTest(reason=reason), OriginalParser(auto_guest=False) as parser:
                with patch.object(parser, "_json", return_value=response):
                    with self.assertRaises(ParseError) as caught:
                        parser.source_streams(detail())
                self.assertEqual(caught.exception.code, "source_unavailable")
                messages[reason] = str(caught.exception)
                self.assertIn(expected, messages[reason])
        self.assertEqual(len(set(messages.values())), len(cases), messages)

    def test_mixed_source_failures_include_all_reasons(self):
        response = payload()
        row = response["video_info"]["data"]["video_list"]["video_1"]
        response["video_info"]["data"]["video_list"] = [
            dict(row, vtype="dash"), dict(row, encrypt=True), dict(row, main_url=""),
            dict(row, main_url={"unexpected": "type"},
                 backup_url_1="https://untrusted.example/video.mp4"),
        ]
        with OriginalParser(auto_guest=False) as parser:
            with patch.object(parser, "_json", return_value=response):
                with self.assertRaises(ParseError) as caught:
                    parser.source_streams(detail())
        self.assertEqual(caught.exception.code, "source_unavailable")
        for reason in ("非 MP4 格式", "带媒体加密标记", "缺少播放地址", "地址解码失败", "地址校验未通过"):
            self.assertIn(reason + " 1 项", str(caught.exception))

    def test_invalid_source_row_collections_report_parse_error(self):
        for rows in (None, {}, [], [None, "invalid"], "invalid", 7):
            response = payload()
            response["video_info"]["data"]["video_list"] = rows
            with self.subTest(rows=rows), OriginalParser(auto_guest=False) as parser:
                with patch.object(parser, "_json", return_value=response):
                    with self.assertRaises(ParseError) as caught:
                        parser.source_streams(detail())
                self.assertEqual(caught.exception.code, "source_unavailable")

    def test_source_selection_ignores_normal_and_uses_valid_backup(self):
        response = payload()
        rows = response["video_info"]["data"]["video_list"]
        rows["normal"] = dict(rows["video_1"], quality="normal", size=999999999,
                              vwidth=3840, vheight=2160, bitrate=20000000)
        rows["normal"]["main_url"] = FIXTURE["decoded_url"].replace(
            "/tos-cn-v-0000c2287/", "/tos-cn-ve-51-ce/")
        rows["video_1"].update({"main_url": "invalid-address",
                                "backup_url_1": FIXTURE["encoded_url"],
                                "backup_url_2": FIXTURE["encoded_url"]})
        with OriginalParser(auto_guest=False) as parser:
            with patch.object(parser, "_json", return_value=response):
                _, candidates = parser.source_streams(detail())
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0]["official_quality"], "original")
        self.assertEqual(candidates[0]["size"], 61314387)
        self.assertEqual(candidates[0]["urls"], [FIXTURE["decoded_url"]])

    def test_catalog_original_dispatch_requires_matching_identity_and_valid_mp4(self):
        record = {
            "aweme_id": AWEME, "video_id": VID, "file_id": VID,
            "file_hash": "b" * 32, "size": 123456,
            "width": 1920, "height": 1080, "duration_seconds": 175.148,
            "bit_rate": 2800574, "codec": "h264", "fps": 25,
            "verified_by": "official_fplay_and_mp4_probe",
        }
        body = b"\x00\x00\x00\x10ftypisom0000"
        dispatch = Response(body, status=206, url="https://v11.douyinvod.com/original.mp4",
                            headers={"Content-Range": "bytes 0-15/123456"})
        normal = payload()
        normal_row = normal["video_info"]["data"]["video_list"]["video_1"]
        normal_row.update({"quality": "normal", "size": 60000000})
        normal_row["main_url"] = FIXTURE["decoded_url"].replace(
            "/tos-cn-v-0000c2287/", "/tos-cn-ve-51-ce/")

        with OriginalParser(auto_guest=False) as parser, \
                patch("original_parser.client._read_original_records", return_value={AWEME: record}), \
                patch.object(parser, "_json", return_value=normal), \
                patch.object(parser, "_get", return_value=dispatch) as get:
            _, candidates = parser.source_streams(detail())

        selected = candidates[0]
        self.assertEqual(selected["source_evidence"], "official_play_hash")
        self.assertEqual(selected["official_quality"], "original")
        self.assertEqual(selected["file_id"], VID)
        params = parse_qs(urlsplit(get.call_args.args[0]).query)
        self.assertEqual(params["video_id"], [VID])
        self.assertEqual(params["file_id"], [VID])
        self.assertEqual(params["sign"], ["b" * 32])
        self.assertEqual(params["is_play_url"], ["1"])

    def test_catalog_original_dispatch_rejects_wrong_size_and_wrong_identity(self):
        record = {
            "aweme_id": AWEME, "video_id": VID, "file_id": VID,
            "file_hash": "b" * 32, "size": 123456,
            "width": 1920, "height": 1080, "duration_seconds": 175.148,
            "verified_by": "official_fplay_and_mp4_probe",
        }
        normal = payload()
        normal_row = normal["video_info"]["data"]["video_list"]["video_1"]
        normal_row["quality"] = "normal"
        normal_row["main_url"] = FIXTURE["decoded_url"].replace(
            "/tos-cn-v-0000c2287/", "/tos-cn-ve-51-ce/")
        bad_size = Response(b"\x00\x00\x00\x10ftypisom0000", status=206,
                            url="https://v11.douyinvod.com/original.mp4",
                            headers={"Content-Range": "bytes 0-15/123457"})
        stale = dict(record, video_id="different_video_id")

        with OriginalParser(auto_guest=False) as parser, \
                patch("original_parser.client._read_original_records", return_value={AWEME: record}), \
                patch.object(parser, "_json", return_value=normal), \
                patch.object(parser, "_get", return_value=bad_size):
            with self.assertRaises(ParseError) as caught:
                parser.source_streams(detail())
        self.assertEqual(caught.exception.code, "source_unavailable")
        self.assertIn("获取原画失败", str(caught.exception))

        with OriginalParser(auto_guest=False) as parser, \
                patch("original_parser.client._read_original_records", return_value={AWEME: stale}), \
                patch.object(parser, "_json", return_value=normal), \
                patch.object(parser, "_get") as get:
            with self.assertRaises(ParseError) as caught:
                parser.source_streams(detail())
        get.assert_not_called()
        self.assertEqual(caught.exception.code, "source_unavailable")

    def test_source_diagnostics_do_not_expose_upstream_secrets(self):
        markers = ("secret-query-token", "secret-key-seed", "secret-quality-value")
        for fields in ({"main_url": "https://untrusted.example/video?token=" + markers[0]},
                       {"main_url": "bad-base64-" + markers[0]},
                       {"quality": markers[2]}):
            response = payload()
            response["video_info"]["data"]["key_seed"] = markers[1]
            response["video_info"]["data"]["video_list"]["video_1"].update(fields)
            with self.subTest(fields=fields), OriginalParser(auto_guest=False) as parser:
                with patch.object(parser, "_json", return_value=response):
                    with patch("original_parser.client.logger") as diagnostic_log:
                        with self.assertRaises(ParseError) as caught:
                            parser.source_streams(detail())
                output = str(caught.exception) + repr(diagnostic_log.mock_calls)
                for marker in markers:
                    self.assertNotIn(marker, output)
                self.assertLess(len(str(caught.exception)), 1200)

    def test_refuse_web_fallback_or_encrypted_video(self):
        for fields in ({"vtype": "dash"}, {"encrypt": True}, {"spade_a": "key"}):
            response = payload()
            response["video_info"]["data"]["video_list"]["video_1"].update(fields)
            with self.subTest(fields=fields), OriginalParser() as parser:
                with patch.object(parser, "_json", return_value=response), self.assertRaises(ParseError):
                    parser.source_streams(detail())

    def test_refuse_wrong_video_identity(self):
        response = payload()
        response["video_info"]["data"]["video_id"] = "another_video"
        with OriginalParser() as parser, patch.object(parser, "_json", return_value=response):
            with self.assertRaisesRegex(ParseError, "另一个视频"):
                parser.source_streams(detail())

    def test_probe_tail_moov_and_mirror_fallback(self):
        content = mp4()
        candidate = {"urls": ["https://v11.douyinvod.com/bad", "https://v11.douyinvod.com/good"],
                     "size": len(content), "width": 1920, "height": 1080, "duration_seconds": 2}

        def get(url, *, headers):
            if url.endswith("bad"):
                return Response(b"", status=403)
            start, end = map(int, headers["Range"][6:].split("-"))
            return Response(content[start:end + 1], status=206, url=url,
                            headers={"Content-Range": f"bytes {start}-{end}/{len(content)}"})

        with OriginalParser() as parser, patch.object(parser, "_get", side_effect=get):
            result = parser.probe(candidate)
            self.assertTrue(result["has_audio"])
            self.assertEqual(candidate["url"], candidate["urls"][1])

    def test_silent_media_is_rejected(self):
        content = mp4(audio=False)
        candidate = {"urls": [FIXTURE["decoded_url"]], "size": len(content),
                     "width": 1920, "height": 1080, "duration_seconds": 2}

        def get(url, *, headers):
            start, end = map(int, headers["Range"][6:].split("-"))
            return Response(content[start:end + 1], status=206,
                            headers={"Content-Range": f"bytes {start}-{end}/{len(content)}"})

        with OriginalParser() as parser, patch.object(parser, "_get", side_effect=get):
            with self.assertRaisesRegex(ParseError, "同时包含音视频"):
                parser.probe(candidate)

    def test_truncated_download_never_publishes(self):
        candidate = {"urls": [FIXTURE["decoded_url"]], "size": 9999, "file_hash": "0" * 32}
        result = {"data": {"url": FIXTURE["decoded_url"], "video_list": [candidate]}}
        with tempfile.TemporaryDirectory() as folder, OriginalParser() as parser:
            path = Path(folder) / "video.mp4"
            with patch.object(parser, "_get", return_value=Response(mp4())):
                with self.assertRaises(ParseError):
                    parser._download_once(result, path)
            self.assertFalse(path.exists())
            self.assertEqual(list(Path(folder).iterdir()), [])

    def test_download_reference_and_overwrite_protection(self):
        content = mp4()
        candidate = {"urls": [FIXTURE["decoded_url"]], "size": len(content),
                     "file_hash": hashlib.md5(content).hexdigest()}
        result = {"data": {"url": FIXTURE["decoded_url"], "video_list": [candidate]}}
        with tempfile.TemporaryDirectory() as folder, OriginalParser() as parser:
            path, reference = Path(folder) / "video.mp4", Path(folder) / "ref.mp4"
            reference.write_bytes(content)
            with patch.object(parser, "_get", return_value=Response(content)):
                record = parser.download(result, path, reference=reference)
            self.assertTrue(record["reference_match"])
            with self.assertRaisesRegex(ParseError, "已存在"):
                parser.download(result, path)
            self.assertEqual(path.read_bytes(), content)

    def test_expired_url_is_resolved_again(self):
        stale = {"data": {"aweme_id": AWEME, "expires_at": 1}}
        fresh = {"data": {"aweme_id": AWEME, "expires_at": 9999999999}}
        with tempfile.TemporaryDirectory() as folder, OriginalParser() as parser:
            with patch.object(parser, "parse", return_value=copy.deepcopy(fresh)) as resolve:
                with patch.object(parser, "_download_once", return_value={"ok": True}) as download:
                    parser.download(stale, Path(folder) / "video.mp4")
                    resolve.assert_called_once_with(AWEME)
                    self.assertEqual(download.call_args.args[0], fresh)


class MediaTests(unittest.TestCase):
    def test_tail_metadata(self):
        body = mp4()
        reads = []
        def read(offset, size):
            reads.append((offset, size))
            return body[offset:offset + size]
        result = inspect_mp4(read, len(body))
        self.assertEqual(result["duration_seconds"], 2)
        self.assertTrue(result["has_audio"] and result["has_video"])
        self.assertLess(sum(size for _, size in reads), len(body) - 1000)

    def test_truncated_box(self):
        body = struct.pack(">I4s", 9999, b"moov")
        with self.assertRaises(ValueError):
            inspect_mp4(lambda offset, size: body[offset:offset + size], len(body))


if __name__ == "__main__":
    unittest.main()
