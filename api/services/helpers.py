import csv
from io import TextIOWrapper

from django.utils import timezone
from django.utils.dateparse import parse_datetime


def _parse_ts_to_aware(value: str) -> timezone.datetime:
    """
    Парсим timestamp в aware datetime (локальный TZ, если был naive).
    """
    dt = parse_datetime(value)
    if dt is None:
        dt = timezone.datetime.fromisoformat(value)
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_current_timezone())
    return dt


def parse_csv_to_records(file) -> tuple[list[dict], list[dict]]:
    """
    Читает CSV и возвращает:
      - список records вида {"lat", "lon", "ts", "indoor"}
      - список ошибок [{"row": N, "error": "..."}]
    Ожидаемые колонки: latitude, longitude, timestamp[, indoor]
    """
    decoded = TextIOWrapper(file, encoding="utf-8")
    reader = csv.DictReader(decoded)

    records = []
    errors = []

    for rowno, row in enumerate(reader, start=1):
        try:
            lat = float(row["latitude"])
            lon = float(row["longitude"])
            ts = _parse_ts_to_aware(row["timestamp"])

            indoor_raw = row.get("indoor", "").strip().lower()
            indoor = indoor_raw in ("true", "1", "yes", "y")

            records.append({"lat": lat, "lon": lon, "ts": ts, "indoor": indoor})
        except KeyError as e:
            errors.append({"row": rowno, "error": f"Missing column: {e.args[0]}"})
        except ValueError as e:
            errors.append({"row": rowno, "error": f"Bad value: {e}"})
        except Exception as e:
            errors.append({"row": rowno, "error": str(e)})

    return records, errors


def parse_json_to_records(payload) -> tuple[list[dict], list[dict]]:
    """
    Читает JSON payload вида {"movements": [...]} и возвращает:
      - список records вида {"lat", "lon", "ts", "indoor"}
      - список ошибок [{"row": N, "error": "..."}]
    Ожидаемые поля элемента: latitude, longitude, timestamp[, indoor]
    """
    if not isinstance(payload, dict):
        return [], [{"error": "Invalid JSON object."}]

    movements = payload.get("movements")
    if movements is None:
        return [], [{"error": "Missing 'movements' field."}]
    if not isinstance(movements, list):
        return [], [{"error": "'movements' must be a list."}]

    records = []
    errors = []

    for rowno, row in enumerate(movements, start=1):
        try:
            if not isinstance(row, dict):
                raise ValueError("Movement item must be an object")

            lat = float(row["latitude"])
            lon = float(row["longitude"])
            ts = _parse_ts_to_aware(row["timestamp"])

            indoor_raw = str(row.get("indoor", "")).strip().lower()
            indoor = indoor_raw in ("true", "1", "yes", "y")

            records.append({"lat": lat, "lon": lon, "ts": ts, "indoor": indoor})
        except KeyError as e:
            errors.append({"row": rowno, "error": f"Missing field: {e.args[0]}"})
        except ValueError as e:
            errors.append({"row": rowno, "error": f"Bad value: {e}"})
        except Exception as e:
            errors.append({"row": rowno, "error": str(e)})

    return records, errors
