from datetime import date

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import DailyCheckin


class DailyCheckinApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            email="daily-checkin@example.com",
            password="pass12345",
            name="Daily Checkin User",
        )
        cls.other_user = User.objects.create_user(
            email="other@example.com",
            password="pass12345",
            name="Other User",
        )

    def setUp(self):
        self.client.force_authenticate(self.user)
        self.url = reverse("daily-checkin")

    def test_post_creates_daily_checkin(self):
        payload = {"date": "2026-04-21"}

        resp = self.client.post(self.url, payload, format="json")

        assert resp.status_code == status.HTTP_201_CREATED
        checkin = DailyCheckin.objects.get(user=self.user, date=date(2026, 4, 21))
        assert resp.data["id"] == checkin.id
        assert resp.data["date"] == "2026-04-21"
        assert "created_at" in resp.data

    def test_post_rejects_duplicate_date_for_same_user(self):
        DailyCheckin.objects.create(user=self.user, date=date(2026, 4, 21))

        resp = self.client.post(
            self.url, {"date": "2026-04-21"}, format="json"
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert DailyCheckin.objects.filter(user=self.user, date="2026-04-21").count() == 1
        assert "date" in resp.data

    def test_post_allows_same_date_for_other_user(self):
        DailyCheckin.objects.create(user=self.other_user, date=date(2026, 4, 21))

        resp = self.client.post(
            self.url, {"date": "2026-04-21"}, format="json"
        )

        assert resp.status_code == status.HTTP_201_CREATED
        assert DailyCheckin.objects.filter(date="2026-04-21").count() == 2

    def test_get_requires_date_param(self):
        resp = self.client.get(self.url)

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "date" in resp.data.get("detail", "").lower()

    def test_get_returns_exists_false_when_no_checkin(self):
        resp = self.client.get(self.url, {"date": "2026-04-21"})

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data == {"date": "2026-04-21", "exists": False}

    def test_get_returns_exists_true_when_checkin_exists(self):
        DailyCheckin.objects.create(user=self.user, date=date(2026, 4, 21))

        resp = self.client.get(self.url, {"date": "2026-04-21"})

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data == {"date": "2026-04-21", "exists": True}

    def test_get_does_not_leak_other_users_checkin(self):
        DailyCheckin.objects.create(user=self.other_user, date=date(2026, 4, 21))

        resp = self.client.get(self.url, {"date": "2026-04-21"})

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data == {"date": "2026-04-21", "exists": False}

    def test_endpoint_requires_auth(self):
        self.client.force_authenticate(user=None)

        resp = self.client.get(self.url, {"date": "2026-04-21"})

        assert resp.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )
