# api/tests/test_movement_upload_json.py
from __future__ import annotations

from django.apps import apps
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework import status
from unittest.mock import patch
from django.utils import timezone

from zoneinfo import ZoneInfo

from api.services.air_exposure_daily import recompute_daily_exposure
from api.services.air_exposure import AQSample

Movement = apps.get_model("api", "Movement")
AirExposureLog = apps.get_model("api", "AirExposureLog")
DailyExposure = apps.get_model("api", "DailyExposure")


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
@override_settings(TIME_ZONE="Europe/Vilnius", USE_TZ=True)
class MovementUploadJSONTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(email="u@test.local", password="pass1234")
        self.client.force_authenticate(self.user)
        timezone.activate(ZoneInfo("Europe/Vilnius"))

    def _make_payload(self) -> dict:
        return {
            "movements": [
                {
                    "latitude": 54.6872,
                    "longitude": 25.2797,
                    "timestamp": "2025-09-08T10:10:00+03:00",
                },
                {
                    "latitude": 54.6873,
                    "longitude": 25.2798,
                    "timestamp": "2025-09-08T10:40:00+03:00",
                },
            ]
        }

    def test_upload_creates_movements_and_air_exposure_log(self):
        payload = self._make_payload()

        bucket = timezone.make_aware(timezone.datetime(2025, 9, 8, 10, 0))
        aq_sample = AQSample(
            timestamp=bucket,
            aqi=3,
            pm25=18.0,
            pm10=30.0,
            no2=22.0,
            so2=3.0,
            co=150.0,
            o3=60.0,
            temperature=None,
            humidity=None,
            wind_speed=None,
            provider="OWM",
            data_quality="ok",
        )

        with patch(
            "api.services.air_exposure.fetch_aq_for_bucket", return_value=aq_sample
        ):
            url = reverse("movements-upload-json")
            resp = self.client.post(url, payload, format="json")

        self.assertIn(resp.status_code, (status.HTTP_201_CREATED, 207), resp.data)

        self.assertEqual(Movement.objects.filter(user=self.user).count(), 2)

        self.assertEqual(AirExposureLog.objects.filter(user=self.user).count(), 1)
        log = AirExposureLog.objects.get(user=self.user)

        self.assertAlmostEqual(float(log.pm25), 18.0, places=2)
        self.assertAlmostEqual(float(log.pm10), 30.0, places=2)
        self.assertGreater(log.exposure_minutes, 0)
        local_hour = log.timestamp.astimezone(timezone.get_current_timezone()).hour
        self.assertEqual(local_hour, 10)

        vilnius = ZoneInfo("Europe/Vilnius")
        date_local = timezone.localtime(
            AirExposureLog.objects.filter(user=self.user).first().timestamp, vilnius
        ).date()

        daily = DailyExposure.objects.get(user=self.user, date=date_local)
        self.assertEqual(daily.exposure_level, "Very Good")

        recompute_daily_exposure(self.user.id, date_local)

        Exposure = apps.get_model("api", "Exposure")
        exp = Exposure.objects.get(user=self.user, timestamp=date_local)
        self.assertGreaterEqual(exp.exposure_level, 0.0)
        self.assertIn("pm25_avg_24h", exp.pollutants)

    def test_bad_json_returns_errors(self):
        url = reverse("movements-upload-json")
        resp = self.client.post(
            url,
            {
                "movements": [
                    {
                        "latitude": 1,
                        "longitude": 2,
                    }
                ]
            },
            format="json",
        )
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("errors", resp.data)
