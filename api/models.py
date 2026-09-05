# api/models.py

import uuid

from django.db import models, transaction

from datetime import date, timedelta

from django.utils.translation import gettext_lazy as _, get_language
from django.utils import timezone
from django.utils.text import slugify

from logging import getLogger

import pandas as pd


from django.contrib.auth.models import (
    BaseUserManager,
    AbstractBaseUser,
    PermissionsMixin,
)

from api.services.aq_inputs import get_air_quality_inputs_for_risks_from_logs
from api.services.services import round_coord, fetch_air_quality_data_interval
from api.services.aggregation import agg_max_plus_logistic_tail

from django.conf import settings

logger = getLogger(__name__)


def user_avatar_upload_to(instance, filename):
    suffix = filename.rsplit(".", 1)[-1].lower() if "." in filename else "jpg"
    return f"avatars/user_{instance.pk}/{uuid.uuid4().hex}.{suffix}"


USER_RISK_FACTORS = [
    "bmi",
    "full_year",
    "race",
]

SYMPTOM_CLASS_ACUTE = 1
SYMPTOM_CLASS_SYSTEMIC = 2
SYMPTOM_CLASS_FETAL = 3
SYMPTOM_CLASS_LIFESTYLE = 4

SYMPTOM_CLASS_CHOICES = [
    (SYMPTOM_CLASS_ACUTE, _("Acute & Emergency Indicators")),
    (SYMPTOM_CLASS_SYSTEMIC, _("Condition-Specific Systemic Indicators")),
    (SYMPTOM_CLASS_FETAL, _("Fetal Activity & Growth Markers")),
    (SYMPTOM_CLASS_LIFESTYLE, _("Lifestyle & Environmental Stressors")),
]

SYMPTOM_CHECKLIST_MOMMY = "mommy"
SYMPTOM_CHECKLIST_BABY = "baby"
SYMPTOM_CHECKLIST_TYPE_CHOICES = [
    (SYMPTOM_CHECKLIST_MOMMY, _("Mommy")),
    (SYMPTOM_CHECKLIST_BABY, _("Baby")),
]

SYMPTOM_STATUS_REPORTED = "reported"
SYMPTOM_STATUS_NOT_REPORTED = "not_reported"
SYMPTOM_STATUS_NOT_ANSWERED = "not_answered"
SYMPTOM_STATUS_CHOICES = [
    (SYMPTOM_STATUS_REPORTED, _("Reported by user")),
    (SYMPTOM_STATUS_NOT_REPORTED, _("Not reported by user")),
    (SYMPTOM_STATUS_NOT_ANSWERED, _("Not answered")),
]

SYMPTOM_CLASS_METADATA = {
    SYMPTOM_CLASS_ACUTE: {
        "name": "Acute & Emergency Indicators",
        "color_flag": "critical_red",
    },
    SYMPTOM_CLASS_SYSTEMIC: {
        "name": "Condition-Specific Systemic Indicators",
        "color_flag": "gray",
    },
    SYMPTOM_CLASS_FETAL: {
        "name": "Fetal Activity & Growth Markers",
        "color_flag": "mamaair_orange",
    },
    SYMPTOM_CLASS_LIFESTYLE: {
        "name": "Lifestyle & Environmental Stressors",
        "color_flag": "blue",
    },
}


# def _calculate_risks(risks, fields, object, RiskModel):
#     """
#     Calculate risk factors based on given object and risk factors.

#     Args:
#         risks (list of RiskDefinition): Risk definitions to calculate.
#         fields (list of str): Fields of object that are used in risk factor conditions.
#         object (Any): Object to calculate risk factors for.
#         RiskModel (type): Type of RiskModel to use when calculating risk factors.

#     Returns:
#         dict: Dictionary with risk names as keys and calculated risk factors as values.
#     """
#     risks_dictionary = {}
#     for risk in risks:
#         base_risk = 1.0  # Base risk factor
#         risk_factors = RiskModel.objects.filter(risk=risk)

#         for risk_factor in risk_factors:
#             for factor in fields:
#                 if factor in risk_factor.condition:
#                     if hasattr(object, factor):
#                         value = getattr(object, factor)
#                         if value:
#                             condition = risk_factor.condition.replace(
#                                 factor, str(value)
#                             )
#                             logger.info(
#                                 f"Condition: {condition}, factor: {factor}, value: {value}"
#                             )
#                             try:
#                                 if eval(condition):
#                                     multiplier = risk_factor.get_multiplier(str(value))
#                                     base_risk *= multiplier
#                             except:
#                                 pass
#         risks_dictionary[risk.name] = base_risk
#     return risks_dictionary


class MyUser(AbstractBaseUser):
    USERNAME_FIELD = "email"
    email = models.EmailField(
        "email", unique=True
    )  # changes email to unique and blank to false
    REQUIRED_FIELDS = []  # removes email from REQUIRED_FIELDS
    username = None


class CustomUserManager(BaseUserManager):
    def create_user(self, email, password=None, **extra_fields):
        if not email:
            raise ValueError("The Email must be set")
        email = self.normalize_email(email)
        user = self.model(email=email, **extra_fields)
        user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)


EXPOSURE_LEVEL_CHOICES = [
    ("Clean", _("Clean")),
    ("Very Good", _("Very Good")),
    ("Moderate", _("Moderate")),
    ("Acceptable", _("Acceptable")),
    ("Unhealthy", _("Unhealthy")),
    ("High", _("High")),
    ("Hazardous", _("Hazardous")),
    ("Extreme", _("Extreme")),
]

LANGUAGE_CHOICES = [
    ("en", "English"),
    ("fr", "French"),
    ("sw", "Swahili"),
    ("pl", "Polish"),
]
COUNTRY_REGION_MAP = {
    "KE": "East Africa",
    "GH": "West Africa",
    "NG": "West Africa",
    "PL": "Europe",
    "other": "other",
}


