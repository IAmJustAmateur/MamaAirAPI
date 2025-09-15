# api/tests/test_exposure_history.py
from __future__ import annotations

import datetime as dt

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from api.models import Exposure


class ExposureHistoryViewTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            email="u1@example.com", password="pass123", name="u1"
        )
        cls.other = User.objects.create_user(
            email="u2@example.com", password="pass123", name="u2"
        )

    def setUp(self):
        # Authenticate as primary user for most tests
        self.client.force_authenticate(self.user)
        self.url = reverse("exposure-history")
        self.today = timezone.localdate()

    # ---------- helpers ----------

    def _mk(self, user, date, score):
        """Create (or upsert) an exposure snapshot for a specific date."""
        return Exposure.set_for_date(user=user, level=score, date=date)

    # ---------- tests ----------

    def test_auth_required(self):
        """Endpoint must reject unauthenticated access."""
        self.client.force_authenticate(user=None)
        resp = self.client.get(self.url)
        self.assertEqual(resp.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_default_last_7_days(self):
        """By default returns last 7 calendar days (today inclusive)."""
        # Create 10 days of data for the current user
        for i in range(10):
            d = self.today - dt.timedelta(days=i)
            self._mk(self.user, d, score=1 + i / 10.0)

        resp = self.client.get(self.url)  # no ?days param -> default 7
        self.assertEqual(resp.status_code, status.HTTP_200_OK)

        payload = resp.json()
        self.assertEqual(payload["days_requested"], 7)

        # Expect days: today .. today-6
        expected_dates = {
            (self.today - dt.timedelta(days=i)).isoformat() for i in range(7)
        }
        got_dates = {item["date"] for item in payload["items"]}
        self.assertSetEqual(got_dates, expected_dates)

        # Ensure integrated score is mapped from exposure_level
        # (just sanity check one item exists)
        self.assertIn("integrated_score", payload["items"][0])

    def test_days_param_clamped_and_invalid(self):
        """`days` must clamp to [1, 90] and default to 7 on invalid input."""
        # Create today's and 100-days-ago exposures
        self._mk(self.user, self.today, score=4.2)
        old_date = self.today - dt.timedelta(days=100)
        self._mk(self.user, old_date, score=9.9)

        # days=0 -> clamp to 1 (only today)
        resp = self.client.get(self.url, {"days": 0})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["days_requested"], 1)
        self.assertEqual(len(data["items"]), 1)
        self.assertEqual(data["items"][0]["date"], self.today.isoformat())

        # days=999 -> clamp to 90 (old_date is outside -> not returned)
        resp = self.client.get(self.url, {"days": 999})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["days_requested"], 90)
        got_dates = {item["date"] for item in data["items"]}
        self.assertNotIn(old_date.isoformat(), got_dates)

        # days=invalid -> default 7
        resp = self.client.get(self.url, {"days": "oops"})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["days_requested"], 7)

    def test_only_user_exposures_are_returned(self):
        """Must not leak exposures of other users."""
        # Current user: today and yesterday
        self._mk(self.user, self.today, score=1.0)
        self._mk(self.user, self.today - dt.timedelta(days=1), score=2.0)

        # Other user: today
        self._mk(self.other, self.today, score=7.77)

        resp = self.client.get(self.url, {"days": 2})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        items = resp.json()["items"]

        # Should contain exactly 2 records (both for self.user)
        self.assertEqual(len(items), 2)
        self.assertTrue(all("integrated_score" in x for x in items))

    def test_ordering_is_chronological(self):
        """Items must be ordered by date ascending (chronological)."""
        d0 = self.today - dt.timedelta(days=3)
        d1 = self.today - dt.timedelta(days=1)
        d2 = self.today
        # Create out of order
        self._mk(self.user, d2, score=3.0)
        self._mk(self.user, d0, score=1.0)
        self._mk(self.user, d1, score=2.0)

        resp = self.client.get(self.url, {"days": 4})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        dates = [item["date"] for item in resp.json()["items"]]
        # Expect monotonic ascending
        self.assertEqual(dates, sorted(dates))

    def test_no_data_returns_empty_items(self):
        """With no exposures in the window, items should be empty."""
        resp = self.client.get(self.url, {"days": 7})
        self.assertEqual(resp.status_code, status.HTTP_200_OK)
        data = resp.json()
        self.assertEqual(data["items"], [])
        # Metadata should cover the requested window
        self.assertIn("start_date", data)
        self.assertIn("end_date", data)
