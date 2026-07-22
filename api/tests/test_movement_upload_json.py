# api/tests/test_movement_upload_json.py
from __future__ import annotations

from django.apps import apps
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.test import override_settings
from rest_framework.test import APITestCase
from rest_framework import status
from unittest.mock import patch
from datetime import timedelta
from django.utils import timezone

from zoneinfo import ZoneInfo

from api.services.air_exposure_daily import recompute_daily_exposure
from api.services.air_exposure import (
    AQSample,
    MOVEMENT_BULK_CREATE_BATCH_SIZE,
    ingest_movements_batch,
)
from api.services.coordinate_encryption import decrypt_coordinates
from api.services.h3_grid import latlng_to_cell

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

    def _make_aq_sample(self) -> AQSample:
        bucket = timezone.make_aware(timezone.datetime(2025, 9, 8, 10, 0))
        return AQSample(
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

    def test_upload_creates_movements_and_air_exposure_log(self):
        payload = self._make_payload()

        aq_sample = self._make_aq_sample()

        with patch(
            "api.services.air_exposure.fetch_aq_for_bucket", return_value=aq_sample
        ):
            url = reverse("movements-upload-json")
            resp = self.client.post(url, payload, format="json")

        self.assertIn(resp.status_code, (status.HTTP_201_CREATED, 207), resp.data)
        self.assertTrue(
            {
                "status",
                "imported",
                "air_exposure_created",
                "air_exposure_updated",
                "exposures_recomputed",
                "exposure_errors",
                "errors",
            }.issubset(resp.data.keys())
        )

        movements = list(
            Movement.objects.filter(user=self.user).order_by("timestamp")
        )
        self.assertEqual(len(movements), 2)
        for movement, source in zip(movements, payload["movements"]):
            with self.subTest(timestamp=movement.timestamp):
                self.assertEqual(
                    movement.h3_cell,
                    latlng_to_cell(source["latitude"], source["longitude"]),
                )
                self.assertIsNotNone(movement.coordinates_encrypted)
                self.assertEqual(movement.coordinates_key_version, 1)
                self.assertIsNone(movement.coordinates_purged_at)

                decrypted = decrypt_coordinates(
                    movement.coordinates_encrypted,
                    movement.coordinates_key_version,
                )
                self.assertAlmostEqual(
                    decrypted.latitude, source["latitude"], places=7
                )
                self.assertAlmostEqual(
                    decrypted.longitude, source["longitude"], places=7
                )

        self.assertEqual(AirExposureLog.objects.filter(user=self.user).count(), 1)
        log = AirExposureLog.objects.get(user=self.user)

        self.assertAlmostEqual(float(log.pm25), 18.0, places=2)
        self.assertAlmostEqual(float(log.pm10), 30.0, places=2)
        self.assertGreater(log.exposure_minutes, 0)
        self.assertEqual(
            log.h3_cell,
            latlng_to_cell(log.latitude, log.longitude),
        )
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

    def test_reupload_same_payload_keeps_single_air_exposure_log(self):
        payload = self._make_payload()
        aq_sample = self._make_aq_sample()
        url = reverse("movements-upload-json")

        with patch(
            "api.services.air_exposure.fetch_aq_for_bucket", return_value=aq_sample
        ):
            first_response = self.client.post(url, payload, format="json")
            second_response = self.client.post(url, payload, format="json")

        self.assertIn(
            first_response.status_code,
            (status.HTTP_201_CREATED, 207),
            first_response.data,
        )
        self.assertIn(
            second_response.status_code,
            (status.HTTP_201_CREATED, 207),
            second_response.data,
        )
        self.assertEqual(
            AirExposureLog.objects.filter(user=self.user).count(),
            1,
        )

    @override_settings(MOVEMENT_COORDINATE_KEYS={})
    def test_missing_encryption_key_rejects_batch_without_writes(self):
        url = reverse("movements-upload-json")
        resp = self.client.post(url, self._make_payload(), format="json")

        self.assertEqual(resp.status_code, status.HTTP_500_INTERNAL_SERVER_ERROR)
        self.assertEqual(Movement.objects.filter(user=self.user).count(), 0)
        self.assertEqual(AirExposureLog.objects.filter(user=self.user).count(), 0)

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

    def test_ingest_uses_batched_bulk_create(self):
        records = [
            {"lat": 54.6872, "lon": 25.2797, "ts": timezone.now(), "indoor": False},
            {
                "lat": 54.6873,
                "lon": 25.2798,
                "ts": timezone.now() + timedelta(minutes=5),
                "indoor": False,
            },
        ]

        with (
            patch(
                "api.services.air_exposure.Movement.objects.bulk_create"
            ) as bulk_create,
            patch(
                "api.services.air_exposure.fetch_aq_for_bucket",
                return_value=self._make_aq_sample(),
            ),
            patch(
                "api.services.air_exposure.upsert_air_exposure_log",
                return_value=(True, None),
            ),
            patch("api.services.air_exposure.upsert_daily_exposure"),
        ):
            summary = ingest_movements_batch(user_id=self.user.id, records=records)

        self.assertEqual(summary["imported"], len(records))
        bulk_create.assert_called_once()
        self.assertEqual(
            bulk_create.call_args.kwargs["batch_size"],
            MOVEMENT_BULK_CREATE_BATCH_SIZE,
        )

    def test_large_json_upload_persists_movements(self):
        start = timezone.make_aware(timezone.datetime(2025, 9, 8, 10, 0))
        movement_count = MOVEMENT_BULK_CREATE_BATCH_SIZE + 25
        payload = {
            "movements": [
                {
                    "latitude": 54.6872 + (idx % 5) * 0.00001,
                    "longitude": 25.2797 + (idx % 5) * 0.00001,
                    "timestamp": (start + timedelta(seconds=idx)).isoformat(),
                }
                for idx in range(movement_count)
            ]
        }

        with patch(
            "api.services.air_exposure.fetch_aq_for_bucket",
            return_value=self._make_aq_sample(),
        ):
            url = reverse("movements-upload-json")
            resp = self.client.post(url, payload, format="json")

        self.assertIn(resp.status_code, (status.HTTP_201_CREATED, 207), resp.data)
        self.assertEqual(resp.data["imported"], movement_count)
        self.assertEqual(
            Movement.objects.filter(user=self.user).count(),
            movement_count,
        )