class User(MyUser, PermissionsMixin):

    objects = CustomUserManager()

    RACE_CHOICES = [
        ("caucasian", _("Caucasian")),
        ("african", _("African")),
        ("asian", _("Asian")),
        ("hispanic", _("Hispanic")),
        ("mixed", _("Mixed")),
    ]

    COUNTRY_CHOICES = [
        ("NG", "Nigeria"),
        ("GH", "Ghana"),
        ("KE", "Kenya"),
        ("other", "Other"),
    ]

    SHARE_CHANNELS = [
        ("email", _("Email")),
        ("whatsapp", _("WhatsApp")),
        ("telegram", _("Telegram")),
    ]

    is_active = models.BooleanField(default=True)
    is_staff = models.BooleanField(default=False)

    name = models.CharField(max_length=255, null=True, blank=True)
    registered_at = models.DateTimeField(auto_now_add=True)

    language = models.CharField(max_length=10, choices=LANGUAGE_CHOICES, default="en")

    # demographic data
    date_of_birth = models.DateField(null=True, blank=True)
    height = models.FloatField(null=True, blank=True)
    weight_pre_pregnancy = models.FloatField(null=True, blank=True)

    race = models.CharField(max_length=255, null=True, blank=True, choices=RACE_CHOICES)
    country = models.CharField(
        max_length=255, null=True, blank=True, choices=COUNTRY_CHOICES
    )
    is_first_pregnancy = models.BooleanField(null=True, blank=True)
    pregnancy_number = models.PositiveIntegerField(null=True, blank=True)
    week_of_pregnancy = models.IntegerField(null=True, blank=True)

    pregnancy_start_date = models.DateField(null=True, blank=True)

    tracking_enabled = models.BooleanField(default=False)
    notifications_enabled = models.BooleanField(default=False)
    notification_window_from = models.TimeField(null=True, blank=True)
    notification_window_to = models.TimeField(null=True, blank=True)
    timezone = models.CharField(max_length=64, null=True, blank=True)

    auth_provider = models.CharField(max_length=20, default="password")
    google_sub = models.CharField(max_length=255, null=True, blank=True, unique=True)
    avatar = models.ImageField(upload_to=user_avatar_upload_to, null=True, blank=True)
    avatar_url = models.URLField(null=True, blank=True)
    consent = models.BooleanField(default=False)
    consent_accepted_at = models.DateTimeField(null=True, blank=True)
    preferred_share_channel = models.CharField(
        max_length=255, null=True, blank=True, choices=SHARE_CHANNELS
    )

    def sync_is_first_pregnancy(self):
        if self.pregnancy_number is None:
            return
        self.is_first_pregnancy = self.pregnancy_number == 1

    def save(self, *args, **kwargs):
        self.sync_is_first_pregnancy()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "pregnancy_number" in update_fields:
            kwargs["update_fields"] = set(update_fields) | {"is_first_pregnancy"}
        super().save(*args, **kwargs)

    def set_pregnancy_start_date(self):
        weeks = self.week_of_pregnancy
        if not weeks:
            return
        self.pregnancy_start_date = date.today() - timedelta(weeks=weeks)
        self.save()

    def __str__(self):
        if self.name:
            return f"{self.name} ({self.email})"
        else:
            return f"{self.email}"

    @property
    def bmi(self):
        if not self.height or not self.weight_pre_pregnancy:
            return None
        return self.weight_pre_pregnancy / ((self.height / 100) ** 2)

    @property
    def current_week_of_pregnancy(self) -> int | None:
        """
        Текущая неделя беременности = неделя на момент регистрации + полные недели с регистрации.
        Возвращает None, если исходные данные неполные.
        """
        if self.week_of_pregnancy is None or not self.registered_at:
            return None

        if not self.pregnancy_start_date:
            self.set_pregnancy_start_date()

        if not self.pregnancy_start_date:
            return None

        # Дата «якоря» — день регистрации (когда фиксировалась week_of_pregnancy)

        today = timezone.localdate()

        delta_weeks = max(0, (today - self.pregnancy_start_date).days // 7)
        current = delta_weeks

        # Часто практично ограничивать 42, но если не хотите — уберите min(...)
        return min(current, 42)

    # @property
    # def pregnancy_start_date(self):
    #     """
    #     Дата начала беременности (ориентировочно LMP): дата регистрации минус
    #     зафиксированная на тот момент неделя беременности.
    #     Вернёт None, если данных недостаточно.
    #     """
    #     if self.week_of_pregnancy is None or not self.registered_at:
    #         return None

    #     anchor_date = self.registered_at.astimezone(
    #         timezone.get_current_timezone()
    #     ).date()

    #     try:
    #         weeks = int(self.week_of_pregnancy)
    #     except (TypeError, ValueError):
    #         return None

    #     return anchor_date - timedelta(weeks=weeks)

    @property
    def full_year(self):
        return (
            date.today().year - self.date_of_birth.year if self.date_of_birth else None
        )

    @property
    def MVPA(self):
        pass

    RISK_FIELDS = [
        "bmi",
        "full_year",
        "race",
    ]

    @property
    def region(self):
        return COUNTRY_REGION_MAP.get(self.country, "other")

    def calculate_risk_factors(self):
        lifestyle_risks, ls_integrated_risk = (
            self.calculate_risk_factor_based_on_lifestyle()
        )
        profile_risks, profile_integrated_risk = (
            self.calculate_risk_factor_based_on_user_profile()
        )
        aq_risks, aq_integrated_risk = self.calculate_risk_factor_based_on_aq()
        Exposure.set_for_date(
            user=self,  # или конкретный user
            level=aq_integrated_risk,
            risks=aq_risks,
            # pollutants можно передать, если уже есть; иначе пустой dict
        )
        risks = RiskDefinition.objects.filter(is_enabled=True)
        risk_dictionary = {}
        for risk in risks:

            lifestyle_risk_score = (
                lifestyle_risks[risk.name] if risk.name in lifestyle_risks else 1.0
            )
            profile_risks_score = (
                profile_risks[risk.name] if risk.name in profile_risks else 1.0
            )
            aq_risks_score = aq_risks[risk.name] if risk.name in aq_risks else 1.0

            risk_score = lifestyle_risk_score * profile_risks_score * aq_risks_score

            risk_dictionary[risk.name] = {
                "risk_value": risk_score,
                "priority": risk.priority,
            }

        risk_values = {}
        for risk in risk_dictionary:
            risk_values[risk] = risk_dictionary[risk]["risk_value"]
        integrated_risk = agg_max_plus_logistic_tail(
            risk_values, mid=4.0, sensitivity=0.7
        )

        return risk_dictionary, integrated_risk

    def calculate_risk_factor_based_on_user_profile(self):
        from api.services.user_risks import compute_risks

        risks = RiskDefinition.objects.filter(is_enabled=True)

        risks_dict = compute_risks(
            obj=self,  # fields will be taken from User.RISK_FIELDS or get_risk_fields()
            RiskModel=UserRiskFactor,
            risks_qs=risks,
        )
        integrated_score = agg_max_plus_logistic_tail(
            risks_dict, mid=4.0, sensitivity=0.7
        )
        return risks_dict, integrated_score

    def calculate_risk_factor_based_on_lifestyle(self):
        from api.services.user_risks import compute_risks

        lifestyle = UserLifeStyle.objects.get(user=self.id)
        risks = RiskDefinition.objects.filter(is_enabled=True)

        risks_dict = compute_risks(
            obj=lifestyle,  # fields from UserLifeStyle.RISK_FIELDS or get_risk_fields()
            RiskModel=LifestyleRiskFactor,
            risks_qs=risks,
        )
        integrated_score = agg_max_plus_logistic_tail(
            risks_dict, mid=4.0, sensitivity=0.7
        )
        return risks_dict, integrated_score

    def calculate_risk_factor_based_on_aq(self, aq_data=None):
        from api.services.user_risks import compute_risks

        if aq_data is None:
            aq_data = get_air_quality_inputs_for_risks_from_logs(
                user_id=self.user.id,
                hours=24,
            )
        risks = RiskDefinition.objects.filter(is_enabled=True)

        risks_dict = compute_risks(
            obj=aq_data,  # dict → fields = aq_data.keys()
            RiskModel=AQRiskFactor,
            risks_qs=risks,
        )
        integrated_score = agg_max_plus_logistic_tail(
            risks_dict, mid=4.0, sensitivity=0.7
        )
        return risks_dict, integrated_score

    def get_mommy_symptoms_for_checking(self):
        """Backward-compatible wrapper around the symptom monitoring service."""
        from recommendations.services.symptom_monitoring import generate_symptoms

        return [
            symptom.name
            for symptom in generate_symptoms(self, SYMPTOM_CHECKLIST_MOMMY)
        ]

    def get_baby_symptoms_for_checking(self):
        """Backward-compatible wrapper around the symptom monitoring service."""
        from recommendations.services.symptom_monitoring import generate_symptoms

        return [
            symptom.name
            for symptom in generate_symptoms(self, SYMPTOM_CHECKLIST_BABY)
        ]

    def get_user_movements_df(
        self, start=None, end=None, hours: int = 24
    ) -> pd.DataFrame:
        """
        Возвращает DataFrame с колонками: latitude, longitude, timestamp
        за указанный период. По умолчанию — последние `hours` часов (24).
        """
        end = end or timezone.now()
        if start is None:
            start = end - timedelta(hours=hours)

        qs = (
            Movement.objects.filter(user=self, timestamp__gte=start, timestamp__lte=end)
            .order_by("timestamp")
            .values("latitude", "longitude", "timestamp")
        )

        df = pd.DataFrame.from_records(qs)
        if df.empty:
            return df

        # делаем наивные (без таймзоны) UTC-метки — удобно для .timestamp()
        ts = pd.to_datetime(df["timestamp"], utc=True)
        df["timestamp"] = ts.dt.tz_localize(None)
        return df

    def get_air_quality_inputs_for_risks(
        self, start=None, end=None, hours: int = 24
    ) -> dict:
        """
        Возвращает входы для risk-движка за окно (по умолчанию 24 ч):
          - pm25, no2, so2 — 24h средние (mg/m³)
          - o3, co         — 8h-max за сутки (mg/m³)
        Плюс справочные поля: o3_24h, co_24h, покрытие и качество данных.
        """
        df = self.get_user_movements_df(start=start, end=end, hours=hours)
        if df.empty:
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

        # 1) кластеры по координатам и подтяжка OWM
        df = df.copy()
        df["lat_r"] = df["latitude"].apply(round_coord)
        df["lon_r"] = df["longitude"].apply(round_coord)

        results = {}
        for (lat_r, lon_r), group in df.groupby(["lat_r", "lon_r"]):
            ts = pd.to_datetime(group["timestamp"])
            pollution_map = fetch_air_quality_data_interval(lat_r, lon_r, ts)
            for idx, tstamp in zip(group.index, ts):
                if pollution_map:
                    closest = min(pollution_map.keys(), key=lambda t: abs(t - tstamp))
                    results[idx] = pollution_map.get(closest, {})
                else:
                    results[idx] = {}

        # 2) извлекаем и конвертируем: OWM даёт µg/m³ → делим на 1000 → mg/m³
        df["pm25"] = [results.get(i, {}).get("pm2_5", 0.0) for i in df.index]
        df["no2"] = [results.get(i, {}).get("no2", 0.0) for i in df.index]
        df["so2"] = [results.get(i, {}).get("so2", 0.0) for i in df.index]
        df["o3"] = [results.get(i, {}).get("o3", 0.0) for i in df.index]
        df["co"] = [results.get(i, {}).get("co", 0.0) for i in df.index]

        # 3) агрегируем к почасовому и считаем метрики окна
        df = df.sort_values("timestamp")
        hourly = (
            df.set_index(pd.to_datetime(df["timestamp"]))
            .resample("1H")
            .mean(numeric_only=True)
        )

        def _safe_mean(s: pd.Series) -> float:
            return float(s.mean()) if (s is not None and not s.empty) else 0.0

        def _rolling_8h_max(s: pd.Series) -> float:
            if s is None or s.empty:
                return 0.0
            if len(s) < 8:
                return float(s.mean())
            return float(s.rolling(window=8, min_periods=8).mean().max())

        pm25_avg = _safe_mean(hourly["pm25"])
        no2_24h = _safe_mean(hourly["no2"])
        so2_24h = _safe_mean(hourly["so2"])
        o3_24h = _safe_mean(hourly["o3"])
        co_24h = _safe_mean(hourly["co"])

        o3_8hmax = _rolling_8h_max(hourly["o3"])
        co_8hmax = _rolling_8h_max(hourly["co"])

        return {
            # значения для формул рисков (mg/м³), без суффиксов
            "pm25": pm25_avg,
            "no2": no2_24h,
            "so2": so2_24h,
            "o3": o3_8hmax,
            "co": co_8hmax,
            # справочно
            "o3_24h": o3_24h,
            "co_24h": co_24h,
            "hours_covered": int(hourly.shape[0]),
            "n_movements": int(df.shape[0]),
            "data_quality": "ok" if hourly.shape[0] >= 8 else "low",
        }

    def week_info(self, locale: str | None = None) -> dict | None:
        """
        Вернёт словарь вида:
        {
           "week": int,
           "locale": str,
           "text": str,
           "source": "db"
        }
        или None, если неделя неизвестна или сообщение не найдено.
        """
        # Lazy import, чтобы избежать циклических зависимостей
        from recommendations.services.mamaair import get_mamaair_message_for_week

        week = self.current_week_of_pregnancy
        if not week:
            return None

        # приоритет: явный аргумент -> язык пользователя -> активный язык -> "en"
        loc = locale or getattr(self, "language", None) or get_language() or "en"
        return get_mamaair_message_for_week(week, loc)


class UserLifeStyle(models.Model):
    user = models.OneToOneField(
        User, on_delete=models.CASCADE, related_name="lifestyle"
    )

    average_sleep_hours = models.FloatField(null=True, blank=True)

    WORK_TYPE_CHOICES = [
        ("Desk", _("Desk")),
        ("Standing", _("Standing")),
        ("Physical", _("Physical")),
        ("Care", _("Care")),
        ("Field", _("Field")),
        ("Domestic", _("Domestic")),
        ("Night Shift", _("Night Shift")),
    ]

    WORK_INDOOR_OR_OUTDOOR_CHOICES = [
        ("Mostly Indoor", _("Mostly Indoor")),
        ("Mostly Outdoor", _("Mostly Outdoor")),
        ("Both equally", _("Both equally")),
    ]

    WORK_SCHEDULE_PATTERN = [
        ("day", _("Day")),
        ("evening", _("Evening")),
        ("irregular", _("Irregular")),
    ]

    work_type = models.CharField(
        max_length=64, choices=WORK_TYPE_CHOICES, null=True, blank=True
    )

    DIET_TYPE_CHOICES = [
        ("carnivore", _("Carnivore")),
        ("vegetarian", _("Vegetarian")),
    ]
    diet_type = models.CharField(
        max_length=64, choices=DIET_TYPE_CHOICES, null=True, blank=True
    )

    COOKING_METHOD_CHOICES = [
        ("wood", _("Wood")),
        ("charcoal", _("Charcoal")),
        ("gas", _("Gas")),
        ("electric", _("Electric")),
    ]
    cooking_method = models.CharField(
        max_length=64, choices=COOKING_METHOD_CHOICES, null=True, blank=True
    )

    activity_duration_minutes = models.IntegerField(null=True, blank=True)  # per week
    work_schedule_pattern = models.CharField(
        blank=True,
        null=True,
        choices=WORK_SCHEDULE_PATTERN,
        max_length=60,
    )

    standing_hours_per_day = models.FloatField(null=True, blank=True)

    AREA_CHOICES = [
        ("urban", _("Urban")),
        ("peri_urban", _("Peri-Urban")),
        ("rural", _("Rural")),
    ]
    area = models.CharField(
        max_length=32, choices=AREA_CHOICES, null=True, blank=True
    )

    TIME_SPENT_CHOICES = [
        ("mostly_indoors", _("Mostly indoors")),
        ("mostly_outdoors", _("Mostly outdoors")),
        ("both_equally", _("Both equally")),
    ]
    time_spent = models.CharField(
        max_length=32, choices=TIME_SPENT_CHOICES, null=True, blank=True
    )

    TIME_OF_DAY_CHOICES = [
        ("morning_hours", _("Morning hours")),
        ("midday_or_afternoon", _("Midday or afternoon")),
        ("evening", _("Evening")),
        ("changes_day_to_day", _("It changes day to day")),
    ]
    time_of_day = models.CharField(
        max_length=32, choices=TIME_OF_DAY_CHOICES, null=True, blank=True
    )

    # -------------------------
    # NEW FIELDS (customer request)
    # -------------------------

    COMMUTE_MODE_CHOICES = [
        ("walk", _("Walk")),
        ("matatu-bus", _("Matatu/Bus")),
        ("bike", _("Bike")),
        ("car", _("Car")),
        ("mixed", _("Mixed")),
    ]
    commute_mode = models.CharField(
        max_length=32, choices=COMMUTE_MODE_CHOICES, null=True, blank=True
    )

    hydration_target_ml_per_day = models.IntegerField(null=True, blank=True)

    # Лучше хранить как строку (как просили), но я бы держал единый формат "HH:MM-HH:MM"
    sleep_target_window = models.CharField(max_length=32, null=True, blank=True)

    REST_MICROBREAK_CHOICES = [
        ("5min", _("5 min")),
        ("10min", _("10 min")),
        ("15min", _("15 min")),
    ]
    rest_microbreak_preference = models.CharField(
        max_length=16, choices=REST_MICROBREAK_CHOICES, null=True, blank=True
    )

    supplement_preferences = models.TextField(null=True, blank=True)

    COOKING_VENUE_CHOICES = [
        ("indoor", _("Indoor")),
        ("veranda", _("Veranda")),
        ("outdoor", _("Outdoor")),
    ]
    cooking_venue = models.CharField(
        max_length=16, choices=COOKING_VENUE_CHOICES, null=True, blank=True
    )

    VENTILATION_LEVEL_CHOICES = [
        ("low", _("Low")),
        ("medium", _("Medium")),
        ("high", _("High")),
    ]
    ventilation_level = models.CharField(
        max_length=16, choices=VENTILATION_LEVEL_CHOICES, null=True, blank=True
    )

    # -------------------------

    RISK_FIELDS = [
        "average_sleep_hours",
        "work_type",
        "diet_type",
        "cooking_method",
        "activity_duration_minutes",
        # новые — если вы реально используете их в расчёте риска:
        # "commute_mode",
        # "hydration_target_ml_per_day",
        # "sleep_target_window",
        # "rest_microbreak_preference",
        # "cooking_venue",
        # "ventilation_level",
    ]

    def __str__(self):
        return f"{self.user.email} Lifestyle"


class RiskDefinition(models.Model):
    name = models.CharField(
        max_length=255,
        unique=True,
        help_text="",
    )
    description = models.TextField(blank=True, null=True)
    is_enabled = models.BooleanField(default=True)
    priority = models.IntegerField(
        default=0,
        help_text="",
    )

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class Symptom(models.Model):
    name = models.CharField(max_length=255, unique=True)
    code = models.CharField(max_length=255, unique=True)
    code_namespace = None

    class Meta:
        abstract = True
        ordering = ["name"]

    def __str__(self):
        return self.name

    def save(self, *args, **kwargs):
        if not self.code:
            slug = slugify(self.name).replace("-", "_")
            if not slug:
                raise ValueError("A stable symptom code cannot be generated from name")
            self.code = f"{self.code_namespace}.{slug}"
        super().save(*args, **kwargs)


class MommySymptom(Symptom):
    name = models.CharField(max_length=255, unique=True)
    code_namespace = SYMPTOM_CHECKLIST_MOMMY

    class Meta:
        db_table = "mommy_symptoms"


class BabySymptom(Symptom):
    name = models.CharField(max_length=255, unique=True)
    code_namespace = SYMPTOM_CHECKLIST_BABY

    class Meta:
        db_table = "baby_symptoms"


class RiskDefinitionMommySymptom(models.Model):
    risk_definition = models.ForeignKey(
        RiskDefinition, on_delete=models.CASCADE, related_name="mommy_symptom_links"
    )
    symptom = models.ForeignKey("MommySymptom", on_delete=models.CASCADE)
    symptom_class = models.PositiveSmallIntegerField(
        choices=SYMPTOM_CLASS_CHOICES,
        default=SYMPTOM_CLASS_SYSTEMIC,
    )
    source_phrase = models.CharField(max_length=512, blank=True, default="")

    class Meta:
        unique_together = ("risk_definition", "symptom")


class RiskDefinitionBabySymptom(models.Model):
    risk_definition = models.ForeignKey(
        RiskDefinition, on_delete=models.CASCADE, related_name="baby_symptom_links"
    )
    symptom = models.ForeignKey("BabySymptom", on_delete=models.CASCADE)
    symptom_class = models.PositiveSmallIntegerField(
        choices=SYMPTOM_CLASS_CHOICES,
        default=SYMPTOM_CLASS_FETAL,
    )
    source_phrase = models.CharField(max_length=512, blank=True, default="")

    class Meta:
        unique_together = ("risk_definition", "symptom")


class BaseUserSymptom(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)
    recorded_at = models.DateTimeField(default=timezone.now, editable=True)
    symptom = models.ForeignKey(Symptom, on_delete=models.CASCADE)

    class Meta:
        abstract = True
        ordering = ["-recorded_at"]

    @property
    def date_recorded(self):
        return self.recorded_at.date()

    def __str__(self):
        return f"{self.user.email} - {self.date_recorded} - {self.symptom}"


class UserMommySymptoms(BaseUserSymptom):
    symptom = models.ForeignKey(MommySymptom, on_delete=models.CASCADE)

    class Meta:
        db_table = "user_mommy_symptoms"  # existing table name


class UserBabySymptoms(BaseUserSymptom):
    symptom = models.ForeignKey(BabySymptom, on_delete=models.CASCADE)

    class Meta:
        db_table = "user_baby_symptoms"  # existing table name


class GeneratedSymptomChecklist(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="generated_symptom_checklists",
    )
    checklist_type = models.CharField(
        max_length=16,
        choices=SYMPTOM_CHECKLIST_TYPE_CHOICES,
    )
    local_date = models.DateField()
    generated_at = models.DateTimeField(auto_now_add=True)
    algorithm_version = models.CharField(max_length=64)

    class Meta:
        ordering = ["-local_date", "-generated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "checklist_type", "local_date"],
                name="unique_daily_symptom_checklist",
            )
        ]
        indexes = [
            models.Index(
                fields=["user", "checklist_type", "local_date"],
                name="symptom_checklist_lookup_idx",
            )
        ]

    def __str__(self):
        return f"{self.user} {self.checklist_type} {self.local_date}"


