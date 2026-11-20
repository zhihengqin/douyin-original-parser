import json
import unittest

from tools.public_player_reference_mentions import REFERENCES, scan_body


class TestReferenceMentions(unittest.TestCase):
    ref = REFERENCES["7707954213745085746"]

    def scan(self, body):
        return scan_body(body.encode(), **self.ref)

    def test_match_requires_complete_tokens(self):
        md5 = self.ref["md5"]
        size = self.ref["size"]
        result = self.scan(f"{size}8 0.{size} {size}.31 -{size} {md5}9 path_{md5}")
        self.assertEqual(result["classification"], "none")
        self.assertEqual(result["size_mentions"], 0)
        self.assertEqual(result["md5_mentions"], 0)
        self.assertEqual(self.scan(f"<i>{size}</i>")["classification"], "size_only")

    def test_distinguishes_plaintext_hash_from_row_declarations(self):
        md5 = self.ref["md5"].upper()
        size = self.ref["size"]
        url = f"https://example.invalid/{md5}?secret=test"
        loose = self.scan(f"<a href='{url}'>download</a>")
        self.assertEqual(loose["classification"], "md5_mention")
        self.assertEqual(loose["md5_mentions"], 1)
        separate = self.scan(json.dumps([{"size": size}, {"file_hash": md5}]))
        self.assertEqual(separate["classification"], "declared_md5")
        same = self.scan(json.dumps([{"file_hash": md5, "data_size": str(size),
                                      "url": url, "ignored": {"size": 0}}]))
        self.assertEqual(same, {"size_mentions": 1, "md5_mentions": 2,
                                "classification": "declared_md5_and_size",
                                "declared_fields": ["data_size", "file_hash"]})
