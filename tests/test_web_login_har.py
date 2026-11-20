import json
import unittest
from urllib.parse import urlencode

from tools.compare_web_login_har import compare, summarize


WORK = "7700000000000000001"
OTHER_WORK = "7700000000000000002"
VID = "v1234567890123456789"
OTHER_VID = "v9876543210987654321"
SIGN = "de" * 16
NORMAL_HASH = "11" * 16
ORIGINAL_HASH = "22" * 16
UNRELATED_HASH = "33" * 16
PRIVATE_MARKER = "PRIVATE_TEST_MARKER"


def entry(url, body):
    content = {"mimeType": "application/json"}
    if body is not None:
        content["text"] = json.dumps(body)
    return {"request": {"method": "GET", "url": url, "headers": []},
            "response": {"status": 200, "content": content, "headers": []}}


def detail(work=WORK, vid=VID, fallback=None, encoded=True):
    model = {"video_id": vid, "status": 10}
    if fallback is not None:
        model["fallback_api"] = fallback
    return entry("https://www.douyin.com/aweme/v1/web/aweme/detail/?aweme_id=" + work,
                 {"status_code": 0, "aweme_detail": {"aweme_id": work, "video": {
                     "play_addr": {"uri": vid},
                     "video_model": json.dumps(model) if encoded else model}}})


def row(quality, file_hash):
    return {"quality": quality, "file_hash": file_hash, "size": 456789,
            "vwidth": 720, "vheight": 1280, "vtype": "mp4", "codec_type": "h264",
            "main_url": "https://media.invalid/" + PRIVATE_MARKER}


def catalog(rows, *, selector="original", path_vid=VID, response_vid=VID,
            host="vas-lf-x.snssdk.com", include_body=True):
    params = {"aid": "392139", "private_test": PRIVATE_MARKER}
    if selector == "original":
        params.update(force_fids="b3JpZ2luYWw=", codec_type="5")
    elif selector == "source":
        params.update(stream_type="source")
    url = f"https://{host}/video/fplay/1/{SIGN}/{path_vid}?" + urlencode(params)
    payload = {"code": 0, "video_info": {"code": 0, "data": {
        "video_id": response_vid, "status": 10, "video_list": rows}}}
    return entry(url, payload if include_body else None)


def summarize_entries(*entries):
    return summarize({"log": {"version": "1.2", "entries": list(entries)}}, WORK)


