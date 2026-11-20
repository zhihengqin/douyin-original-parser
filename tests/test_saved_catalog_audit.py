import json
import unittest

from tools.audit_saved_media_catalogs import audit


class SavedCatalogAuditTests(unittest.TestCase):
    def scan(self, value):
        return audit(value, work_id="work", video_id="vid", expected_size=123)

    def test_nested_model_is_associated_with_its_own_work(self):
        model = {"video_list": [{"quality": "original", "size": 123}]}
        payload = {"aweme_id": "work", "video": {"video_model": json.dumps(model)}}
        row, = self.scan(payload)
        self.assertEqual(row["identity"], "matched")
        self.assertTrue(row["rows"][0]["expected_size_match"])

    def test_provider_result_does_not_gain_identity_from_a_size_match(self):
        row, = self.scan({"data": {"vid": "", "video_list": [{"size": 123}]}})
        self.assertEqual(row["identity"], "unverified")
        self.assertTrue(row["rows"][0]["expected_size_match"])

    def test_neighboring_work_does_not_inherit_target_identity(self):
        data = [{"aweme_id": "work", "video_list": []},
                {"aweme_id": "other", "video_list": []}]
        self.assertEqual([r["identity"] for r in self.scan(data)], ["matched", "different"])

    def test_untrusted_text_is_not_included_in_the_summary(self):
        data = {"SECRET_KEY": {"video_list": {"SECRET_ROW": {
            "quality": "SECRET_QUALITY", "size": "SECRET_SIZE", "url": "SECRET_URL"}}}}
        shown = json.dumps(self.scan(data))
        self.assertNotIn("SECRET", shown)

    def test_wrapped_video_metadata_is_read(self):
        row, = self.scan({"video_id": "vid", "video_list": [{
            "size": 123, "video_meta": {"quality": "source"}}]})
        self.assertEqual(row["rows"][0]["quality"], "source")
        self.assertTrue(row["rows"][0]["expected_size_match"])


if __name__ == "__main__":
    unittest.main()
