from zoneinfo import ZoneInfo
import random
from datetime import datetime, timedelta, timezone as dt_timezone


def build_csv_many_points(
    lat=52.2297,
    lon=21.0122,  # Warsaw по умолчанию
    tz_name="Europe/Warsaw",
    points=24,
    step_minutes=5,
    hours_back_start=2,
) -> tuple[str, bytes, str]:
    """
    Генерирует CSV c N-точками, равномерно распределёнными каждые step_minutes,
    в пределах одного-двух последних часов (по локальному TZ).
    Возвращает (filename, bytes, target_date_iso).
    """
    tz = ZoneInfo(tz_name)
    now_local = datetime.now(dt_timezone.utc).astimezone(tz)
    # начнём с полной «целой» метки, N часов назад
    start = now_local.replace(minute=0, second=0, microsecond=0) - timedelta(
        hours=hours_back_start
    )
    rows = ["latitude,longitude,timestamp"]
    for i in range(points):
        ts = (start + timedelta(minutes=i * step_minutes)).isoformat(timespec="seconds")
        # небольшой джиттер координат, чтобы не все были идентичны
        jitter_lat = lat + (random.random() - 0.5) * 0.001
        jitter_lon = lon + (random.random() - 0.5) * 0.001
        rows.append(f"{jitter_lat:.6f},{jitter_lon:.6f},{ts}")
    csv_text = "\n".join(rows) + "\n"
    return "movements_many.csv", csv_text.encode("utf-8"), start.date().isoformat()
