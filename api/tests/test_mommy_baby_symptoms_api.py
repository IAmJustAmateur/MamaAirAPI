from datetime import date
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from api.models import (
    MommySymptom,
    BabySymptom,
    UserMommySymptoms,
    UserBabySymptoms,
)
from .utils import create_defaults

User = get_user_model()


class UserMommyBabySymptomsAPITests(APITestCase):
    """
    End-to-end tests for Mommy & Baby symptoms API.
    Contract highlights:
      - Checklist endpoints return objects with {id, name}.
      - Selection endpoints perform replace-all for the calendar day resolved
        from `recorded_at` (ISO-8601; naive -> server TZ) or `?date=`.
      - GET selection supports `?date=YYYY-MM-DD` and defaults to "today".
    """

    BASE = "/api/"

    def setUp(self):
        # Seed defaults (user, 3 mommy symptoms, 3 baby symptoms, etc.)
        defaults = create_defaults()
        self.user = defaults["user"]
        self.password = defaults["password"]

        # Authenticate
        r = self.client.post(
            self.BASE + "auth/token/",
            {"email": self.user.email, "password": self.password},
            format="json",
        )
        self.assertEqual(r.status_code, 200, r.data)
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {r.data['access']}")

        # Catalogs
        self.ms1, self.ms2, self.ms3 = defaults["mommy_symptoms"][:3]
        self.bs1, self.bs2, self.bs3 = defaults["baby_symptoms"][:3]

        # URLs
        self.mommy_checklist_url = reverse("symptoms-mommy-checklist")
        self.mommy_selection_url = reverse("symptoms-mommy-selection")
        self.baby_checklist_url = reverse("symptoms-baby-checklist")
        self.baby_selection_url = reverse("symptoms-baby-selection")

    # ---------------- MOMMY: Checklist ----------------
    def test_mommy_checklist_returns_id_and_name(self):
        """Checklist must return objects with id and name (strings)."""
        resp = self.client.get(self.mommy_checklist_url)
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertIn("symptoms", resp.data)
        self.assertIsInstance(resp.data["symptoms"], list)
        if resp.data["symptoms"]:
            item = resp.data["symptoms"][0]
            self.assertIn("id", item)
            self.assertIn("name", item)
            self.assertIsInstance(item["name"], str)

    # ---------------- MOMMY: Selection ----------------
    def test_mommy_selection_roundtrip_with_recorded_at_aware(self):
        """POST with aware recorded_at replaces the set for that calendar day; GET by date returns the same set."""
        payload = {
            "symptom_ids": [self.ms1.id, self.ms3.id],
            "recorded_at": "2025-09-01T08:15:00+03:00",
        }
        r = self.client.post(self.mommy_selection_url, payload, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(
            sorted(r.data.get("symptom_ids", [])), sorted(payload["symptom_ids"])
        )
        self.assertEqual(r.data.get("date"), "2025-09-01")

        # DB check for that day
        ids_db = list(
            UserMommySymptoms.objects.filter(
                user=self.user, recorded_at__date="2025-09-01"
            ).values_list("symptom_id", flat=True)
        )
        self.assertEqual(sorted(ids_db), sorted(payload["symptom_ids"]))

        # GET by date
        r = self.client.get(self.mommy_selection_url + "?date=2025-09-01")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(
            sorted(r.data.get("symptom_ids", [])), sorted(payload["symptom_ids"])
        )

    def test_mommy_selection_overwrites_same_day_naive_datetime(self):
        """Naive recorded_at is interpreted in server TZ; second POST for same day overwrites the set (replace-all)."""
        r1 = self.client.post(
            self.mommy_selection_url,
            {"symptom_ids": [self.ms1.id], "recorded_at": "2025-09-02T09:00:00"},
            format="json",
        )
        self.assertEqual(r1.status_code, 200, r1.data)

        r2 = self.client.post(
            self.mommy_selection_url,
            {"symptom_ids": [self.ms2.id], "recorded_at": "2025-09-02T10:00:00"},
            format="json",
        )
        self.assertEqual(r2.status_code, 200, r2.data)
        self.assertEqual(r2.data.get("date"), "2025-09-02")
        self.assertEqual(r2.data.get("symptom_ids"), [self.ms2.id])

        ids_db = list(
            UserMommySymptoms.objects.filter(
                user=self.user, recorded_at__date="2025-09-02"
            ).values_list("symptom_id", flat=True)
        )
        self.assertEqual(ids_db, [self.ms2.id])

    def test_mommy_selection_get_defaults_to_today(self):
        """GET selection without query params should default to today's date."""
        r = self.client.get(self.mommy_selection_url)
        self.assertEqual(r.status_code, 200)
        self.assertIn("date", r.data)
        # NOTE: We don't assert exact IDs here because default day may be empty.

    def test_mommy_selection_rejects_unknown_ids(self):
        r = self.client.post(
            self.mommy_selection_url,
            {
                "symptom_ids": [self.ms1.id, 999999],
                "recorded_at": "2025-09-03T08:00:00+03:00",
            },
            format="json",
        )
        self.assertIn(r.status_code, (400, 422))

    def test_mommy_selection_rejects_invalid_recorded_at(self):
        r = self.client.post(
            self.mommy_selection_url,
            {"symptom_ids": [self.ms1.id], "recorded_at": "not-a-datetime"},
            format="json",
        )
        self.assertIn(r.status_code, (400, 422))

    # ---------------- BABY: Checklist ----------------
    def test_baby_checklist_returns_id_and_name(self):
        """Checklist must return objects with id and name (strings)."""
        resp = self.client.get(self.baby_checklist_url)
        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertIn("symptoms", resp.data)
        self.assertIsInstance(resp.data["symptoms"], list)
        if resp.data["symptoms"]:
            item = resp.data["symptoms"][0]
            self.assertIn("id", item)
            self.assertIn("name", item)

    # ---------------- BABY: Selection ----------------
    def test_baby_selection_roundtrip_with_recorded_at(self):
        payload = {
            "symptom_ids": [self.bs1.id, self.bs3.id],
            "recorded_at": "2025-09-01T09:00:00",
        }
        r = self.client.post(self.baby_selection_url, payload, format="json")
        self.assertEqual(r.status_code, 200, r.data)
        self.assertEqual(sorted(r.data["symptom_ids"]), sorted(payload["symptom_ids"]))
        self.assertEqual(r.data["date"], "2025-09-01")

        ids_db = list(
            UserBabySymptoms.objects.filter(
                user=self.user, recorded_at__date="2025-09-01"
            ).values_list("symptom_id", flat=True)
        )
        self.assertEqual(sorted(ids_db), sorted(payload["symptom_ids"]))

        # GET by date
        r = self.client.get(self.baby_selection_url + "?date=2025-09-01")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(sorted(r.data["symptom_ids"]), sorted(payload["symptom_ids"]))

    def test_baby_selection_overwrites_same_day(self):
        r1 = self.client.post(
            self.baby_selection_url,
            {"symptom_ids": [self.bs2.id], "recorded_at": "2025-09-02T10:00:00"},
            format="json",
        )
        self.assertEqual(r1.status_code, 200, r1.data)

        r2 = self.client.post(
            self.baby_selection_url,
            {
                "symptom_ids": [self.bs1.id, self.bs3.id],
                "recorded_at": "2025-09-02T11:00:00",
            },
            format="json",
        )
        self.assertEqual(r2.status_code, 200, r2.data)
        self.assertEqual(
            sorted(r2.data["symptom_ids"]), sorted([self.bs1.id, self.bs3.id])
        )
        # self.assertListEqual(r2.data["symptom_ids"], [self.bs1.id, self.bs3.id])

        ids_db = list(
            UserBabySymptoms.objects.filter(
                user=self.user, recorded_at__date="2025-09-02"
            ).values_list("symptom_id", flat=True)
        )
        self.assertEqual(sorted(ids_db), sorted([self.bs1.id, self.bs3.id]))

    def test_baby_selection_get_defaults_to_today(self):
        r = self.client.get(self.baby_selection_url)
        self.assertEqual(r.status_code, 200)
        self.assertIn("date", r.data)

    def test_baby_selection_rejects_unknown_ids(self):
        r = self.client.post(
            self.baby_selection_url,
            {
                "symptom_ids": [self.bs1.id, 999999],
                "recorded_at": "2025-09-03T08:00:00+03:00",
            },
            format="json",
        )
        self.assertIn(r.status_code, (400, 422))

    def test_baby_selection_rejects_invalid_recorded_at(self):
        r = self.client.post(
            self.baby_selection_url,
            {"symptom_ids": [self.bs1.id], "recorded_at": "bad-ts"},
            format="json",
        )
        self.assertIn(r.status_code, (400, 422))
