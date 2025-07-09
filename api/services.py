# api/services/advice_selector.py

from .models import AdviceTemplate


def get_current_advices(user, pregnancy_week=None):
    """
    Stub: later will filter based on user profile, pregnancy week, air exposure, etc.
    """
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
