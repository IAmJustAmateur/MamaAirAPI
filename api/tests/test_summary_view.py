from datetime import timedelta
from unittest.mock import patch, Mock

from django.utils import timezone
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status

from django.contrib.auth import get_user_model

# Подправь импорты моделей под свой проект
from api.models import Exposure, AirExposureLog

User = get_user_model()


class SummaryViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="pass1234",
            is_active=True,
        )
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

    def _mock_recommendations(self):
        snapshot = Mock()
        snapshot.recommendations = [
            {
                "id": "AQ_RULE_01.v2",
                "severity": "medium",
                "title": "Сократить пребывание на улице",
                "message": "Сегодня концентрация PM2.5 повышена.",
                "ttl_hours": 6,
                "priority": 50,
            },
            {
                "id": "UV_RULE_02.v1",
                "severity": "high",
                "title": "Солнцезащита",
                "message": "УФ-индекс высокий, используйте крем SPF 30+.",
                "ttl_hours": 8,
                "priority": 70,
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
        ]:
            assert key in resp.data, f"Missing key: {key}"

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
        assert set(
            ["id", "severity", "title", "message", "ttl_hours", "priority"]
        ).issubset(recs[0].keys())

        # today_journey — структура
        j = resp.data["today_journey"]
        assert isinstance(j, dict)
        assert "distance_m" in j and "distance_km" in j

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

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["mom_exposure"] is None
        assert resp.data["risks_delta"]["mom"] is None
        assert resp.data["risks_delta"]["baby"] is None
