# services/air_exposure_daily.py
from __future__ import annotations
from datetime import timedelta, timezone as dt_timezone
from typing import Tuple, Dict

from django.apps import apps
from django.db.models import Q
from django.utils import timezone

AirExposureLog = apps.get_model("api", "AirExposureLog")
Exposure = apps.get_model("api", "Exposure")


def _day_bounds(date) -> Tuple[timezone.datetime, timezone.datetime]:
    # Возвращаем UTC-границы суток для безопасного фильтра по timestamp (который хранится в UTC)
    tz = dt_timezone.utc
    start = timezone.make_aware(
        timezone.datetime.combine(date, timezone.datetime.min.time()), tz
    )
    end = start + timedelta(days=1)
    return start, end


def _time_weighted_avg(values_minutes: list[Tuple[float | None, int]]) -> float | None:
    num = 0.0
    denom = 0
    for val, mins in values_minutes:
        if val is None or mins <= 0:
            continue
        num += float(val) * int(mins)
        denom += int(mins)
    if denom == 0:
        return None
    return num / denom


def _rolling_8h_max(values_minutes: list[Tuple[float | None, int]]) -> float | None:
    """
    Принимаем почасовые бакеты (значение, покрытие минут).
    Считаем максимум среднего по любому скользящему окну до 8 часов
    (внутри окна также минутно-взвешенно, пропуски допустимы).
    """
    n = len(values_minutes)
    best = None
    for i in range(n):
        num = 0.0
        den = 0
        for j in range(i, min(i + 8, n)):
            v, m = values_minutes[j]
            if v is None or m <= 0:
                continue
            num += float(v) * int(m)
            den += int(m)
        if den > 0:
            avg = num / den
            best = avg if best is None else max(best, avg)
    return best


def recompute_daily_exposure(user_id: int, date):
    """
    Пересчитывает суточный агрегат Exposure за указанную локальную дату пользователя.
    Берёт все hourly AirExposureLog (UTC) попавшие в эти сутки по локальному календарю —
    на старте можно считать по UTC-суткам, если все бакеты строятся из локального времени.
    """
    start_utc, end_utc = _day_bounds(date)

    logs = (
        AirExposureLog.objects.filter(
            user_id=user_id, timestamp__gte=start_utc, timestamp__lt=end_utc
        )
        .order_by("timestamp")
        .values("pm25", "pm10", "no2", "so2", "co", "o3", "aqi", "exposure_minutes")
    )

    if not logs:
        return Exposure.set_for_date(
            user=apps.get_model("api", "User").objects.get(pk=user_id),
            level=0.0,
            pollutants={
                "pm25_avg_24h": 0.0,
                "pm10_avg_24h": 0.0,
                "no2_avg_24h": 0.0,
                "o3_8h_max": None,
                "co_8h_max": None,
                "aqi_max_24h": None,
                "minutes_covered": 0,
                "hours_covered": 0,
                "data_quality": "no_data",
            },
            date=date,
        )

    # Подготовим массивы (значение, покрытие минут) по каждому загрязнителю
    vm_pm25 = [(row["pm25"], row["exposure_minutes"]) for row in logs]
    vm_pm10 = [(row["pm10"], row["exposure_minutes"]) for row in logs]
    vm_no2 = [(row["no2"], row["exposure_minutes"]) for row in logs]
    vm_so2 = [(row["so2"], row["exposure_minutes"]) for row in logs]
    vm_co = [(row["co"], row["exposure_minutes"]) for row in logs]
    vm_o3 = [(row["o3"], row["exposure_minutes"]) for row in logs]

    pm25_avg = _time_weighted_avg(vm_pm25)  # µg/m³
    pm10_avg = _time_weighted_avg(vm_pm10)
    no2_avg = _time_weighted_avg(vm_no2)

    o3_8h_max = _rolling_8h_max(vm_o3)
    co_8h_max = _rolling_8h_max(vm_co)

    aqi_max = max((row["aqi"] for row in logs if row["aqi"] is not None), default=None)

    minutes_covered = sum(int(row["exposure_minutes"] or 0) for row in logs)
    hours_covered = minutes_covered // 60
    data_quality = "ok" if minutes_covered > 0 else "no_data"

    pollutants = {
        "pm25_avg_24h": pm25_avg or 0.0,
        "pm10_avg_24h": pm10_avg or 0.0,
        "no2_avg_24h": no2_avg or 0.0,
        "o3_8h_max": o3_8h_max,
        "co_8h_max": co_8h_max,
        "aqi_max_24h": aqi_max,
        "minutes_covered": minutes_covered,
        "hours_covered": hours_covered,
        "data_quality": data_quality,
        "units": "µg/m³",
    }

    # Выбор итоговой метрики: по умолчанию — pm25 24h avg
    exposure_level = pollutants["pm25_avg_24h"]

    user = apps.get_model("api", "User").objects.get(pk=user_id)
    return Exposure.set_for_date(
        user=user, level=exposure_level, pollutants=pollutants, date=date
    )
