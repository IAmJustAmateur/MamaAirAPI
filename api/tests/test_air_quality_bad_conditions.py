# api/tests/test_air_quality_bad_conditions.py
from __future__ import annotations

from django.apps import apps
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework import status
from django.core.files.uploadedfile import SimpleUploadedFile
from django.utils import timezone
from zoneinfo import ZoneInfo
from unittest.mock import patch

from api.services.air_exposure import AQSample
from api.services.air_exposure_daily import recompute_daily_exposure

Movement = apps.get_model("api", "Movement")
AirExposureLog = apps.get_model("api", "AirExposureLog")
Exposure = apps.get_model("api", "Exposure")


@override_settings(
    CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}},
    TIME_ZONE="Europe/Vilnius",
    USE_TZ=True,
)
class BadAirQualityReactionTests(APITestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(email="aq@test.local", password="pass1234")
        self.client.force_authenticate(self.user)
        self.vilnius = ZoneInfo("Europe/Vilnius")

    def _csv_for_bucket(self, bucket_local_dt) -> SimpleUploadedFile:
        """
        Создаёт CSV с двумя точками внутри одного часового бакета (локальное время).
        """
        t1 = (bucket_local_dt + timezone.timedelta(minutes=10)).isoformat()
        t2 = (bucket_local_dt + timezone.timedelta(minutes=40)).isoformat()
        csv_content = (
            "latitude,longitude,timestamp\n"
            f"54.6872,25.2797,{t1}\n"
            f"54.6873,25.2798,{t2}\n"
        )
        return SimpleUploadedFile(
            "movements.csv", csv_content.encode("utf-8"), content_type="text/csv"
        )

    def _aq(
        self,
        bucket_local_dt,
        pm25,
        pm10=30.0,
        no2=20.0,
        so2=3.0,
        co=150.0,
        o3=60.0,
        aqi=3,
    ) -> AQSample:
        """
        Формирует AQSample для заданного локального бакета (сконвертирует в aware dt).
        Единицы — µg/m³.
        """
        bucket_local_dt = bucket_local_dt.replace(minute=0, second=0, microsecond=0)
        bucket_aware = (
            bucket_local_dt
            if bucket_local_dt.tzinfo
            else timezone.make_aware(bucket_local_dt, self.vilnius)
        )
        return AQSample(
            timestamp=bucket_aware,
            aqi=aqi,
            pm25=pm25,
            pm10=pm10,
            no2=no2,
            so2=so2,
            co=co,
            o3=o3,
            temperature=None,
            humidity=None,
            wind_speed=None,
            provider="TEST",
            data_quality="ok",
        )

    def test_exposure_increases_when_air_quality_worsens(self):
        # Выберем сегодняшний день и два часа (H1, H2)
        now_local = timezone.now().astimezone(self.vilnius)
        day_local = now_local.date()
        h1 = now_local.replace(
            hour=max(1, now_local.hour - 3), minute=0, second=0, microsecond=0
        )
        h2 = now_local.replace(
            hour=max(2, now_local.hour - 2), minute=0, second=0, microsecond=0
        )

        # 1) Загружаем бакет H1 с «чистым» воздухом (низкий PM2.5)
        clean_csv = self._csv_for_bucket(h1)
        clean_sample = self._aq(h1, pm25=8.0, pm10=15.0)  # чистый
        with patch(
            "api.services.air_exposure.fetch_aq_for_bucket", return_value=clean_sample
        ):
            url = reverse("movements-upload")
            resp1 = self.client.post(url, {"file": clean_csv}, format="multipart")
        self.assertIn(resp1.status_code, (status.HTTP_201_CREATED, 207), resp1.data)

        # Пересчёт exposure за день
        recompute_daily_exposure(self.user.id, day_local)
        exp1 = Exposure.objects.get(user=self.user, timestamp=day_local)
        self.assertGreaterEqual(exp1.exposure_level, 0.0)
        base_level = exp1.exposure_level

        # Контроль: в логах должен быть хотя бы один час
        self.assertGreaterEqual(
            AirExposureLog.objects.filter(user=self.user).count(), 1
        )

        # 2) Загружаем бакет H2 с «плохим» воздухом (высокий PM2.5)
        bad_csv = self._csv_for_bucket(h2)
        bad_sample = self._aq(h2, pm25=85.0, pm10=100.0)  # сильно хуже
        with patch(
            "api.services.air_exposure.fetch_aq_for_bucket", return_value=bad_sample
        ):
            resp2 = self.client.post(url, {"file": bad_csv}, format="multipart")
        self.assertIn(resp2.status_code, (status.HTTP_201_CREATED, 207), resp2.data)

        # Пересчитываем exposure снова
        recompute_daily_exposure(self.user.id, day_local)
        exp2 = Exposure.objects.get(user=self.user, timestamp=day_local)

        # Должен вырасти общий уровень (по умолчанию это pm25_avg_24h)
        self.assertGreater(exp2.exposure_level, base_level)

        # Доп.проверки: в часовых логах есть обе записи и «плохой» час действительно плохой
        logs = AirExposureLog.objects.filter(user=self.user).order_by("timestamp")
        self.assertGreaterEqual(logs.count(), 2)

        # Найдём лог, соответствующий H2, в локальном времени
        log_h2 = None
        for lg in logs:
            local_dt = timezone.localtime(lg.timestamp, self.vilnius)
            if local_dt.hour == h2.hour and local_dt.date() == h2.date():
                log_h2 = lg
                break
        self.assertIsNotNone(log_h2, "Не нашли лог для второго бакета (H2)")
        self.assertIsNotNone(log_h2.pm25)
        self.assertGreater(
            float(log_h2.pm25), float(logs.first().pm25)
        )  # второй час хуже первого
