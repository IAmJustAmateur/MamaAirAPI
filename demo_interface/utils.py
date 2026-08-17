import math
import random
from datetime import timedelta
from django.utils import timezone
from zoneinfo import ZoneInfo

from api.models import Movement
from api.services.movement_location import prepare_movement_location

# Границы Нигерии (грубая рамка — достаточно для правдоподобной генерации)
NIGERIA_BOUNDS = {
    "lat_min": 4.27,
    "lat_max": 13.89,
    "lon_min": 2.67,
    "lon_max": 14.68,
}

# Несколько крупных городов — чтобы старт был "правдоподобным"
NIGERIA_CITY_SEEDS = [
    (6.5244, 3.3792),  # Lagos
    (9.0765, 7.3986),  # Abuja
    (12.0022, 8.5920),  # Kano
    (4.8156, 7.0498),  # Port Harcourt
    (7.3775, 3.9470),  # Ibadan
    (10.5105, 7.4165),  # Kaduna
]


def _meters_to_deg(d_meters: float, lat_deg: float):
    """
    Перевод метров в дельту градусов, с учётом широты для долготы.
    """
    # ~ длина градуса широты/долготы в метрах
    meters_per_deg_lat = 111_320.0
    meters_per_deg_lon = 111_320.0 * math.cos(math.radians(lat_deg))
    if (
        meters_per_deg_lon < 1e-6
    ):  # защита от деления на ~0 вблизи полюсов (нам тут не страшно)
        meters_per_deg_lon = 1e-6
    return d_meters / meters_per_deg_lat, d_meters / meters_per_deg_lon


def _clamp_to_nigeria(lat: float, lon: float):
    lat_c = min(max(lat, NIGERIA_BOUNDS["lat_min"]), NIGERIA_BOUNDS["lat_max"])
    lon_c = min(max(lon, NIGERIA_BOUNDS["lon_min"]), NIGERIA_BOUNDS["lon_max"])
    return lat_c, lon_c


def _choose_start_point(seed_city_bias=True):
    """
    Выбираем стартовую точку.
    Если seed_city_bias=True — берём одну из "опорных" городских точек с небольшим шумом.
    Иначе — равномерно по рамке Нигерии.
    """
    if seed_city_bias:
        base_lat, base_lon = random.choice(NIGERIA_CITY_SEEDS)
        # Небольшой шум ~ до 500 м
        jitter_m = random.uniform(0, 500)
        bearing = random.uniform(0, 2 * math.pi)
        dlat_m, dlon_m = math.sin(bearing) * jitter_m, math.cos(bearing) * jitter_m
        dlat_deg, _ = _meters_to_deg(abs(dlat_m), base_lat)
        _, dlon_deg = _meters_to_deg(abs(dlon_m), base_lat)
        lat = base_lat + (dlat_deg if dlat_m >= 0 else -dlat_deg)
        lon = base_lon + (dlon_deg if dlon_m >= 0 else -dlon_deg)
        return _clamp_to_nigeria(lat, lon)
    else:
        lat = random.uniform(NIGERIA_BOUNDS["lat_min"], NIGERIA_BOUNDS["lat_max"])
        lon = random.uniform(NIGERIA_BOUNDS["lon_min"], NIGERIA_BOUNDS["lon_max"])
        return lat, lon


def generate_plausible_movements_24h(
    user,
    *,
    step_minutes: int = 10,
    max_step_meters: int = 1000,  # не дальше 1 км за 10 минут
    p_still_day: float = 0.65,  # днём вероятность "стоим"
    p_still_night: float = 0.95,  # ночью вероятность "стоим"
    lagos_tz: str = "Africa/Lagos",
    seed: int | None = None,
    clear_existing: bool = False,
):
    """
    Генерирует перемещения пользователя за последние 24 часа с шагом step_minutes.

    Правила:
    - пешком: не дальше max_step_meters за шаг (по умолчанию 1 км за 10 минут);
    - минимум ~75% стоим на месте (за счёт p_still_day=0.65, p_still_night=0.95);
    - ночью (22:00–06:00 Africa/Lagos) почти не двигаемся;
    - остаёмся в пределах Нигерии (рамка).

    Параметры:
      user            — объект пользователя
      step_minutes    — размер шага сетки (обычно 10 минут)
      max_step_meters — максимум смещения за шаг
      p_still_day     — вероятность "стоим" днём
      p_still_night   — вероятность "стоим" ночью
      lagos_tz        — временная зона для определения дня/ночи
      seed            — фиксировать генератор случайностей
      clear_existing  — удалить уже существующие Movement за этот интервал (24 часа)

    Возвращает:
      dict с количеством созданных точек и фактической долей статичных точек.
    """
    if seed is not None:
        random.seed(seed)

    now_utc = timezone.now()
    start_utc = now_utc - timedelta(hours=24)
    tz = ZoneInfo(lagos_tz)

    # при необходимости чистим существующие 24ч (аккуратно, по пользователю)
    if clear_existing:
        Movement.objects.filter(
            user=user, timestamp__gte=start_utc, timestamp__lte=now_utc
        ).delete()

    # сетка времени
    step = timedelta(minutes=step_minutes)
    times = []
    t = start_utc
    while t <= now_utc:
        times.append(t)
        t += step

    # стартовая точка (около города)
    lat, lon = _choose_start_point(seed_city_bias=True)

    # вероятностное распределение длины шага (когда "идём"):
    # берём треугольное: от 0 до max_step_meters, мода около 200 м — частые короткие пешие перемещения
    def _draw_step_length():
        return random.triangular(0, max_step_meters, 200)

    movements = []
    still_count = 0

    for ts_utc in times:
        # определяем вероятность "стоим" по локальному часу в Лагосе
        local = ts_utc.astimezone(tz)
        hour = local.hour
        is_night = hour >= 22 or hour < 6
        p_still = p_still_night if is_night else p_still_day

        if random.random() < p_still:
            # остаёмся на месте
            still_count += 1
        else:
            # делаем небольшой "пеший" шаг
            dist_m = _draw_step_length()
            bearing = random.uniform(0, 2 * math.pi)
            # разложим на север/восток и переведём в градусы
            north_m = math.sin(bearing) * dist_m
            east_m = math.cos(bearing) * dist_m
            dlat_deg, _ = _meters_to_deg(abs(north_m), lat)
            _, dlon_deg = _meters_to_deg(abs(east_m), lat)

            lat += dlat_deg if north_m >= 0 else -dlat_deg
            lon += dlon_deg if east_m >= 0 else -dlon_deg

            # держим точку в пределах Нигерии
            lat, lon = _clamp_to_nigeria(lat, lon)

        location = prepare_movement_location(lat, lon)
        movements.append(
            Movement(
                user=user,
                latitude=location.latitude,
                longitude=location.longitude,
                timestamp=ts_utc,
                h3_cell=location.h3_cell,
                coordinates_encrypted=location.coordinates_encrypted,
                coordinates_key_version=location.coordinates_key_version,
            )
        )

    Movement.objects.bulk_create(movements, batch_size=1000)

    return {
        "created": len(movements),
        "still_share": round(still_count / max(1, len(movements)), 3),
        "window": [start_utc, now_utc],
        "step_minutes": step_minutes,
    }
