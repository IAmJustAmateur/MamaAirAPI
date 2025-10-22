# api/services/guidelines.py
from __future__ import annotations
from typing import Any, Dict, Optional, Tuple

from django.utils import timezone

from api.models import GuidelineLimit

# Предполагаемые единицы исходных данных:
#   - Логи (AirExposureLog): все в µg/m³, КРОМЕ CO — там обычно тоже µg/m³ (many APIs).
#   - Exposure.pollutants: считаем, что в µg/m³ (если у тебя иначе — поправь тут).
LOG_UNITS = {
    "pm25": "µg/m³",
    "pm10": "µg/m³",
    "no2": "µg/m³",
    "o3": "µg/m³",
    "so2": "µg/m³",
    "co": "µg/m³",  # часто µg/m³; лимит WHO — в mg/m³ → конвертируем
}
EXPOSURE_UNITS = LOG_UNITS.copy()


def get_label(pollutant: str) -> str:
    return {
        "pm25": "PM2.5",
        "pm10": "PM10",
        "no2": "NO₂",
        "o3": "O₃",
        "so2": "SO₂",
        "co": "CO",
    }.get(pollutant, pollutant)


def _convert(value: Optional[float], from_unit: str, to_unit: str) -> Optional[float]:
    if value is None or from_unit == to_unit:
        return value
    if from_unit == "µg/m³" and to_unit == "mg/m³":
        return value / 1000.0
    if from_unit == "mg/m³" and to_unit == "µg/m³":
        return value * 1000.0
    # иные конверсии не поддержаны — возвращаем как есть
    return value


def _extract_exposure_pollutant(exposure, pollutant: str) -> Optional[float]:
    """
    Достаём суточный агрегат поллютанта из Exposure.pollutants.
    Поддерживаем форматы:
      - {"pm25": 12.3}
      - {"pm25": {"daily_mean": 12.3}}
      - {"pm25": {"mean": 12.3}}
      - {"pm25": {"value": 12.3}}
    Возвращаем None, если нет данных.
    """
    if not exposure:
        return None
    data = getattr(exposure, "pollutants", None) or {}
    val = data.get(pollutant)
    if isinstance(val, (int, float)):
        return float(val)
    if isinstance(val, dict):
        for key in ("daily_mean", "mean", "value"):
            if key in val and isinstance(val[key], (int, float)):
                return float(val[key])
    return None


def compute_pollutant_compliance(user, latest_log, exposure_today) -> Dict[str, Any]:
    """
    Возвращает структуру:
    {
      "source": "WHO",
      "version": "AQG 2021",
      "per_pollutant": {
        "pm25": {
          "value": 11.7,
          "unit": "µg/m³",
          "avg_period_used": "24h",            # "24h" | "8h" | "instant-approx" | "24h-approx"
          "value_source": "exposure",           # "exposure" | "log" | "none"
          "value_datetime": "2025-10-16",       # ISO (date для exposure) или ISO datetime для log
          "limit": 15.0,
          "limit_unit": "µg/m³",
          "limit_avg_period": "24h",
          "compliance": true,
          "exceedance_pct": null,
          "approximate": false
        },
        ...
      }
    }
    """
    active = GuidelineLimit.objects.filter(is_active=True).order_by(
        "pollutant", "avg_period", "-updated_at", "-id"
    )

    # Берём первый по каждой паре (pollutant, avg_period)
    chosen: Dict[Tuple[str, str], GuidelineLimit] = {}
    for gl in active:
        key = (gl.pollutant, gl.avg_period)
        if key not in chosen:
            chosen[key] = gl

    # Для простоты берём по одному лимиту на поллютант (приоритет: 24h > 8h > 1h)
    priority = {"24h": 0, "8h": 1, "1h": 2, "annual": 3}
    pick: Dict[str, GuidelineLimit] = {}
    for (pol, avg), gl in chosen.items():
        prev = pick.get(pol)
        if prev is None or priority.get(gl.avg_period, 99) < priority.get(
            prev.avg_period, 99
        ):
            pick[pol] = gl

    per_pollutant: Dict[str, Any] = {}

    for pol, gl in pick.items():
        # 1) пытаемся взять суточный агрегат из Exposure
        exp_val_raw = _extract_exposure_pollutant(exposure_today, pol)
        exp_unit = EXPOSURE_UNITS.get(pol, "µg/m³")

        # 2) иначе — моментное значение из лога
        log_val_raw = getattr(latest_log, pol, None) if latest_log is not None else None
        log_unit = LOG_UNITS.get(pol, "µg/m³")

        # Выбор источника значения
        if exp_val_raw is not None:
            value_raw = exp_val_raw
            from_unit = exp_unit
            value_source = "exposure"
            # Если лимит на 24h — используем как есть; если 8h/1h — помечаем approximate
            if gl.avg_period == "24h":
                avg_used = "24h"
                approximate = False
            else:
                avg_used = "24h-approx"
                approximate = True
            value_dt = getattr(exposure_today, "timestamp", timezone.localdate())
        elif log_val_raw is not None:
            value_raw = log_val_raw
            from_unit = log_unit
            value_source = "log"
            avg_used = "instant-approx"
            approximate = True
            value_dt = getattr(latest_log, "timestamp", None)
        else:
            value_raw = None
            from_unit = gl.unit
            value_source = "none"
            avg_used = gl.avg_period
            approximate = False
            value_dt = None

        # Конвертация в единицы лимита
        value = (
            _convert(value_raw, from_unit, gl.unit) if value_raw is not None else None
        )

        # Сравнение
        if value is None:
            compliance = None
            exceedance_pct = None
        else:
            compliance = value <= gl.value
            exceedance_pct = None
            if not compliance and gl.value > 0:
                exceedance_pct = ((value - gl.value) / gl.value) * 100.0

        per_pollutant[pol] = {
            "value": value,
            "label": get_label(pol),
            "unit": (
                gl.unit if value is not None else gl.unit
            ),  # единица результата — как у лимита
            "avg_period_used": avg_used,
            "value_source": value_source,
            "value_datetime": (value_dt.isoformat() if value_dt is not None else None),
            "limit": gl.value,
            "limit_unit": gl.unit,
            "limit_avg_period": gl.avg_period,
            "compliance": compliance,
            "exceedance_pct": exceedance_pct,
            "approximate": approximate,
        }

    # Берём метаданные из любого активного лимита (или дефолт)
    meta_source = "WHO"
    meta_version = "AQG 2021"
    any_gl = next(iter(pick.values()), None)
    if any_gl:
        meta_source = any_gl.source
        meta_version = any_gl.version

    return {
        "source": meta_source,
        "version": meta_version,
        "per_pollutant": per_pollutant,
    }
