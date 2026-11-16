import io
import json
import struct
import tempfile
import unittest
from unittest.mock import patch
from urllib.parse import urlsplit

from original_parser.client import OriginalParser, ParseError
from tools.probe_official_vid_lineage import (
    MAX_METADATA_BYTES, MAX_OBJECTS, MAX_VIDS, DiscoveryParser,
    inspect_identity, main, probe, sdk_url,
)

WORK = "7707993970332290314"
CURRENT = "v28033gi0000dbs4nevog65jrl6u1s10"
EMBEDDED = "v28033gi0000dbrj3knog65o00vl2vc0"
SECRET = "private-signed-query"


def box(kind, body):
    return struct.pack(">I4s", len(body) + 8, kind) + body


class Raw(io.BytesIO):
    def read(self, length=-1, **_):
        return super().read(length)


class Response:
    def __init__(self, status, body, content_range):
        self.status_code = status
        self.raw = Raw(body)
        self.headers = {"Content-Range": content_range}
        self.url = "https://v3.douyinvod.com/file?token=" + SECRET

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.raw.close()

    def close(self):
        self.raw.close()

    def iter_content(self, length):
        while chunk := self.raw.read(length):
            yield chunk


def media_file():
    header = box(b"ftyp", b"isom" + b"\0" * 16)
    metadata = box(b"moov", box(b"udta", b"vid:" + EMBEDDED.encode()))
    return header + metadata + box(b"mdat", b"media bytes are not metadata"), len(header + metadata)


