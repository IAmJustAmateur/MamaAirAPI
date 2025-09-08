# api/tests/test_movement_upload_csv.py
from __future__ import annotations

from django.apps import apps
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework import status
from unittest.mock import patch
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone

from zoneinfo import ZoneInfo

# Импортируем AQSample из сервиса, чтобы вернуть его из мока
from api.services.air_exposure import AQSample

Movement = apps.get_model("api", "Movement")
AirExposureLog = apps.get_model("api", "AirExposureLog")


@override_settings(
    # изолируем кэш для тестов
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}}
)
@override_settings(TIME_ZONE="Europe/Vilnius", USE_TZ=True)
class MovementUploadCSVTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(email="u@test.local", password="pass1234")
        self.client.force_authenticate(self.user)
        timezone.activate(ZoneInfo("Europe/Vilnius"))

    def _make_csv_file(self) -> SimpleUploadedFile:
        # Две точки в одном часу и одной «сети» (round(lat/lon, 2))
        csv_content = (
            "latitude,longitude,timestamp\n"
            "54.6872,25.2797,2025-09-08T10:10:00+03:00\n"
            "54.6873,25.2798,2025-09-08T10:40:00+03:00\n"
        )
        return SimpleUploadedFile(
            "movements.csv",
            csv_content.encode("utf-8"),
            content_type="text/csv",
        )

    def test_upload_creates_movements_and_air_exposure_log(self):
        file = self._make_csv_file()

        # Готовим детерминированный ответ провайдера AQ
        bucket = timezone.make_aware(timezone.datetime(2025, 9, 8, 10, 0))
        aq_sample = AQSample(
            timestamp=bucket,
            aqi=3,  # шкала 1..5 у OWM
            pm25=18.0,  # µg/m³
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
            url = reverse("movements-upload")
            resp = self.client.post(url, {"file": file}, format="multipart")

        self.assertIn(resp.status_code, (status.HTTP_201_CREATED, 207), resp.data)

        # Проверяем, что движения записались
        self.assertEqual(Movement.objects.filter(user=self.user).count(), 2)

        # И что создался ровно один часовой лог экспозиции
        self.assertEqual(AirExposureLog.objects.filter(user=self.user).count(), 1)
        log = AirExposureLog.objects.get(user=self.user)

        # Значения из мока попали в лог
        self.assertAlmostEqual(float(log.pm25), 18.0, places=2)
        self.assertAlmostEqual(float(log.pm10), 30.0, places=2)
        self.assertGreater(log.exposure_minutes, 0)
        # Бакет — начало часа 10:00 локального TZ
        local_hour = log.timestamp.astimezone(timezone.get_current_timezone()).hour
        self.assertEqual(local_hour, 10)

    def test_bad_csv_returns_errors(self):
        bad_csv = SimpleUploadedFile(
            "bad.csv",
            b"lat,lon,time\n1,2,2025-01-01T00:00:00Z\n",  # неверные заголовки
            content_type="text/csv",
        )
        url = reverse("movements-upload")
        resp = self.client.post(url, {"file": bad_csv}, format="multipart")
        self.assertEqual(resp.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("errors", resp.data)
