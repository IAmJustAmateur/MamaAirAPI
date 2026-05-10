from datetime import date

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import Wellbeing, UserWellbeingLog


class WellbeingApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            email="u@example.com",
            password="pass12345",
            name="Test User",
        )

        # ---- Fetch seeded catalog items (created by seed migration) ----
        # Water goal (seed ensures at least one)
        cls.water_goal = (
            Wellbeing.objects.filter(kind="water_goal", is_active=True)
            .order_by("id")
            .first()
        )
        if not cls.water_goal:
            # fallback (на случай если миграцию отключили)
            cls.water_goal = Wellbeing.objects.create(
                kind="water_goal", number_value=2130, unit="ml", is_active=True
            )

        # Moods
        cls.mood_1, _ = Wellbeing.objects.get_or_create(
            kind="mood",
            code="feel_sick",
            defaults={"title": "Feel sick", "sort_order": 10, "is_active": True},
        )
        cls.mood_2, _ = Wellbeing.objects.get_or_create(
            kind="mood",
            code="nervous",
            defaults={"title": "Nervous", "sort_order": 20, "is_active": True},
        )

        # Feelings
        cls.feel_1, _ = Wellbeing.objects.get_or_create(
            kind="feeling",
            code="headache",
            defaults={"title": "Headache", "sort_order": 10, "is_active": True},
        )
        cls.feel_2, _ = Wellbeing.objects.get_or_create(
            kind="feeling",
            code="poor_sleep",
            defaults={"title": "Poor Sleep", "sort_order": 20, "is_active": True},
        )

        # Inactive test item — делаем с уникальным code, которого нет в seed
        cls.inactive_feel, _ = Wellbeing.objects.get_or_create(
            kind="feeling",
            code="inactive_x_test",
            defaults={"title": "Inactive X", "sort_order": 999, "is_active": False},
        )

    def setUp(self):
        self.client.force_authenticate(self.user)

    # ---------- Catalog ----------

    def test_catalog_get_returns_water_goal_moods_feelings(self):
        url = reverse("wellbeing-catalog")
        resp = self.client.get(url)

        assert resp.status_code == status.HTTP_200_OK
        assert "water_goal" in resp.data
        assert resp.data["water_goal"]["value"] == 2130
        assert resp.data["water_goal"]["unit"] == "ml"

        mood_titles = [x["title"] for x in resp.data["moods"]]
        feel_titles = [x["title"] for x in resp.data["feelings"]]

        assert "Feel sick" in mood_titles
        assert "Nervous" in mood_titles
        assert "Headache" in feel_titles
        assert "Poor Sleep" in feel_titles

        # inactive should not be returned
        assert "Inactive X" not in feel_titles

    # ---------- Log GET ----------

    def test_log_get_requires_date_param(self):
        url = reverse("wellbeing-log")
        resp = self.client.get(url)

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "date" in resp.data.get("detail", "").lower()

    def test_log_get_returns_empty_when_no_log(self):
        url = reverse("wellbeing-log")
        d = date(2026, 2, 28).isoformat()
        resp = self.client.get(url, {"date": d})

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["date"] == d
        assert resp.data["water_amount"] == 0
        assert resp.data["water_unit"] == "ml"
        assert resp.data["moods"] == []
        assert resp.data["feelings"] == []

    def test_log_get_returns_existing_log(self):
        log = UserWellbeingLog.objects.create(
            user=self.user, date=date(2026, 2, 28), water_amount=250, water_unit="ml"
        )
        log.moods.set([self.mood_1.id])
        log.feelings.set([self.feel_1.id])

        url = reverse("wellbeing-log")
        resp = self.client.get(url, {"date": "2026-02-28"})

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["water_amount"] == 250
        assert resp.data["water_unit"] == "ml"
        assert [x["id"] for x in resp.data["moods"]] == [self.mood_1.id]
        assert [x["id"] for x in resp.data["feelings"]] == [self.feel_1.id]

    # ---------- Log POST (upsert) ----------

    def test_log_post_creates_log_and_sets_m2m(self):
        url = reverse("wellbeing-log")
        payload = {
            "date": "2026-02-28",
            "water_amount": 250,
            "water_unit": "ml",
            "mood_ids": [self.mood_1.id, self.mood_2.id],
            "feeling_ids": [self.feel_1.id],
        }
        resp = self.client.post(url, payload, format="json")

        assert resp.status_code == status.HTTP_201_CREATED

        log = UserWellbeingLog.objects.get(user=self.user, date=date(2026, 2, 28))
        assert log.water_amount == 250
        assert log.water_unit == "ml"
        assert set(log.moods.values_list("id", flat=True)) == {
            self.mood_1.id,
            self.mood_2.id,
        }
        assert set(log.feelings.values_list("id", flat=True)) == {self.feel_1.id}

    def test_log_post_adds_water_to_existing_log(self):
        log = UserWellbeingLog.objects.create(
            user=self.user, date=date(2026, 2, 28), water_amount=250, water_unit="ml"
        )
        log.moods.set([self.mood_1.id])
        log.feelings.set([self.feel_1.id])

        url = reverse("wellbeing-log")
        payload = {
            "date": "2026-02-28",
            "water_amount": 500,
            "water_unit": "ml",
            "mood_ids": [self.mood_2.id],
            "feeling_ids": [self.feel_2.id],
        }
        resp = self.client.post(url, payload, format="json")

        assert resp.status_code == status.HTTP_201_CREATED

        log.refresh_from_db()
        assert log.water_amount == 750
        assert set(log.moods.values_list("id", flat=True)) == {self.mood_2.id}
        assert set(log.feelings.values_list("id", flat=True)) == {self.feel_2.id}

    def test_log_post_water_only_preserves_existing_moods_and_feelings(self):
        log = UserWellbeingLog.objects.create(
            user=self.user, date=date(2026, 2, 28), water_amount=250, water_unit="ml"
        )
        log.moods.set([self.mood_1.id])
        log.feelings.set([self.feel_1.id])

        url = reverse("wellbeing-log")
        payload = {
            "date": "2026-02-28",
            "water_amount": 500,
            "water_unit": "ml",
        }
        resp = self.client.post(url, payload, format="json")

        assert resp.status_code == status.HTTP_201_CREATED

        log.refresh_from_db()
        assert log.water_amount == 750
        assert set(log.moods.values_list("id", flat=True)) == {self.mood_1.id}
        assert set(log.feelings.values_list("id", flat=True)) == {self.feel_1.id}

    def test_log_post_rejects_wrong_kind_in_mood_ids(self):
        # Passing a FEELING id in mood_ids should be rejected
        url = reverse("wellbeing-log")
        payload = {
            "date": "2026-02-28",
            "mood_ids": [self.feel_1.id],  # wrong kind
            "feeling_ids": [],
        }
        resp = self.client.post(url, payload, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_log_post_rejects_inactive_feeling(self):
        url = reverse("wellbeing-log")
        payload = {
            "date": "2026-02-28",
            "mood_ids": [],
            "feeling_ids": [self.inactive_feel.id],  # inactive
        }
        resp = self.client.post(url, payload, format="json")
        assert resp.status_code == status.HTTP_400_BAD_REQUEST

    def test_catalog_requires_auth(self):
        self.client.force_authenticate(user=None)
        url = reverse("wellbeing-catalog")
        resp = self.client.get(url)
        assert resp.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )

    def test_log_requires_auth(self):
        self.client.force_authenticate(user=None)
        url = reverse("wellbeing-log")
        resp = self.client.get(url, {"date": "2026-02-28"})
        assert resp.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )
