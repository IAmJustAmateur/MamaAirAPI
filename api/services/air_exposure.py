# services/air_exposure.py
from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Dict, Iterable, List, Tuple

from collections import defaultdict
from django.apps import apps
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

# Модели через apps.get_model, чтобы не ловить циклические импорты
Movement = apps.get_model("api", "Movement")
AirExposureLog = apps.get_model("api", "AirExposureLog")


# =========================
# ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ
# =========================


def bucket_start(dt: timezone.datetime) -> timezone.datetime:
    """Начало часового бакета (локальный TZ)."""
    tz = timezone.get_current_timezone()
    dt = dt.astimezone(tz)
    return dt.replace(minute=0, second=0, microsecond=0, tzinfo=tz)


def grid_id(lat: float, lon: float, precision: int = 2) -> str:
    """
    Простейшая «сетка»: округление координат (можно заменить на H3).
    precision=2 ~ ~1.1 км по широте.
    """
    return f"{round(lat, precision):.2f}_{round(lon, precision):.2f}"


def estimate_minutes_covered(timestamps: List[timezone.datetime]) -> int:
    """
    Эвристика покрытия минут внутри часа по набору точек.
    Если точки редкие/нерегулярные — используем span, каппим в 60.
    """
    if not timestamps:
        return 0
    ts = sorted(timestamps)
    span_min = (ts[-1] - ts[0]).total_seconds() / 60.0
    approx = min(60, max(1, int(round(span_min + 2))))  # небольшой буфер по краям
    return approx


def weighted_update(
    old_val: float | None, old_min: int, new_val: float | None, new_min: int
) -> Tuple[float | None, int]:
    """
    Минутно-взвешенное объединение значений.
    Возвращает (новое значение, новое покрытие), покрытие каппим 60.
    """
    new_min = max(0, min(60, new_min))
    old_min = max(0, min(60, old_min))

    if new_val is None:
        return (old_val, old_min)
    if old_val is None or old_min <= 0:
        return (new_val, new_min)

    # Если уже есть покрытие, добавляем ещё минут, но не больше 60.
    # При капе — нормализуем веса пропорционально доступным минутам.
    add_min = min(new_min, max(0, 60 - old_min))
    total_min = old_min + add_min
    if total_min <= 0:
        return (old_val, old_min)

    val = (old_val * old_min + new_val * add_min) / total_min
    return (val, total_min)


# =========================
# ПРОВАЙДЕР AQ (ЗАГЛУШКА)
# =========================


@dataclass
class AQSample:
    timestamp: timezone.datetime  # метка провайдера (обычно начало часа)
    aqi: int | None
    pm25: float | None  # единицы: µg/m³
    pm10: float | None
    no2: float | None
    so2: float | None
    co: float | None
    o3: float | None
    temperature: float | None
    humidity: float | None
    wind_speed: float | None
    provider: str = "provider"
    data_quality: str = "ok"  # ok|gap|interpolated


def fetch_aq_for_bucket(lat: float, lon: float, bucket: timezone.datetime) -> AQSample:
    """
    Подтягиваем AQ для координаты/часа с кэшем.
    ЗАМЕНИ на реальную интеграцию (OWM/Google AQ). Верни µg/m³.
    """
    key = f"aq:{round(lat,2)}:{round(lon,2)}:{bucket.isoformat()}"
    cached = cache.get(key)
    if cached:
        return cached

    # TODO: интеграция с твоим провайдером
    sample = AQSample(
        timestamp=bucket,
        aqi=75,
        pm25=18.0,
        pm10=30.0,
        no2=22.0,
        so2=3.0,
        co=150.0,
        o3=60.0,
        temperature=18.5,
        humidity=55.0,
        wind_speed=3.2,
        provider="OWM",
        data_quality="ok",
    )
    cache.set(key, sample, timeout=60 * 60)  # кэш на 1 час
    return sample


# =========================
# UPSERT AIR EXPOSURE LOG
# =========================


@transaction.atomic
def upsert_air_exposure_log(
    user_id: int,
    bucket: timezone.datetime,
    lat: float,
    lon: float,
    indoor: bool,
    aq: AQSample,
    minutes_covered: int,
):
    """
    Upsert `AirExposureLog` по ключу (user, bucket, lat/lon (rounded), indoor).
    Числа усредняются минутно-взвешенно, покрытие каппится до 60.
    """
    # Чтобы избежать дрожания координат — храним округлённые
    lat_ = round(lat, 5)
    lon_ = round(lon, 5)

    obj, created = AirExposureLog.objects.get_or_create(
        user_id=user_id,
        timestamp=bucket,  # используем начало бакета как "время данных"
        latitude=lat_,
        longitude=lon_,
        indoor=indoor,
        defaults={
            "aqi": aq.aqi,
            "pm25": aq.pm25,
            "pm10": aq.pm10,
            "no2": aq.no2,
            "so2": aq.so2,
            "co": aq.co,
            "o3": aq.o3,
            "temperature": aq.temperature,
            "humidity": aq.humidity,
            "wind_speed": aq.wind_speed,
            "exposure_minutes": min(60, int(minutes_covered)),
        },
    )

    if created:
        return True, obj

    old_min = int(obj.exposure_minutes or 0)
    new_min = int(minutes_covered or 0)

    obj.pm25, obj.exposure_minutes = weighted_update(
        obj.pm25, old_min, aq.pm25, new_min
    )
    obj.pm10, _ = weighted_update(obj.pm10, old_min, aq.pm10, new_min)
    obj.no2, _ = weighted_update(obj.no2, old_min, aq.no2, new_min)
    obj.so2, _ = weighted_update(obj.so2, old_min, aq.so2, new_min)
    obj.co, _ = weighted_update(obj.co, old_min, aq.co, new_min)
    obj.o3, _ = weighted_update(obj.o3, old_min, aq.o3, new_min)

    # Метаданные обновляем свежими значениями, если они есть
    if aq.aqi is not None:
        obj.aqi = aq.aqi
    if aq.temperature is not None:
        obj.temperature = aq.temperature
    if aq.humidity is not None:
        obj.humidity = aq.humidity
    if aq.wind_speed is not None:
        obj.wind_speed = aq.wind_speed

    obj.save(
        update_fields=[
            "pm25",
            "pm10",
            "no2",
            "so2",
            "co",
            "o3",
            "aqi",
            "temperature",
            "humidity",
            "wind_speed",
            "exposure_minutes",
        ]
    )
    return False, obj


# =========================
# ПУБЛИЧНЫЙ ВХОД ДЛЯ VIEW
# =========================


def ingest_movements_batch(
    user_id: int,
    records: List[dict],
    *,
    default_indoor: bool = False,
    grid_precision: int = 2,
) -> dict:
    """
    Ингест батча движений без циклических импортов.
    records: [{lat, lon, ts, indoor?}, ...]
    Возвращает сводку: сколько movements сохранено, сколько AirExposureLog создано/обновлено.
    """
    if not records:
        return {"imported": 0, "air_exposure_created": 0, "air_exposure_updated": 0}

    # 1) Подготовка Movement-объектов (без лишних импортов)
    mv_objs = []
    for r in records:
        lat = float(r["lat"])
        lon = float(r["lon"])
        ts = r["ts"]
        if timezone.is_naive(ts):
            ts = timezone.make_aware(ts, timezone.get_current_timezone())
        mv_objs.append(
            Movement(user_id=user_id, latitude=lat, longitude=lon, timestamp=ts)
        )

    # 2) Сохранение movements батчем
    with transaction.atomic():
        Movement.objects.bulk_create(mv_objs, ignore_conflicts=True)

    # 3) Группировка по часовому бакету и «гридy»
    groups: Dict[Tuple[timezone.datetime, str, bool], List[timezone.datetime]] = (
        defaultdict(list)
    )
    grid_to_latlon: Dict[str, Tuple[float, float]] = {}

    for mv in mv_objs:
        b = bucket_start(mv.timestamp)
        g = grid_id(mv.latitude, mv.longitude, precision=grid_precision)
        indoor = (
            bool(records[0].get("indoor", default_indoor))
            if "indoor" in mv.__dict__
            else default_indoor
        )  # на старте можно общим флагом
        groups[(b, g, indoor)].append(mv.timestamp)
        if g not in grid_to_latlon:
            grid_to_latlon[g] = (mv.latitude, mv.longitude)

    # 4) Upsert AirExposureLog по группам
    created_logs = 0
    updated_logs = 0

    for (bkt, gid, indoor), ts_list in groups.items():
        minutes = estimate_minutes_covered(ts_list)
        lat, lon = grid_to_latlon[gid]
        aq = fetch_aq_for_bucket(lat, lon, bkt)
        created, _ = upsert_air_exposure_log(
            user_id=user_id,
            bucket=bkt,
            lat=lat,
            lon=lon,
            indoor=indoor,
            aq=aq,
            minutes_covered=minutes,
        )
        if created:
            created_logs += 1
        else:
            updated_logs += 1

    return {
        "imported": len(mv_objs),
        "air_exposure_created": created_logs,
        "air_exposure_updated": updated_logs,
    }