class GeneratedSymptomChecklistItem(models.Model):
    checklist = models.ForeignKey(
        GeneratedSymptomChecklist,
        on_delete=models.CASCADE,
        related_name="items",
    )
    symptom_id_snapshot = models.PositiveBigIntegerField()
    symptom_code = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255)
    position = models.PositiveSmallIntegerField()
    status = models.CharField(
        max_length=16,
        choices=SYMPTOM_STATUS_CHOICES,
        default=SYMPTOM_STATUS_NOT_ANSWERED,
    )

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["checklist", "position"],
                name="unique_symptom_checklist_position",
            ),
            models.UniqueConstraint(
                fields=["checklist", "symptom_code"],
                name="unique_symptom_checklist_code",
            ),
        ]

    def __str__(self):
        return f"{self.checklist_id} #{self.position} {self.symptom_code}"


class SymptomChecklistResponse(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    checklist = models.ForeignKey(
        GeneratedSymptomChecklist,
        on_delete=models.PROTECT,
        related_name="responses",
        null=True,
        blank=True,
    )
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="symptom_checklist_responses",
    )
    checklist_type = models.CharField(
        max_length=16,
        choices=SYMPTOM_CHECKLIST_TYPE_CHOICES,
    )
    local_date = models.DateField()
    recorded_at = models.DateTimeField()
    submitted_at = models.DateTimeField(auto_now_add=True)
    reported_symptom_ids = models.JSONField(default=list)
    reported_symptom_codes = models.JSONField(default=list)

    class Meta:
        ordering = ["-submitted_at"]
        indexes = [
            models.Index(
                fields=["user", "checklist_type", "local_date"],
                name="symptom_response_lookup_idx",
            )
        ]

    def __str__(self):
        return f"{self.user} {self.checklist_type} {self.local_date}"