class VidLineageProbeTests(unittest.TestCase):
    def run_limited_probe(self, rows, embedded_vids):
        fallback = f"https://vas-lf-x.snssdk.com/video/fplay/1/{'a' * 32}/{CURRENT}"
        detail = {"video": {"play_addr": {"uri": CURRENT},
                  "video_model": {"video_id": CURRENT, "fallback_api": fallback}}}
        queried = []

        def directory(url, **_):
            vid = CURRENT if url == fallback else urlsplit(url).path.rsplit("/", 1)[-1]
            if url != fallback:
                queried.append(vid)
            return {"video_info": {"data": {"status": 10, "video_id": vid,
                    "video_list": rows}}}

        with tempfile.TemporaryDirectory() as folder, \
                OriginalParser(auto_guest=False) as parser, \
                patch.object(parser, "detail", return_value=detail), \
                patch.object(parser, "_json", side_effect=directory), \
                patch.object(parser, "_get", side_effect=AssertionError("unexpected network")), \
                patch("tools.probe_official_vid_lineage.DiscoveryParser", return_value=parser), \
                patch("tools.probe_official_vid_lineage.inspect_identity",
                      return_value={"embedded_vids": embedded_vids}) as inspect, \
                patch("sys.argv", ["probe", "https://www.douyin.com/video/" + WORK,
                                   "--out", folder + "/report.json"]), \
                patch("sys.stdout", new_callable=io.StringIO) as stdout:
            exit_code = main()
            report = json.loads(stdout.getvalue())
        return report, exit_code, inspect.call_count, queried

    def test_object_limit_reports_unique_omissions_and_incomplete_cli_audit(self):
        for count in (MAX_OBJECTS, MAX_OBJECTS + 3):
            with self.subTest(unique_objects=count):
                rows = [{"file_id": f"{i:032x}", "size": 100,
                         "main_url": "https://v3.douyinvod.com/file"} for i in range(count)]
                # Duplicates of both checked and omitted objects must not affect counts.
                report, exit_code, inspections, queried = self.run_limited_probe(
                    rows + [rows[0], rows[-1]], [])
                omitted = max(0, count - MAX_OBJECTS)
                self.assertEqual(inspections, MAX_OBJECTS)
                self.assertEqual(len(report["media_objects"]), MAX_OBJECTS)
                self.assertEqual(report["objects_omitted"], omitted)
                self.assertEqual(report["object_limit_reached"], bool(omitted))
                self.assertFalse(report["vid_limit_reached"])
                self.assertEqual(report["vids_omitted"], 0)
                self.assertEqual(queried, [CURRENT])
                self.assertEqual(report["audit_complete"], not omitted)
                self.assertEqual(exit_code, 2 if omitted else 0)
                self.assertFalse(report["repair_verified"])

    def test_vid_limit_reports_unique_omissions_and_incomplete_cli_audit(self):
        for count in (MAX_VIDS, MAX_VIDS + 2):
            with self.subTest(observed_vids=count):
                embedded = ["v" + str(i).zfill(20) for i in range(count - 1)]
                rows = [{"file_id": f"{i:032x}", "size": 100,
                         "main_url": "https://v3.douyinvod.com/file"} for i in range(2)]
                # The current VID and repeats within/across objects are already observed.
                report, exit_code, inspections, queried = self.run_limited_probe(
                    rows, [CURRENT] + embedded + [embedded[-1]])
                omitted = max(0, count - MAX_VIDS)
                self.assertEqual(inspections, 2)
                self.assertEqual(queried, [CURRENT] + embedded[:MAX_VIDS - 1])
                self.assertEqual(report["vids_omitted"], omitted)
                self.assertEqual(report["vid_limit_reached"], bool(omitted))
                self.assertFalse(report["object_limit_reached"])
                self.assertEqual(report["objects_omitted"], 0)
                self.assertEqual(report["audit_complete"], not omitted)
                self.assertEqual(exit_code, 2 if omitted else 0)
                self.assertFalse(report["repair_verified"])

    def test_link_flow_uses_only_observed_vids_without_catalog_or_secret_output(self):
        content, media_start = media_file()
        fallback = f"https://vas-lf-x.snssdk.com/video/fplay/1/{'a' * 32}/{CURRENT}?token={SECRET}"
        detail = {"aweme_id": WORK, "video": {"play_addr": {"uri": CURRENT},
                  "video_model": json.dumps({"video_id": CURRENT, "fallback_api": fallback})}}
        row = {"quality": "normal", "file_hash": "1" * 32, "file_id": "2" * 32,
               "size": len(content), "main_url": "https://v3.douyinvod.com/file?token=" + SECRET}
        queried, ranges = [], []

        def directory(url, **_):
            vid = CURRENT if url == fallback else urlsplit(url).path.rsplit("/", 1)[-1]
            queried.append(vid)
            return {"video_info": {"data": {"status": 10, "video_id": vid,
                    "video_list": {"video_1": row}}}}

        def get_range(url, *, headers):
            start, end = map(int, headers["Range"].removeprefix("bytes=").split("-"))
            ranges.append((start, end))
            return Response(206, content[start:end + 1], f"bytes {start}-{end}/{len(content)}")

        with OriginalParser(auto_guest=False) as parser, \
                patch.object(parser, "detail", return_value=detail), \
                patch.object(parser, "_json", side_effect=directory), \
                patch.object(parser, "_get", side_effect=get_range), \
                patch.object(parser, "source_streams", side_effect=AssertionError("catalog path")), \
                patch("original_parser.client._read_original_records", side_effect=AssertionError("catalog read")):
            result = probe(parser, "https://www.douyin.com/video/" + WORK)

        self.assertEqual(queried, [CURRENT, CURRENT, EMBEDDED])
        self.assertEqual(result["media_objects"][0]["embedded_vids"], [EMBEDDED])
        self.assertTrue(all(end < media_start for _, end in ranges))
        self.assertFalse(result["catalog_used"])
        self.assertFalse(result["repair_verified"])
        self.assertTrue(result["audit_complete"])
        self.assertNotIn(SECRET, json.dumps(result))
        self.assertNotIn("https://", json.dumps(result))

    def test_sdk_host_is_allowed_but_external_redirect_is_rejected(self):
        payload = {"video_info": {"data": {"video_id": CURRENT}}}
        response = Response(200, json.dumps(payload).encode(), "")
        with DiscoveryParser(auto_guest=False) as parser, \
                patch.object(parser.session, "get", return_value=response):
            self.assertEqual(parser._json(sdk_url(CURRENT)), payload)

        redirect = Response(302, b"", "")
        redirect.headers["Location"] = "https://example.invalid/?token=" + SECRET
        with DiscoveryParser(auto_guest=False) as parser, \
                patch.object(parser.session, "get", return_value=redirect) as get:
            with self.assertRaises(ParseError) as caught:
                parser._json(sdk_url(CURRENT))
        self.assertEqual(caught.exception.code, "invalid_url")
        self.assertEqual(get.call_count, 1)

    def test_full_response_or_changed_object_size_is_rejected_before_body_read(self):
        content, _ = media_file()
        for status, total in ((200, len(content)), (206, len(content) + 1)):
            with self.subTest(status=status, total=total), OriginalParser(auto_guest=False) as parser:
                response = Response(status, content, f"bytes 0-15/{total}")
                with patch.object(parser, "_get", return_value=response) as get:
                    with self.assertRaisesRegex(ValueError, "range_mismatch"):
                        inspect_identity(parser, response.url, len(content))
                self.assertEqual(get.call_count, 1)

    def test_oversized_moov_is_rejected_before_fetching_its_body(self):
        header = struct.pack(">I4s", MAX_METADATA_BYTES + 8, b"moov") + b"\0" * 8
        ftyp = b"\0\0\0\x20ftyp" + b"isom0000"
        first = Response(206, ftyp, "bytes 0-15/4000000")
        second = Response(206, ftyp, "bytes 0-15/4000000")
        third = Response(206, header, "bytes 32-47/4000000")
        # The box length is valid for this object's total size, but reading its
        # metadata would exceed the budget. Its body must never be requested.
        with OriginalParser(auto_guest=False) as parser, \
                patch.object(parser, "_get", side_effect=[first, second, third]) as get:
            with self.assertRaisesRegex(ValueError, "metadata_budget_exceeded"):
                inspect_identity(parser, first.url, 4000000)
        self.assertEqual(get.call_count, 3)


if __name__ == "__main__":
    unittest.main()
