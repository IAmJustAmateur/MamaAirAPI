# analytics/utils.py
from __future__ import annotations
from dataclasses import dataclass
from datetime import timedelta
from math import radians, sin, cos, asin, sqrt
from typing import Optional, Iterable, Tuple

from django.conf import settings
from django.utils import timezone
from datetime import timezone as dt_timezone

try:
    # Python 3.9+ стандартная библиотека
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    from pytz import timezone as ZoneInfo  # fallback, если вдруг нужно

from api.models import Movement, User  # поправь импорт под свой проект


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Расстояние между двумя точками (широта/долгота) в метрах."""
    # радиус Земли (средний) в метрах
    R = 6371008.8
    φ1, λ1, φ2, λ2 = map(radians, (lat1, lon1, lat2, lon2))
    dφ, dλ = (φ2 - φ1), (λ2 - λ1)
    a = sin(dφ / 2) ** 2 + cos(φ1) * cos(φ2) * sin(dλ / 2) ** 2
    c = 2 * asin(min(1.0, sqrt(a)))
    return R * c


@dataclass
class JourneyResult:
    distance_m: float
    distance_km: float
    points: int

    def to_dict(self) -> dict:
        return {
            "distance_m": round(self.distance_m, 2),
            "distance_km": round(self.distance_km, 3),
            "points": self.points,
        }


def _today_bounds_in_utc(
    tz: Optional[str],
) -> Tuple[timezone.datetime, timezone.datetime]:
    """
    Возвращает (start_utc, end_utc) для «сегодня» в заданном часовом поясе.
    """
    tzinfo = ZoneInfo(tz or settings.TIME_ZONE)
    now_local = timezone.now().astimezone(tzinfo)
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    start_utc = start_local.astimezone(dt_timezone.utc)
    end_utc = end_local.astimezone(dt_timezone.utc)
    return start_utc, end_utc


def get_today_journey(user: User, tz: Optional[str] = None) -> dict:
    """
    Считает длину маршрута пользователя за «сегодня» (в заданном часовом поясе)
    по таблице Movement. Возвращает dict с метрами/километрами и количеством точек.
    """
    start_utc, end_utc = _today_bounds_in_utc(tz)

    # Берём только нужные поля и сразу сортируем по времени по возрастанию
    qs = (
        Movement.objects.filter(
            user=user, timestamp__gte=start_utc, timestamp__lt=end_utc
        )
        .order_by("timestamp")
        .values_list("latitude", "longitude")
    )

    points = 0
    total_m = 0.0
    prev: Optional[Tuple[float, float]] = None

    for lat, lon in qs.iterator():
        points += 1
        if prev is not None:
            total_m += _haversine_m(prev[0], prev[1], lat, lon)
        prev = (lat, lon)

    res = JourneyResult(distance_m=total_m, distance_km=total_m / 1000.0, points=points)
    return res.to_dict()