class SymptomChecklistResponseItem(models.Model):
    response = models.ForeignKey(
        SymptomChecklistResponse,
        on_delete=models.CASCADE,
        related_name="items",
    )
    symptom_code = models.CharField(max_length=255)
    display_name = models.CharField(max_length=255)
    position = models.PositiveSmallIntegerField()
    status = models.CharField(max_length=16, choices=SYMPTOM_STATUS_CHOICES)

    class Meta:
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["response", "symptom_code"],
                name="unique_symptom_response_code",
            )
        ]

    def __str__(self):
        return f"{self.response_id} {self.symptom_code}={self.status}"


class Movement(models.Model):

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="movements")
    latitude = models.FloatField()
    longitude = models.FloatField()
    timestamp = models.DateTimeField()

    # Additive security fields. They remain nullable during rollout and backfill.
    h3_cell = models.CharField(
        max_length=15, null=True, blank=True, db_index=True, editable=False
    )
    coordinates_encrypted = models.BinaryField(null=True, blank=True, editable=False)
    coordinates_key_version = models.PositiveSmallIntegerField(
        null=True, blank=True, editable=False
    )
    coordinates_purged_at = models.DateTimeField(
        null=True, blank=True, editable=False
    )

    class Meta:
        db_table = "movements"  # existing table name
        ordering = ["-timestamp"]
        indexes = [
            models.Index(
                fields=["user", "timestamp"], name="movement_user_ts_idx"
            ),
            models.Index(
                fields=["user", "h3_cell", "timestamp"],
                name="movement_user_h3_ts_idx",
            ),
        ]

    def __str__(self):
        return f"{self.user.email} @ {self.timestamp}"


