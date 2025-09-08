# api/services/advice_selector.py
from datetime import timedelta, datetime
import requests
import pandas as pd
import os
from django.conf import settings

OWM_BASE_URL = "http://api.openweathermap.org/data/2.5/air_pollution/history"

OWM_API_KEY = settings.OWM_API_KEY


def round_coord(val: float) -> float:
    return round(val, 2)  # ~1 км


def fetch_air_quality_data_interval(
    lat: float, lon: float, timestamps: pd.Series
) -> dict:
    """
    Тянем OWM историю по часовым меткам [start..end].
    Возвращаем dict: { datetime -> components_dict }
    """
    start_time = pd.to_datetime(timestamps.min()).to_pydatetime()
    end_time = pd.to_datetime(timestamps.max()).to_pydatetime()
    if end_time - start_time < timedelta(hours=1):
        start_time = end_time - timedelta(hours=1)

    start_ts = int(start_time.timestamp())
    end_ts = int(end_time.timestamp())

    url = f"{OWM_BASE_URL}?lat={lat}&lon={lon}&start={start_ts}&end={end_ts}&appid={OWM_API_KEY}"
    resp = requests.get(url)
    if resp.status_code != 200:
        raise RuntimeError(f"OWM error {resp.status_code}: {resp.text}")

    items = resp.json().get("list", [])
    return {datetime.fromtimestamp(it["dt"]): it["components"] for it in items}


def get_current_advices(user, pregnancy_week=None):
    """
    Stub: later will filter based on user profile, pregnancy week, air exposure, etc.
    """
    from api.models import AdviceTemplate

    return AdviceTemplate.objects.filter(is_active=True)


def get_air_quality_summary(user):
    return {
        "pm25": {"value": 12.5, "who_limit": 15},
        "pm10": {"value": 24.3, "who_limit": 10},
        "no2": {"value": 12.5, "who_limit": 15},
        "so2": {"value": 12.5, "who_limit": 15},
        "o3": {"value": 12.5, "who_limit": 15},
        "co": {"value": 12.5, "who_limit": 15},
        "aqi": 53,
    }


def get_weather_summary(user):
    return {
        "temperature": 23,
        "humidity": 65,
        "pressure": 1012,
        "wind_speed": 3.4,
        "condition": "Partly Cloudy",
    }


def get_uv_index(user):
    return {"value": 5, "level": "moderate"}


def get_exposure_summary(user, target="mom"):
    return {
        "total_score": "moderate",
        "last_updated": "2025-06-26T12:34:56Z",
        "exposure_levels": [
            {"date": "2025-06-20", "level": 1},
            {"date": "2025-06-21", "level": 2},
        ],
    }


def get_risks_delta(user):
    return {"mom": -0.15, "baby": 1.3}


def get_current_recommendations(user):
    return {
        "mom": ["Avoid charcoal cooking.", "Drink more water."],
        "baby": ["some recommendation 1", "some recommendation 2"],
    }


def get_today_journey(user):
    return {"length": 25.5, "time": 4.6}
