# tests/test_today_journey.py
from datetime import timedelta
from datetime import timezone as dt_timezone
from math import isclose

from django.test import TestCase
from django.utils import timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from pytz import timezone as ZoneInfo

from api.models import User, Movement
from api.services.analytics import get_today_journey  # поправь путь


def haversine_m(lat1, lon1, lat2, lon2):
    # локальная копия формулы из utils, чтобы валидировать подсчет
    from math import radians, sin, cos, asin, sqrt

    R = 6371008.8
    φ1, λ1, φ2, λ2 = map(radians, (lat1, lon1, lat2, lon2))
    dφ, dλ = (φ2 - φ1), (λ2 - λ1)
    a = sin(dφ / 2) ** 2 + cos(φ1) * cos(φ2) * sin(dλ / 2) ** 2
    c = 2 * asin(min(1.0, sqrt(a)))
    return R * c


class GetTodayJourneyTests(TestCase):
    def setUp(self):
        self.tz = "Europe/Vilnius"
        self.tzinfo = ZoneInfo(self.tz)
        self.user = User.objects.create_user(email="u@example.com", password="x")
        now_local = timezone.now().astimezone(self.tzinfo)
        self.today_start_local = now_local.replace(
            hour=0, minute=0, second=0, microsecond=0
        )
        self.today_end_local = self.today_start_local + timedelta(days=1)

    def _mk_ts(self, minutes_from_midnight):
        return (
            self.today_start_local + timedelta(minutes=minutes_from_midnight)
        ).astimezone(dt_timezone.utc)

    def test_straight_north_route_today_only(self):
        """
        Маршрут: 5 точек строго к северу, по ~500 м между точками (всего ~2 км).
        Плюс одна точка вчера — она не должна попасть в расчет.
        Точки создаём в обратном порядке, чтобы проверить сортировку по времени внутри функции.
        """
        lat0, lon0 = 54.6872, 25.2797  # Вильнюс, для примера
        step_m = 500.0
        # 1 градус широты ~ 111_320 м => 500 м ~ 0.0044916°
        step_lat_deg = step_m / 111_320.0

        # 5 точек в течение сегодняшнего дня
        coords = [(lat0 + i * step_lat_deg, lon0) for i in range(5)]  # 0..4
        times = [self._mk_ts(m) for m in (10, 30, 60, 120, 180)]  # возрастают

        # добавим «вчерашнюю» точку, которую нужно проигнорировать
        Movement.objects.create(
            user=self.user,
            latitude=lat0 - step_lat_deg,
            longitude=lon0,
            timestamp=(self.today_start_local - timedelta(minutes=1)).astimezone(
                dt_timezone.utc
            ),
        )

        # создаём сегодняшние точки в обратном порядке времени
        for (lat, lon), ts in reversed(list(zip(coords, times))):
            Movement.objects.create(
                user=self.user, latitude=lat, longitude=lon, timestamp=ts
            )

        # ожидаемая длина по гаверсинусу
        expected_m = 0.0
        for (lat1, lon1), (lat2, lon2) in zip(coords[:-1], coords[1:]):
            expected_m += haversine_m(lat1, lon1, lat2, lon2)

        result = get_today_journey(self.user, tz=self.tz)

        # Проверяем количество учтённых точек и расстояние
        self.assertEqual(result["points"], 5)
        # допускаем маленькую погрешность
        self.assertTrue(
            isclose(result["distance_m"], expected_m, rel_tol=1e-5, abs_tol=0.05)
        )
        self.assertTrue(
            isclose(
                result["distance_km"], expected_m / 1000.0, rel_tol=1e-5, abs_tol=0.05
            )
        )

    def test_timezone_matters(self):
        """
        Граничный случай: точка ровно в 00:00 локального времени должна попадать в «сегодня».
        А точка ровно в 00:00 вчера — нет.
        """
        lat, lon = 54.6872, 25.2797

        ts_today_0000_local = self.today_start_local.astimezone(dt_timezone.utc)
        ts_yesterday_0000_local = (
            self.today_start_local - timedelta(days=1)
        ).astimezone(dt_timezone.utc)

        Movement.objects.create(
            user=self.user,
            latitude=lat,
            longitude=lon,
            timestamp=ts_yesterday_0000_local,
        )
        Movement.objects.create(
            user=self.user,
            latitude=lat + 0.001,
            longitude=lon,
            timestamp=ts_today_0000_local,
        )

        result = get_today_journey(self.user, tz=self.tz)
        self.assertEqual(result["points"], 1)  # только сегодняшняя точка
