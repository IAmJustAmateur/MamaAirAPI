from rest_framework.test import APITestCase


class MetaChoicesTests(APITestCase):
    def setUp(self):
        self.url = "http://127.0.0.1:8000/api/meta/choices/"

    def test_meta_choices_endpoint(self):

        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, 200, resp.data)

        # Keys we expect in response
        expected_keys = {
            "languages",
            "races",
            "countries",
            "work_types",
            "diet_types",
            "cooking_methods",
            "lifestyle_areas",
            "lifestyle_time_spent",
            "lifestyle_time_of_day",
            "exposure_levels",
        }
        self.assertTrue(expected_keys.issubset(resp.data.keys()))

        # Each list should be non-empty and contain dicts with value/label
        for key in expected_keys:
            items = resp.data[key]
            self.assertIsInstance(items, list, f"{key} is not list")
            self.assertGreater(len(items), 0, f"{key} is empty")
            sample = items[0]
            self.assertIn("value", sample)
            self.assertIn("label", sample)

    def test_languages_include_english(self):

        resp = self.client.get(self.url)
        langs = [x["value"] for x in resp.data["languages"]]
        self.assertIn("en", langs)

    def test_countries_include_nigeria(self):

        resp = self.client.get(self.url)
        countries = [x["value"] for x in resp.data["countries"]]
        self.assertIn("NG", countries)

    def test_lifestyle_onboarding_choices_include_figma_values(self):
        resp = self.client.get(self.url)

        self.assertIn(
            "peri_urban", [x["value"] for x in resp.data["lifestyle_areas"]]
        )
        self.assertIn(
            "both_equally", [x["value"] for x in resp.data["lifestyle_time_spent"]]
        )
        self.assertIn(
            "changes_day_to_day",
            [x["value"] for x in resp.data["lifestyle_time_of_day"]],
        )
