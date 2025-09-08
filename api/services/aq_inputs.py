# services/aq_inputs.py
from __future__ import annotations
from datetime import timedelta
from typing import Dict, Tuple, List

from django.apps import apps
from django.utils import timezone

AirExposureLog = apps.get_model("api", "AirExposureLog")


def _time_weighted_avg(values_minutes: List[Tuple[float | None, int]]) -> float | None:
    num, den = 0.0, 0
    for v, m in values_minutes:
        if v is None or m <= 0:
            continue
        num += float(v) * int(m)
        den += int(m)
    return num / den if den > 0 else None


def _rolling_8h_max(values_minutes: List[Tuple[float | None, int]]) -> float | None:
    n = len(values_minutes)
    best = None
    for i in range(n):
        num, den = 0.0, 0
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


def get_air_quality_inputs_for_risks_from_logs(
    user_id: int, *, hours: int = 24
) -> Dict:
    """
    Формирует входы для risk-движка за окно (по умолчанию 24 часа) из AirExposureLog.
    ВОЗВРАЩАЕТ mg/м³ для совместимости с вашим движком (конвертируем из µg/м³).
    """
    now = timezone.now()
    start = now - timedelta(hours=hours)

    logs = (
        AirExposureLog.objects.filter(
            user_id=user_id, timestamp__gte=start, timestamp__lte=now
        )
        .order_by("timestamp")
        .values("pm25", "pm10", "no2", "so2", "co", "o3", "exposure_minutes")
    )

    if not logs:
        return {
            "pm25": 0.0,
            "no2": 0.0,
            "so2": 0.0,
            "o3": 0.0,
            "co": 0.0,
            "o3_24h": 0.0,
            "co_24h": 0.0,
            "hours_covered": 0,
            "n_movements": 0,
            "data_quality": "no_data",
        }

    vm_pm25 = [(row["pm25"], row["exposure_minutes"]) for row in logs]
    vm_pm10 = [(row["pm10"], row["exposure_minutes"]) for row in logs]
    vm_no2 = [(row["no2"], row["exposure_minutes"]) for row in logs]
    vm_so2 = [(row["so2"], row["exposure_minutes"]) for row in logs]
    vm_co = [(row["co"], row["exposure_minutes"]) for row in logs]
    vm_o3 = [(row["o3"], row["exposure_minutes"]) for row in logs]

    pm25_24h = _time_weighted_avg(vm_pm25) or 0.0  # µg/м³
    pm10_24h = _time_weighted_avg(vm_pm10) or 0.0
    no2_24h = _time_weighted_avg(vm_no2) or 0.0
    so2_24h = _time_weighted_avg(vm_so2) or 0.0
    o3_24h = _time_weighted_avg(vm_o3) or 0.0
    co_24h = _time_weighted_avg(vm_co) or 0.0

    o3_8hmax = _rolling_8h_max(vm_o3) or 0.0  # µg/м³
    co_8hmax = _rolling_8h_max(vm_co) or 0.0

    hours_covered = sum(1 for row in logs if (row["exposure_minutes"] or 0) > 0)

    return {
        "pm25": pm25_24h,
        "pm10": pm10_24h,
        "no2": no2_24h,
        "so2": so2_24h,
        "o3": o3_8hmax,
        "co": co_8hmax,
        # справочные (как и раньше)
        "o3_24h": o3_24h,
        "co_24h": co_24h,
        "hours_covered": int(hours_covered),
        "n_movements": 0,  # тут можно не считать, мы берём не movements
        "data_quality": "ok" if hours_covered >= 8 else "low",
    }