class WebLoginHarTests(unittest.TestCase):
    def test_exact_issued_addresses_pair_across_captures_and_distinguish_relabels(self):
        normal = catalog([row("normal", NORMAL_HASH), row("original", UNRELATED_HASH)])
        new = catalog([row("source", NORMAL_HASH), row("original", ORIGINAL_HASH),
                       row("original", UNRELATED_HASH)])
        new["request"]["url"] += "&different_issuance=1"
        guest = summarize_entries(detail(fallback=normal["request"]["url"]), normal)
        logged = summarize_entries(new, detail(fallback={"fallback_api": new["request"]["url"]}, encoded=False))
        result = {c["selector"]: c for c in compare(guest, logged)}["issued"]
        self.assertEqual(result["status"], "comparable")
        self.assertEqual(result["added_original_hashes"], [ORIGINAL_HASH])
        self.assertEqual(result["relabeled_original_hashes"], [NORMAL_HASH])
        self.assertEqual([c["selector"] for c in logged["catalogs"]], ["issued"])
        for token in (SIGN, PRIVATE_MARKER, "different_issuance", "https://"):
            self.assertNotIn(token, json.dumps([guest, logged, result]))

    def test_generic_or_conflicting_queries_do_not_establish_issuance(self):
        generic = catalog([row("original", ORIGINAL_HASH)], selector="unspecified")
        url = generic["request"]["url"]
        for unverified_detail in (detail(), detail(fallback=url + "&changed="),
                                  detail(OTHER_WORK, fallback=url)):
            obs = summarize_entries(detail(), unverified_detail, generic)
            self.assertEqual(obs["catalogs"][0]["selector"], "unspecified")
        forged = catalog([row("original", ORIGINAL_HASH)])
        forged["request"]["url"] += "&stream_type=source"
        self.assertEqual(summarize_entries(detail(), forged)["catalogs"][0]["selector"], "unspecified")
        self.assertEqual(summarize_entries(detail(fallback=forged["request"]["url"]), forged)
                         ["catalogs"][0]["selector"], "issued")

    def test_missing_body_is_not_absent_or_comparable_even_with_another_valid_issued_response(self):
        hit = catalog([row("normal", NORMAL_HASH)])
        missing = catalog([], include_body=False)
        target = detail(fallback=hit["request"]["url"])
        complete = summarize_entries(target, hit)
        get = lambda other: next(c for c in compare(complete, other) if c["selector"] == "issued")
        absent = get(summarize_entries(target))
        no_body = get(summarize_entries(target, missing))
        partial = get(summarize_entries(target, hit, missing))
        for result in (absent, no_body, partial):
            self.assertEqual(result["status"], "no_paired_catalog")
            self.assertEqual(result["added_original_hashes"], [])
        self.assertEqual(absent["logged_requests"], {"total": 0, "unreadable": 0})
        self.assertEqual(no_body["logged_requests"], {"total": 1, "unreadable": 1})
        self.assertEqual(partial["logged_requests"], {"total": 2, "unreadable": 1})

    def test_conflicting_file_hash_or_absent_grade_blocks_object_deduction(self):
        before = summarize_entries(detail(), catalog([row("normal", NORMAL_HASH)]))
        conflicting = dict(row("original", ORIGINAL_HASH), video_meta={"file_hash": UNRELATED_HASH})
        for ambiguous in (conflicting, row("", ORIGINAL_HASH)):
            logged = summarize_entries(detail(), catalog([ambiguous]))
            result = next(r for r in compare(before, logged) if r["selector"] == "original")
            self.assertEqual(result["status"], "no_paired_catalog")
            self.assertFalse(result["added_original_hashes"] or result["relabeled_original_hashes"])

    def test_detail_only_and_missing_body_are_distinct(self):
        detail_only = summarize_entries(detail())
        no_body = summarize_entries(detail(), catalog([], include_body=False))
        self.assertEqual(detail_only["verdict"], "no_catalog_request")
        self.assertEqual(no_body["verdict"], "no_matched_catalog")
        self.assertFalse(no_body["catalogs"])

    def test_catalog_must_belong_to_target_and_official_host(self):
        for label, captured in (
            ("other work", (detail(OTHER_WORK, OTHER_VID),
                            catalog([row("original", ORIGINAL_HASH)], path_vid=OTHER_VID,
                                    response_vid=OTHER_VID))),
            ("body VID differs", (detail(), catalog([row("original", ORIGINAL_HASH)],
                                                   response_vid=OTHER_VID))),
            ("path VID differs", (detail(), catalog([row("original", ORIGINAL_HASH)],
                                                   path_vid=OTHER_VID))),
            ("foreign host", (detail(), catalog([row("original", ORIGINAL_HASH)],
                                                host="snssdk.com.invalid"))),
        ):
            with self.subTest(label=label):
                summary = summarize_entries(*captured)
                self.assertNotEqual(summary["verdict"], "matched_catalog")
                self.assertFalse(summary["catalogs"])
                self.assertNotIn(ORIGINAL_HASH, json.dumps(summary))

    def test_verified_original_hash_is_distinct_from_new_ordinary_hash(self):
        before = summarize_entries(detail(), catalog([row("normal", NORMAL_HASH)]))
        after = summarize_entries(detail(), catalog([row("original", ORIGINAL_HASH),
                                                     row("normal", UNRELATED_HASH)]))
        self.assertEqual(after["verdict"], "matched_catalog")
        self.assertEqual(len(after["catalogs"]), 1)
        actual = after["catalogs"][0]
        self.assertEqual((actual["selector"], actual["rows"], actual["originals"],
                          actual["hash_complete"]), ("original", 2, 1, True))
        paired = {item["selector"]: item for item in compare(before, after)}
        self.assertEqual(paired["original"]["status"], "comparable")
        self.assertEqual(paired["original"]["added_original_hashes"], [ORIGINAL_HASH])
        rendered = json.dumps([before, after, paired])
        for token in (SIGN, PRIVATE_MARKER, "https://"):
            self.assertNotIn(token, rendered)

    def test_different_selectors_are_not_a_pair(self):
        guest = summarize_entries(detail(), catalog([row("normal", NORMAL_HASH)]))
        login = summarize_entries(detail(), catalog([row("source", ORIGINAL_HASH)], selector="source"))
        paired = compare(guest, login)
        self.assertTrue(paired)
        self.assertTrue(all(item["status"] == "no_paired_catalog" for item in paired))
        self.assertFalse(any(item.get("added_original_hashes") for item in paired))
