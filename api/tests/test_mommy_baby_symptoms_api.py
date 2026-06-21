from datetime import date, datetime, timedelta
from django.utils import timezone
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from django.urls import reverse

from api.models import (
    MommySymptom,
    BabySymptom,
    RiskDefinition,
    RiskDefinitionMommySymptom,
    RiskDefinitionBabySymptom,
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
        self.mommy_statistics_url = reverse("symptoms-mommy-statistics")
        self.mommy_class_statistics_url = reverse("symptoms-mommy-class-statistics")
        self.baby_checklist_url = reverse("symptoms-baby-checklist")
        self.baby_selection_url = reverse("symptoms-baby-selection")
        self.baby_class_statistics_url = reverse("symptoms-baby-class-statistics")

    def _aware_at(self, day, hour=9):
        return timezone.make_aware(
            datetime(day.year, day.month, day.day, hour, 0),
            timezone.get_default_timezone(),
        )

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

    def test_mommy_checklist_returns_top_five_unique_items(self):
        resp = self.client.get(self.mommy_checklist_url)

        self.assertEqual(resp.status_code, 200, resp.data)
        symptoms = resp.data["symptoms"]
        ids = [item["id"] for item in symptoms]
        self.assertLessEqual(len(symptoms), 5)
        self.assertEqual(len(ids), len(set(ids)))

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

    # ---------------- MOMMY: Statistics ----------------
    def test_mommy_statistics_returns_counts_for_period_and_multiple_risks(self):
        symptom = MommySymptom.objects.create(
            name="Test mommy statistics isolated symptom"
        )
        risk_1 = RiskDefinition.objects.create(
            name="Test mommy statistics risk A", is_enabled=True, priority=1
        )
        risk_2 = RiskDefinition.objects.create(
            name="Test mommy statistics risk B", is_enabled=True, priority=2
        )
        RiskDefinitionMommySymptom.objects.create(
            risk_definition=risk_1, symptom=symptom
        )
        RiskDefinitionMommySymptom.objects.create(
            risk_definition=risk_2, symptom=symptom
        )

        UserMommySymptoms.objects.create(
            user=self.user,
            symptom=symptom,
            recorded_at=self._aware_at(date(2026, 3, 1)),
        )
        UserMommySymptoms.objects.create(
            user=self.user,
            symptom=symptom,
            recorded_at=self._aware_at(date(2026, 3, 3)),
        )
        UserMommySymptoms.objects.create(
            user=self.user,
            symptom=symptom,
            recorded_at=self._aware_at(date(2026, 3, 10)),
        )

        resp = self.client.get(
            self.mommy_statistics_url,
            {"start_date": "2026-03-01", "end_date": "2026-03-07"},
        )

        self.assertEqual(resp.status_code, 200, resp.data)
        rows = [row for row in resp.data if row["symptom_id"] == symptom.id]
        self.assertEqual(len(rows), 2)
        self.assertEqual({row["risk_id"] for row in rows}, {risk_1.id, risk_2.id})
        self.assertEqual({row["quantity"] for row in rows}, {2})
        self.assertEqual({row["symptom_name"] for row in rows}, {symptom.name})

    def test_mommy_statistics_date_overrides_date_range(self):
        risk = RiskDefinition.objects.create(
            name="Test mommy statistics date override", is_enabled=True
        )
        RiskDefinitionMommySymptom.objects.create(
            risk_definition=risk, symptom=self.ms2
        )
        UserMommySymptoms.objects.create(
            user=self.user,
            symptom=self.ms2,
            recorded_at=self._aware_at(date(2026, 3, 1)),
        )
        UserMommySymptoms.objects.create(
            user=self.user,
            symptom=self.ms2,
            recorded_at=self._aware_at(date(2026, 3, 2)),
        )

        resp = self.client.get(
            self.mommy_statistics_url,
            {
                "date": "2026-03-02",
                "start_date": "2026-03-01",
                "end_date": "2026-03-01",
            },
        )

        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data[0]["symptom_id"], self.ms2.id)
        self.assertEqual(resp.data[0]["risk_id"], risk.id)
        self.assertEqual(resp.data[0]["quantity"], 1)

    def test_mommy_statistics_defaults_to_current_week(self):
        risk = RiskDefinition.objects.create(
            name="Test mommy statistics current week", is_enabled=True
        )
        RiskDefinitionMommySymptom.objects.create(
            risk_definition=risk, symptom=self.ms3
        )
        today = timezone.localdate()
        week_start = today - timedelta(days=today.weekday())
        in_week = week_start
        before_week = week_start - timedelta(days=1)

        UserMommySymptoms.objects.create(
            user=self.user,
            symptom=self.ms3,
            recorded_at=self._aware_at(in_week),
        )
        UserMommySymptoms.objects.create(
            user=self.user,
            symptom=self.ms3,
            recorded_at=self._aware_at(before_week),
        )

        resp = self.client.get(self.mommy_statistics_url)

        self.assertEqual(resp.status_code, 200, resp.data)
        rows = [row for row in resp.data if row["risk_id"] == risk.id]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["quantity"], 1)

    def test_mommy_statistics_is_scoped_to_authenticated_user(self):
        risk = RiskDefinition.objects.create(
            name="Test mommy statistics auth user scope", is_enabled=True
        )
        RiskDefinitionMommySymptom.objects.create(
            risk_definition=risk, symptom=self.ms1
        )
        other_user = User.objects.create_user(
            email="other-mommy-stat@example.com", password="pass12345"
        )
        UserMommySymptoms.objects.create(
            user=other_user,
            symptom=self.ms1,
            recorded_at=self._aware_at(date(2026, 4, 1)),
        )

        resp = self.client.get(
            self.mommy_statistics_url,
            {"start_date": "2026-04-01", "end_date": "2026-04-02"},
        )

        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data, [])

    def test_mommy_statistics_excludes_unclassified_and_disabled_risks(self):
        disabled_symptom = MommySymptom.objects.create(
            name="Test mommy statistics disabled symptom"
        )
        unclassified_symptom = MommySymptom.objects.create(
            name="Test mommy statistics unclassified symptom"
        )
        disabled_risk = RiskDefinition.objects.create(
            name="Test mommy statistics disabled risk", is_enabled=False
        )
        RiskDefinitionMommySymptom.objects.create(
            risk_definition=disabled_risk, symptom=disabled_symptom
        )
        UserMommySymptoms.objects.create(
            user=self.user,
            symptom=disabled_symptom,
            recorded_at=self._aware_at(date(2026, 5, 1)),
        )
        UserMommySymptoms.objects.create(
            user=self.user,
            symptom=unclassified_symptom,
            recorded_at=self._aware_at(date(2026, 5, 1)),
        )

        resp = self.client.get(self.mommy_statistics_url, {"date": "2026-05-01"})

        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data, [])

    def test_mommy_statistics_rejects_invalid_period_params(self):
        missing_end = self.client.get(
            self.mommy_statistics_url, {"start_date": "2026-03-01"}
        )
        reversed_range = self.client.get(
            self.mommy_statistics_url,
            {"start_date": "2026-03-07", "end_date": "2026-03-01"},
        )
        invalid_date = self.client.get(self.mommy_statistics_url, {"date": "bad"})

        self.assertEqual(missing_end.status_code, 400)
        self.assertEqual(reversed_range.status_code, 400)
        self.assertEqual(invalid_date.status_code, 400)

    def test_mommy_class_statistics_groups_by_class_without_risk_double_counting(self):
        symptom = MommySymptom.objects.create(
            name="Test mommy class statistics acute symptom"
        )
        lifestyle_symptom = MommySymptom.objects.create(
            name="Test mommy class statistics lifestyle symptom"
        )
        risk_1 = RiskDefinition.objects.create(
            name="Test mommy class statistics risk A", is_enabled=True, priority=1
        )
        risk_2 = RiskDefinition.objects.create(
            name="Test mommy class statistics risk B", is_enabled=True, priority=2
        )
        RiskDefinitionMommySymptom.objects.create(
            risk_definition=risk_1,
            symptom=symptom,
            symptom_class=1,
            source_phrase="Emergency source phrase",
        )
        RiskDefinitionMommySymptom.objects.create(
            risk_definition=risk_2,
            symptom=symptom,
            symptom_class=1,
            source_phrase="Second emergency source phrase",
        )
        RiskDefinitionMommySymptom.objects.create(
            risk_definition=risk_2,
            symptom=lifestyle_symptom,
            symptom_class=4,
            source_phrase="Lifestyle source phrase",
        )
        for day in [date(2026, 3, 1), date(2026, 3, 3)]:
            UserMommySymptoms.objects.create(
                user=self.user,
                symptom=symptom,
                recorded_at=self._aware_at(day),
            )
        UserMommySymptoms.objects.create(
            user=self.user,
            symptom=lifestyle_symptom,
            recorded_at=self._aware_at(date(2026, 3, 4)),
        )
        UserMommySymptoms.objects.create(
            user=self.user,
            symptom=symptom,
            recorded_at=self._aware_at(date(2026, 3, 10)),
        )

        resp = self.client.get(
            self.mommy_class_statistics_url,
            {"start_date": "2026-03-01", "end_date": "2026-03-07"},
        )

        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["start_date"], "2026-03-01")
        self.assertEqual(resp.data["end_date"], "2026-03-07")
        classes = {item["symptom_class"]: item for item in resp.data["classes"]}
        self.assertEqual(classes[1]["quantity"], 2)
        self.assertEqual(classes[1]["color_flag"], "critical_red")
        self.assertEqual(len(classes[1]["symptoms"]), 1)
        self.assertEqual(classes[1]["symptoms"][0]["symptom_id"], symptom.id)
        self.assertEqual(classes[1]["symptoms"][0]["quantity"], 2)
        self.assertEqual(
            {risk["risk_id"] for risk in classes[1]["symptoms"][0]["risks"]},
            {risk_1.id, risk_2.id},
        )
        self.assertEqual(classes[4]["quantity"], 1)

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

    def test_baby_checklist_returns_top_five_unique_items(self):
        resp = self.client.get(self.baby_checklist_url)

        self.assertEqual(resp.status_code, 200, resp.data)
        symptoms = resp.data["symptoms"]
        ids = [item["id"] for item in symptoms]
        self.assertLessEqual(len(symptoms), 5)
        self.assertEqual(len(ids), len(set(ids)))

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

    def test_baby_class_statistics_groups_by_class(self):
        symptom = BabySymptom.objects.create(name="Test baby class statistics symptom")
        risk = RiskDefinition.objects.create(
            name="Test baby class statistics risk", is_enabled=True, priority=1
        )
        RiskDefinitionBabySymptom.objects.create(
            risk_definition=risk,
            symptom=symptom,
            symptom_class=3,
            source_phrase="Reduced fetal activity",
        )
        UserBabySymptoms.objects.create(
            user=self.user,
            symptom=symptom,
            recorded_at=self._aware_at(date(2026, 4, 1)),
        )
        UserBabySymptoms.objects.create(
            user=self.user,
            symptom=symptom,
            recorded_at=self._aware_at(date(2026, 4, 2)),
        )

        resp = self.client.get(
            self.baby_class_statistics_url,
            {"date": "2026-04-01"},
        )

        self.assertEqual(resp.status_code, 200, resp.data)
        self.assertEqual(resp.data["start_date"], "2026-04-01")
        self.assertEqual(resp.data["end_date"], "2026-04-01")
        self.assertEqual(len(resp.data["classes"]), 1)
        class_data = resp.data["classes"][0]
        self.assertEqual(class_data["symptom_class"], 3)
        self.assertEqual(class_data["class_name"], "Fetal Activity & Growth Markers")
        self.assertEqual(class_data["quantity"], 1)
        self.assertEqual(class_data["symptoms"][0]["symptom_id"], symptom.id)
        self.assertEqual(class_data["symptoms"][0]["quantity"], 1)
        self.assertEqual(class_data["symptoms"][0]["risks"][0]["risk_id"], risk.id)