class AirExposureLog(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="air_exposure_logs"
    )
    timestamp = models.DateTimeField(db_index=True)
    latitude = models.FloatField()
    longitude = models.FloatField()
    h3_cell = models.CharField(
        max_length=15, null=True, blank=True, db_index=True, editable=False
    )

    pm25 = models.FloatField(null=True, blank=True)
    pm10 = models.FloatField(null=True, blank=True)
    no2 = models.FloatField(null=True, blank=True)
    so2 = models.FloatField(null=True, blank=True)
    co = models.FloatField(null=True, blank=True)
    o3 = models.FloatField(null=True, blank=True)  # ozone
    aqi = models.IntegerField(null=True, blank=True)  # Air Quality Index
    temperature = models.FloatField(null=True, blank=True)
    humidity = models.FloatField(null=True, blank=True)
    pressure = models.FloatField(null=True, blank=True)
    uvi = models.FloatField(null=True, blank=True)
    uvi_level = models.CharField(max_length=32, null=True, blank=True)
    wind_speed = models.FloatField(null=True, blank=True)  # wind speed in m/s

    exposure_minutes = models.IntegerField(default=60)
    activity_level = models.CharField(
        max_length=32, blank=True, null=True
    )  # "low", "moderate", "high"
    indoor = models.BooleanField(default=False)

    class Meta:
        ordering = ["-timestamp"]
        indexes = [
            models.Index(
                fields=["user", "h3_cell", "timestamp"],
                name="airexp_user_h3_ts_idx",
            ),
        ]


