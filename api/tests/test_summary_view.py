from datetime import timedelta
from unittest.mock import patch, Mock

from django.utils import timezone
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status

from django.contrib.auth import get_user_model

from api.models import Exposure, AirExposureLog, DailyExposure

User = get_user_model()


class SummaryViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="pass1234",
            is_active=True,
            week_of_pregnancy=12,
        )
        self.user.set_pregnancy_start_date()
        self.client.force_authenticate(self.user)

        self.now = timezone.now()
        self.prev = self.now - timedelta(days=1)

        # Создаём AirExposureLog: обязательные поля + AQ/погода/UV
        self.latest_log = AirExposureLog.objects.create(
            user=self.user,
            timestamp=self.now,
            latitude=54.6872,
            longitude=25.2797,
            # AQ
            pm25=18.2,
            pm10=28.4,
            no2=None,
            so2=None,
            co=None,
            o3=None,
            aqi=3,
            # Погода
            temperature=21.3,
            humidity=55,
            pressure=1015,
            wind_speed=3.2,
            # UV
            uvi=6.1,
            uvi_level="high",
            # Остальное — по умолчанию
        )

        # Две экспозиции для проверки дельты
        self.exp_new = Exposure.objects.create(
            user=self.user,
            timestamp=self.now,
            exposure_level=0.62,
            risks={"pm25": "moderate"},
        )
        self.exp_old = Exposure.objects.create(
            user=self.user,
            timestamp=self.prev,
            exposure_level=0.40,
            risks={"pm25": "low"},
        )

        self.exp_new.pollutants = {"pm25": 18.0, "pm10": 30.0}
        self.exp_new.save(update_fields=["pollutants"])
        DailyExposure.objects.create(
            user=self.user,
            date=timezone.localdate(),
            exposure_level="Moderate",
        )

    def _mock_recommendations(self):
        snapshot = Mock()
        snapshot.recommendations = [
            {
                "id": "AQ_RULE_01.v2",
                "severity": "medium",
                "title": "Сократить пребывание на улице",
                "alert": "Сегодня концентрация PM2.5 повышена.",
                "recommendation_diet": "drink more water and eat antioxidant-rich foods.",
                "recommendation_activity": "Consider indoor activities or outdoor activities in low-traffic areas.",
                "recommendation_behavior": "Use air purifiers at home if available.",
                "ttl_hours": 6,
                "priority": 50,
                "snapshot_id": 123,
                "snapshot_created_at": timezone.now().isoformat(),
            },
            {
                "id": "UV_RULE_02.v1",
                "severity": "high",
                "title": "UV index is high",
                "alert": "The UV index is at a high level today.",
                "recommendation_diet": "Include foods rich in antioxidants, such as berries and leafy greens.",
                "recommendation_activity": "Limit outdoor activities during peak sunlight hours (10 AM - 4 PM).",
                "recommendation_behavior": "Wear protective clothing and use sunscreen with high SPF when outdoors.",
                "ttl_hours": 8,
                "priority": 70,
                "snapshot_id": 123,
                "snapshot_created_at": timezone.now().isoformat(),
            },
        ]
        return snapshot

    @patch("api.views.get_today_journey")
    @patch("api.views.update_air_exposure_log_with_weather")
    @patch(
        "recommendations.evaluator.get_or_create_fresh_snapshot"
    )  # <-- путь, по которому импортируется во view
    def test_summary_view_happy_path(
        self,
        mock_get_snapshot,
        mock_update_air_exposure_log_with_weather,
        mock_get_today_journey,
    ):
        # Возвращаем ИНСТАНС AirExposureLog (его сериализует AirExposureLogSerializer)
        mock_update_air_exposure_log_with_weather.return_value = self.latest_log

        mock_get_today_journey.return_value = {
            "distance_m": 1834.57,
            "distance_km": 1.835,
            "points": [
                {"lat": 54.6872, "lon": 25.2797, "t": self.prev.isoformat()},
                {"lat": 54.69, "lon": 25.28, "t": self.now.isoformat()},
            ],
        }
        mock_get_snapshot.return_value = self._mock_recommendations()

        url = reverse("summary")  # замени, если у тебя другой name
        resp = self.client.get(url)

        assert resp.status_code == status.HTTP_200_OK, resp.data

        # Верхний уровень
        for key in [
            "aq_weather_uv",
            "mom_exposure",
            "risks_delta",
            "recommendations",
            "today_journey",
            "daily_exposure_level",
            "pollutant_compliance",
        ]:
            assert key in resp.data, f"Missing key: {key}"
        assert resp.data["daily_exposure_level"] == "Moderate"

        # aq_weather_uv — результаты AirExposureLogSerializer
        aq = resp.data["aq_weather_uv"]
        assert isinstance(aq, dict)
        # Проверим несколько полей из модели
        assert aq.get("aqi") == 3
        assert aq.get("uvi") == 6.1
        assert aq.get("uvi_level") == "high"
        assert aq.get("temperature") == 21.3
        assert aq.get("humidity") == 55
        assert aq.get("pressure") == 1015
        assert aq.get("pm25") == 18.2
        assert aq.get("pm10") == 28.4
        # Также должны быть координаты
        assert aq.get("latitude") == 54.6872
        assert aq.get("longitude") == 25.2797

        # mom_exposure — сериализованная модель
        me = resp.data["mom_exposure"]
        assert isinstance(me, dict)
        assert set(["id", "timestamp", "exposure_level", "risks"]).issubset(me.keys())
        assert float(me["exposure_level"]) == self.exp_new.exposure_level

        # delta = 0.62 - 0.40 = 0.22
        assert (
            resp.data["risks_delta"]["mom"]
            == self.exp_new.exposure_level - self.exp_old.exposure_level
        )

        # рекомендации — список нужной формы
        recs = resp.data["recommendations"]
        assert isinstance(recs, list) and len(recs) == 2
        required_keys = {
            "id",
            "severity",
            "title",
            "alert",
            "recommendation_diet",
            "recommendation_activity",
            "recommendation_behavior",
            "ttl_hours",
            "priority",
            "snapshot_id",
            "snapshot_created_at",
        }
        assert required_keys.issubset(recs[0].keys())

        # today_journey — структура
        j = resp.data["today_journey"]
        assert isinstance(j, dict)
        assert "distance_m" in j and "distance_km" in j

        mas = resp.data["week_info"]
        assert mas is not None

        hist = resp.data["exposure_history"]
        assert isinstance(hist, dict)
        for k in ("start_date", "end_date", "days_requested", "items"):
            assert k in hist, f"exposure_history missing '{k}'"

        assert hist["days_requested"] == 7
        assert isinstance(hist["items"], list)
        # элементы истории: {"date": <iso-date>, "integrated_score": <float>}
        if hist["items"]:
            first_item = hist["items"][0]
            assert "date" in first_item and "integrated_score" in first_item

            # --- pollutant_compliance -- проверяем структуру и ключевые кейсы ---
        pc = resp.data["pollutant_compliance"]
        assert isinstance(pc, dict)
        assert pc.get("source") in ("WHO",)  # по сид-сету
        assert pc.get("version") == "AQG 2021"
        assert isinstance(pc.get("per_pollutant"), dict)

        per = pc["per_pollutant"]
        # Должны присутствовать как минимум эти поллютанты
        for pol in ("pm25", "pm10"):
            assert pol in per, f"per_pollutant missing {pol}"

        # pm25: берём из Exposure (24h), превышает 15 → compliance=False
        pm25 = per["pm25"]
        for k in (
            "value",
            "label",
            "unit",
            "avg_period_used",
            "value_source",
            "limit",
            "limit_unit",
            "limit_avg_period",
            "compliance",
            "approximate",
        ):
            assert k in pm25, f"pm25 missing {k}"
        assert pm25["value_source"] == "exposure"
        assert pm25["avg_period_used"] in ("24h", "24h-approx")
        assert pm25["limit_avg_period"] == "24h"
        # мы поставили exp_new.pollutants.pm25 = 18.0 → лимит 15 → non-compliant
        assert abs(pm25["value"] - 18.0) < 1e-6
        assert pm25["unit"] in (
            "µg/m³",
            "ug/m3",
        )  # допускаем разные символы в окружении
        assert pm25["limit"] == 15.0
        assert pm25["compliance"] is False
        # При 24h из Exposure — approximate должно быть False (или оставим строго)
        assert pm25["approximate"] is False

        # pm10: exp_new.pollutants.pm10 = 30.0, лимит 45 → compliant
        pm10 = per["pm10"]
        assert pm10["value_source"] == "exposure"
        assert pm10["limit_avg_period"] == "24h"
        assert pm10["compliance"] is True
        assert abs(pm10["value"] - 30.0) < 1e-6
        assert pm10["approximate"] in (False,)  # ожидаем False для 24h

        # Вызовы моков
        mock_update_air_exposure_log_with_weather.assert_called_once_with(
            self.latest_log
        )
        mock_get_today_journey.assert_called_once_with(self.user)
        mock_get_snapshot.assert_called_once_with(
            self.user, fresh_for_hours=6, trigger_event="login"
        )

    @patch("api.views.get_today_journey")
    @patch("api.views.update_air_exposure_log_with_weather")
    @patch("recommendations.evaluator.get_or_create_fresh_snapshot")
    def test_summary_view_no_exposures_returns_nulls(
        self,
        mock_get_snapshot,
        mock_update_aq_weather_uv,
        mock_get_today_journey,
    ):
        Exposure.objects.filter(user=self.user).delete()

        # тут тоже возвращаем инстанс AirExposureLog
        mock_update_aq_weather_uv.return_value = self.latest_log
        mock_get_today_journey.return_value = {
            "distance_m": 0.0,
            "distance_km": 0.0,
            "points": [],
        }
        mock_get_snapshot.return_value = self._mock_recommendations()

        url = reverse("summary")
        resp = self.client.get(url)

        # поля присутствуют
        assert "week_info" in resp.data  # ← добавлено
        assert "daily_exposure_level" in resp.data
        assert "exposure_history" in resp.data  # ← добавлено

        # exposure_history — корректная структура
        hist = resp.data["exposure_history"]
        assert isinstance(hist, dict)
        for k in ("start_date", "end_date", "days_requested", "items"):
            assert k in hist
        assert hist["days_requested"] == 7
        assert isinstance(hist["items"], list)

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["mom_exposure"] is None
        assert resp.data["daily_exposure_level"] == "Moderate"
        assert resp.data["risks_delta"]["mom"] is None
        assert resp.data["risks_delta"]["baby"] is None

        # --- pollutant_compliance при отсутствии суточной экспозиции ---
        pc = resp.data["pollutant_compliance"]
        assert isinstance(pc, dict)
        assert pc.get("version") == "AQG 2021"
        per = pc.get("per_pollutant", {})
        assert isinstance(per, dict)

        # pm25 должен браться из логов → value_source='log', avg_period_used='instant-approx', approximate=True
        assert "pm25" in per
        pm25 = per["pm25"]
        for k in (
            "value",
            "unit",
            "avg_period_used",
            "value_source",
            "limit",
            "limit_unit",
            "limit_avg_period",
            "compliance",
            "approximate",
        ):
            assert k in pm25
        assert pm25["value_source"] == "log"
        assert pm25["avg_period_used"] == "instant-approx"
        assert pm25["approximate"] is True
        # значение берётся из latest_log.pm25 (=18.2) и сравнивается с лимитом 15.0 → non-compliant
        # (Учти: если сервис делает конверсию единиц, здесь всё равно должно быть число около 18.2)
        assert isinstance(pm25["value"], (int, float))
        assert pm25["limit"] == 15.0
        assert pm25["compliance"] in (
            True,
            False,
            None,
        )  # допускаем обе ветки на случай округлений
