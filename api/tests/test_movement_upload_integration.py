# api/tests/test_movement_upload_csv_integration.py
from __future__ import annotations

from django.apps import apps
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test import override_settings
from django.conf import settings
from rest_framework.test import APITestCase
from rest_framework import status
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from zoneinfo import ZoneInfo

Movement = apps.get_model("api", "Movement")
AirExposureLog = apps.get_model("api", "AirExposureLog")


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    USE_TZ=True,
)
class MovementUploadCSVIntegrationOWMTests(APITestCase):
    """Интеграционный тест с реальным запросом к OWM (если задан OWM_API_KEY)."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            email="owm@test.local", password="pass1234"
        )
        self.client.force_authenticate(self.user)

    def _csv_for_bucket_two_points(self) -> SimpleUploadedFile:
        # Берём бакет ~2 часа назад в зоне Вильнюса, чтобы точно был «прошедший» час
        vilnius = ZoneInfo("Europe/Vilnius")
        now_vilnius = timezone.now().astimezone(vilnius)
        bucket = now_vilnius.replace(
            minute=0, second=0, microsecond=0
        ) - timezone.timedelta(hours=2)

        t1 = (bucket + timezone.timedelta(minutes=10)).isoformat()
        t2 = (bucket + timezone.timedelta(minutes=40)).isoformat()

        # Две точки в центре Вильнюса (54.6872, 25.2797)
        csv_content = (
            "latitude,longitude,timestamp\n"
            f"54.6872,25.2797,{t1}\n"
            f"54.6873,25.2798,{t2}\n"
        )
        return SimpleUploadedFile(
            "movements.csv", csv_content.encode("utf-8"), content_type="text/csv"
        )

    def test_upload_real_owm(self):
        # Если нет ключа — пропускаем тест, чтобы CI не падал
        owm_key = getattr(settings, "OWM_API_KEY", None)
        if not owm_key:
            self.skipTest(
                "OWM_API_KEY is not configured; skipping real OWM integration test."
            )

        file = self._csv_for_bucket_two_points()
        url = reverse("movements-upload")

        resp = self.client.post(url, {"file": file}, format="multipart")
        self.assertIn(resp.status_code, (status.HTTP_201_CREATED, 207), resp.data)

        # Движения записались
        self.assertEqual(Movement.objects.filter(user=self.user).count(), 2)

        # Должен появиться хотя бы один часовой лог
        logs = AirExposureLog.objects.filter(user=self.user)
        self.assertGreaterEqual(logs.count(), 1)

        log = logs.order_by("-timestamp").first()

        # Источник — OWM (как задано в fetch_aq_for_bucket)
        # data_quality может быть "ok" или "gap" в зависимости от наличия данных
        self.assertIn(
            getattr(log, "aqi", None) is None or isinstance(log.aqi, int), (True,)
        )
        # Проверим диапазон значений, если есть данные
        if log.pm25 is not None:
            self.assertGreaterEqual(float(log.pm25), 0.0)
        if log.pm10 is not None:
            self.assertGreaterEqual(float(log.pm10), 0.0)

        # Покрытие должно быть > 0
        self.assertIsNotNone(log.exposure_minutes)
        self.assertGreater(int(log.exposure_minutes), 0)


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    USE_TZ=True,
)
class MovementUploadJSONIntegrationOWMTests(APITestCase):
    """Интеграционный тест JSON endpoint с реальным запросом к OWM (если задан OWM_API_KEY)."""

    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(
            email="owm-json@test.local", password="pass1234"
        )
        self.client.force_authenticate(self.user)

    def _payload_for_bucket_two_points(self) -> dict:
        vilnius = ZoneInfo("Europe/Vilnius")
        now_vilnius = timezone.now().astimezone(vilnius)
        bucket = now_vilnius.replace(
            minute=0, second=0, microsecond=0
        ) - timezone.timedelta(hours=2)

        t1 = (bucket + timezone.timedelta(minutes=10)).isoformat()
        t2 = (bucket + timezone.timedelta(minutes=40)).isoformat()

        return {
            "movements": [
                {
                    "latitude": 54.6872,
                    "longitude": 25.2797,
                    "timestamp": t1,
                },
                {
                    "latitude": 54.6873,
                    "longitude": 25.2798,
                    "timestamp": t2,
                },
            ]
        }

    def test_upload_real_owm(self):
        owm_key = getattr(settings, "OWM_API_KEY", None)
        if not owm_key:
            self.skipTest(
                "OWM_API_KEY is not configured; skipping real OWM integration test."
            )

        payload = self._payload_for_bucket_two_points()
        url = reverse("movements-upload-json")

        resp = self.client.post(url, payload, format="json")
        self.assertIn(resp.status_code, (status.HTTP_201_CREATED, 207), resp.data)

        self.assertEqual(Movement.objects.filter(user=self.user).count(), 2)

        logs = AirExposureLog.objects.filter(user=self.user)
        self.assertGreaterEqual(logs.count(), 1)

        log = logs.order_by("-timestamp").first()

        self.assertIn(
            getattr(log, "aqi", None) is None or isinstance(log.aqi, int), (True,)
        )
        if log.pm25 is not None:
            self.assertGreaterEqual(float(log.pm25), 0.0)
        if log.pm10 is not None:
            self.assertGreaterEqual(float(log.pm10), 0.0)

        self.assertIsNotNone(log.exposure_minutes)
        self.assertGreater(int(log.exposure_minutes), 0)