class HealthInsightSnapshot(models.Model):
    """
    Снимок рекомендаций для пользователя.
    recommendations — список объектов (карточек), а не просто строки. Пример элемента:
    {
      "id": "alert.pm25.daily.v1",
      "severity": "moderate",
      "title": "PM2.5 is high",
      "alert": "Limit outdoor time...",
      "recommendation_diet": "",
      "recommendation_activity": "Prefer indoor activity today.",
      "recommendation_behavior": "Ventilate with filtration if possible.",
      "category": "air_quality",
      "ttl_hours": 12,
      "expires_at": "2025-09-18T08:00:00Z",
      "sources": ["engine"],
      "engine_version": "receng-mvp-0.1"
    }
    """

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="health_insights"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    # Рекомендации (структурированный список карточек)
    recommendations = models.JSONField(default=list, blank=True)

    # Метаданные генерации
    source = models.CharField(max_length=32, default="engine")  # "engine" | "ml" | ...
    trigger_event = models.CharField(
        max_length=64, blank=True, null=True
    )  # "manual" | "login" | "auto"
    engine_version = models.CharField(max_length=32, default="receng-mvp-0.1")

    class Meta:
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["user", "-created_at"]),
        ]

    def __str__(self):
        return f"HealthInsightSnapshot(user={self.user_id}, created_at={self.created_at:%Y-%m-%d %H:%M})"


class AdviceTemplate(models.Model):
    title = models.CharField(max_length=255)
    text = models.TextField()

    # Optional metadata (can be used later)
    category = models.CharField(max_length=100, blank=True, null=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.title


class WeeklyExposure(models.Model):

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="weekly_exposures"
    )
    pregnancy_week = models.PositiveIntegerField()
    exposure_level = models.CharField(max_length=32, choices=EXPOSURE_LEVEL_CHOICES)

    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "pregnancy_week")
        ordering = ["-pregnancy_week"]

    def __str__(self):
        return f"{self.user.email} - Week {self.pregnancy_week} - {self.exposure_level}"


class DailyExposure(models.Model):

    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="daily_exposures"
    )
    date = models.DateField()
    exposure_level = models.CharField(max_length=32, choices=EXPOSURE_LEVEL_CHOICES)

    recorded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ("user", "date")
        ordering = ["-date"]

    def __str__(self):
        return f"{self.user.email} - {self.date} - {self.exposure_level}"


class AbstractRiskFactor(models.Model):
    risk = models.ForeignKey(RiskDefinition, on_delete=models.CASCADE)
    multiplier = models.FloatField()

    def __str__(self):
        return f"{self.risk.name} - {self.multiplier}"

    def get_multiplier(self, param=None):
        return self.multiplier

    class Meta:
        abstract = True


class UserRiskFactor(AbstractRiskFactor):
    condition = models.CharField(max_length=255)


class LifestyleRiskFactor(AbstractRiskFactor):
    condition = models.CharField(max_length=255)


class AQRiskFactor(AbstractRiskFactor):
    condition = models.CharField(max_length=255)
    formula = models.CharField(max_length=255)
    pollutant = models.CharField(max_length=255)

    def get_multiplier(self, param):
        multiplier = super().get_multiplier()
        if param is None:
            return multiplier
        new_formula = self.formula.replace("param", str(param))
        return multiplier * eval(new_formula)


class Exposure(models.Model):
    user = models.ForeignKey(
        "api.User", on_delete=models.CASCADE, related_name="exposures"
    )
    # локальная календарная дата (суточный агрегат)
    timestamp = models.DateField(default=timezone.localdate, editable=False)

    # интегральный суточный скор (раньше был "уровень" — оставляем имя поля)
    exposure_level = models.FloatField()

    # диагностические агрегаты по поллютантам — оставляем как есть (можно заполнять опционально)
    pollutants = models.JSONField(default=dict)

    risks = models.JSONField(default=dict, blank=True)

    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-timestamp"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "timestamp"], name="uniq_exposure_user_date"
            )
        ]
        indexes = [models.Index(fields=["user", "timestamp"])]

    def __str__(self):
        return f"{self.user_id} {self.timestamp}: {self.exposure_level}"

    @classmethod
    def set_for_date(cls, user, level: float, pollutants=None, risks=None, date=None):
        """
        Upsert на (user, date). Заменяет интегральный скор (exposure_level),
        а также pollutants и risks за этот день.
        """
        date = date or timezone.localdate()
        with transaction.atomic():
            obj, _created = cls.objects.update_or_create(
                user=user,
                timestamp=date,
                defaults={
                    "exposure_level": float(level),
                    "pollutants": pollutants or {},
                    "risks": risks or {},
                },
            )
        return obj


class GuidelineLimit(models.Model):
    """
    Конфигурируемые предельные уровни (например, WHO AQG 2021).
    Позволяет версионирование и переключение активных лимитов без правки кода.
    """

    # базовые справочники
    POLLUTANT_CHOICES = [
        ("pm25", "PM2.5"),
        ("pm10", "PM10"),
        ("no2", "NO₂"),
        ("o3", "O₃"),
        ("so2", "SO₂"),
        ("co", "CO"),
    ]
    # усреднение. На старте достаточно 24h/8h; далее можно расширять.
    AVG_PERIOD_CHOICES = [
        ("24h", "24h mean"),
        ("8h", "8h mean"),
        ("1h", "1h mean"),
        ("annual", "annual"),
    ]

    pollutant = models.CharField(
        max_length=10, choices=POLLUTANT_CHOICES, db_index=True
    )
    avg_period = models.CharField(
        max_length=10, choices=AVG_PERIOD_CHOICES, db_index=True
    )

    # числовое значение и единицы измерения
    value = models.FloatField(help_text="Limit value in the specified unit")
    unit = models.CharField(
        max_length=16,
        help_text="e.g. µg/m³ or mg/m³",
        default="µg/m³",
    )

    # метаданные источника/версии
    source = models.CharField(max_length=64, default="WHO")
    version = models.CharField(max_length=64, default="AQG 2021", db_index=True)

    # период действия (не обязательно)
    valid_from = models.DateField(null=True, blank=True, default=None)
    valid_to = models.DateField(null=True, blank=True, default=None)

    # активный набор — удобно переключать для A/B/локальных стандартов
    is_active = models.BooleanField(default=True, db_index=True)

    # служебные
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "guideline_limits"
        ordering = ["pollutant", "avg_period", "-is_active", "version", "-created_at"]
        # Разрешаем несколько версий/источников, но не дубли внутри одной версии/источника
        unique_together = ("pollutant", "avg_period", "version", "source")

    def __str__(self):
        return f"{self.source} {self.version} • {self.get_pollutant_display()} • {self.avg_period} = {self.value} {self.unit}"

    @classmethod
    def active_map(cls):
        """
        Возвращает dict {(pollutant, avg_period): GuidelineLimit} только по активным записям.
        Если активных несколько — берём последнюю по updated_at.
        """
        qs = cls.objects.filter(is_active=True).order_by(
            "pollutant", "avg_period", "-updated_at", "-id"
        )
        out = {}
        for gl in qs:
            key = (gl.pollutant, gl.avg_period)
            if key not in out:
                out[key] = gl
        return out


class RecommendationCompletion(models.Model):
    DIMENSION_CHOICES = [
        ("diet", "Diet"),
        ("activity", "Activity"),
        ("behavior", "Behavior"),
    ]

    STATUS_CHOICES = [
        ("done", "Done"),
        ("skipped", "Skipped"),
        ("dismissed", "Dismissed"),
    ]

    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="recommendation_completions",
    )

    snapshot = models.ForeignKey(
        HealthInsightSnapshot,
        on_delete=models.CASCADE,
        related_name="completions",
    )

    # link to rule (stable even if snapshot JSON changes)
    rule_id = models.CharField(max_length=128)
    rule_version = models.PositiveIntegerField(default=1)

    dimension = models.CharField(max_length=16, choices=DIMENSION_CHOICES)
    status = models.CharField(max_length=16, choices=STATUS_CHOICES, default="done")

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "recommendation_completions"
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "snapshot", "rule_id", "rule_version", "dimension"],
                name="uniq_user_snapshot_rule_dimension",
            )
        ]
        indexes = [
            models.Index(fields=["user", "-updated_at"]),
            models.Index(fields=["snapshot", "rule_id", "rule_version"]),
        ]

    def __str__(self):
        return f"{self.user_id} {self.rule_id}.v{self.rule_version} {self.dimension}={self.status}"


class DailyPlan(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="daily_plans",
    )
    local_date = models.DateField()
    timezone = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-local_date", "-created_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["user", "local_date"],
                name="uniq_daily_plan_user_local_date",
            )
        ]
        indexes = [models.Index(fields=["user", "local_date"])]

    def __str__(self):
        return f"{self.user_id} {self.local_date} ({self.timezone})"


class DailyAction(models.Model):
    DOMAIN_CHOICES = [
        ("nutrition", "Nutrition"),
        ("activity", "Activity"),
        ("behavior", "Behavior"),
        ("mental", "Mental"),
        ("service", "Service"),
    ]
    ROLE_CHOICES = [
        ("primary", "Primary"),
        ("additional", "Additional"),
        ("support", "Support"),
    ]
    SOURCE_TYPE_CHOICES = [
        ("recommendation", "Recommendation"),
        ("task", "Task"),
    ]
    SOURCE_DIMENSION_CHOICES = RecommendationCompletion.DIMENSION_CHOICES

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    plan = models.ForeignKey(
        DailyPlan,
        on_delete=models.CASCADE,
        related_name="actions",
    )
    stable_key = models.CharField(max_length=255)
    domain = models.CharField(max_length=16, choices=DOMAIN_CHOICES)
    role = models.CharField(max_length=16, choices=ROLE_CHOICES)
    title = models.CharField(max_length=255)
    description = models.TextField()
    timing = models.CharField(max_length=128, null=True, blank=True)
    duration_minutes = models.PositiveIntegerField(null=True, blank=True)
    context = models.CharField(max_length=255, null=True, blank=True)
    sort_order = models.PositiveIntegerField(default=0)

    source_type = models.CharField(max_length=16, choices=SOURCE_TYPE_CHOICES)
    source_task_id = models.PositiveBigIntegerField(null=True, blank=True)
    source_snapshot_id = models.PositiveBigIntegerField(null=True, blank=True)
    source_rule_id = models.CharField(max_length=128, null=True, blank=True)
    source_rule_version = models.PositiveIntegerField(null=True, blank=True)
    source_dimension = models.CharField(
        max_length=16,
        choices=SOURCE_DIMENSION_CHOICES,
        null=True,
        blank=True,
    )

    class Meta:
        ordering = ["sort_order", "stable_key"]
        constraints = [
            models.UniqueConstraint(
                fields=["plan", "stable_key"],
                name="uniq_daily_action_plan_stable_key",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        source_type="task",
                        source_task_id__isnull=False,
                        source_snapshot_id__isnull=True,
                        source_rule_id__isnull=True,
                        source_rule_version__isnull=True,
                        source_dimension__isnull=True,
                    )
                    | models.Q(
                        source_type="recommendation",
                        source_task_id__isnull=True,
                        source_snapshot_id__isnull=False,
                        source_rule_id__isnull=False,
                        source_rule_version__isnull=False,
                        source_dimension__isnull=False,
                    )
                ),
                name="valid_daily_action_source",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(role="support", domain="service")
                    | (models.Q(role__in=["primary", "additional"]) & ~models.Q(domain="service"))
                ),
                name="valid_daily_action_role_domain",
            ),
        ]
        indexes = [
            models.Index(fields=["plan", "role", "sort_order"]),
            models.Index(fields=["source_snapshot_id", "source_rule_id"]),
        ]

    def __str__(self):
        return f"{self.plan_id} {self.role}/{self.domain}: {self.title}"


class Wellbeing(models.Model):
    KIND_CHOICES = (
        ("mood", "Mood (chips)"),
        ("feeling", "Feeling (chips)"),
        ("water_goal", "Water goal/setting"),
    )

    kind = models.CharField(max_length=32, choices=KIND_CHOICES)

    # for mood/feeling
    code = models.SlugField(
        max_length=64, unique=True, null=True, blank=True
    )  # optional stable key
    title = models.CharField(max_length=255, blank=True, default="")
    emoji = models.CharField(max_length=16, blank=True, default="")
    sort_order = models.PositiveIntegerField(default=0)

    # for water_goal
    number_value = models.FloatField(null=True, blank=True)  # e.g. 72
    unit = models.CharField(max_length=16, blank=True, default="ml")  # ml / l

    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["kind", "sort_order", "title"]

    def __str__(self):
        if self.kind == "water_goal":
            return f"Water goal: {self.number_value} {self.unit}"
        return f"{self.kind}: {self.title}"


class UserWellbeingLog(models.Model):
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="wellbeing_logs",
    )
    date = models.DateField()

    water_amount = models.FloatField(default=0)  # e.g. 32
    water_unit = models.CharField(max_length=16, default="ml")

    moods = models.ManyToManyField(Wellbeing, blank=True, related_name="mood_logs")
    feelings = models.ManyToManyField(
        Wellbeing, blank=True, related_name="feeling_logs"
    )

    class Meta:
        unique_together = (("user", "date"),)
        ordering = ["-date"]

    def __str__(self):
        return f"{self.user_id} {self.date}"


class DailyCheckin(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="daily_checkins",
    )
    date = models.DateField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = (("user", "date"),)
        ordering = ["-date"]


class DailyTask(models.Model):
    CATEGORY_CHOICES = [
        ("diet", "Diet"),
        ("activity", "Activity"),
        ("behavior", "Behavior"),
        ("mental", "Mental"),
    ]

    code = models.SlugField(max_length=64, unique=True)
    title = models.CharField(max_length=255)
    category = models.CharField(
        max_length=16,
        choices=CATEGORY_CHOICES,
        default="behavior",
        db_index=True,
    )
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["sort_order", "title"]

    def __str__(self):
        return self.title


class UserDailyTaskCompletion(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name="task_completions",
    )
    task = models.ForeignKey(
        DailyTask,
        on_delete=models.PROTECT,
        related_name="completions",
    )
    date = models.DateField()
    completed = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["user", "task", "date"],
                name="uniq_user_task_completion_date",
            )
        ]
        indexes = [
            models.Index(
                fields=["user", "date"],
                name="api_userdai_user_id_52c953_idx",
            ),
            models.Index(
                fields=["user", "task", "date"],
                name="api_userdai_user_id_9df84f_idx",
            ),
        ]
        ordering = ["-date", "task__sort_order", "task__title"]

    def __str__(self):
        return f"{self.user_id} {self.date} {self.task.code}={self.completed}"
