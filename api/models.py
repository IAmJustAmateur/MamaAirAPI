# api/models.py

import uuid
from django.db import models, transaction
from django.contrib.auth.models import BaseUserManager
from datetime import date, timedelta

from django.utils.translation import gettext_lazy as _
from django.utils import timezone

from logging import getLogger

import pandas as pd

logger = getLogger(__name__)

# models.py

from django.contrib.auth.models import (
    BaseUserManager,
    AbstractBaseUser,
    PermissionsMixin,
)

from api.services import round_coord, fetch_air_quality_data_interval

from api.utils import calculate_exposure

USER_RISK_FACTORS = [
    "bmi",
    "full_year",
    "race",
]


def _calculate_risks(risks, fields, object, RiskModel):
    """
    Calculate risk factors based on given object and risk factors.

    Args:
        risks (list of RiskDefinition): Risk definitions to calculate.
        fields (list of str): Fields of object that are used in risk factor conditions.
        object (Any): Object to calculate risk factors for.
        RiskModel (type): Type of RiskModel to use when calculating risk factors.

    Returns:
        dict: Dictionary with risk names as keys and calculated risk factors as values.
    """
    risks_dictionary = {}
    for risk in risks:
        base_risk = 1.0  # Base risk factor
        risk_factors = RiskModel.objects.filter(risk=risk)

        for risk_factor in risk_factors:
            for factor in fields:
                if factor in risk_factor.condition:
                    if hasattr(object, factor):
                        value = getattr(object, factor)
                        if value:
                            condition = risk_factor.condition.replace(
                                factor, str(value)
                            )
                            logger.info(
                                f"Condition: {condition}, factor: {factor}, value: {value}"
                            )
                            try:
                                if eval(condition):
                                    multiplier = risk_factor.get_multiplier(str(value))
                                    base_risk *= multiplier
                            except:
                                pass
        risks_dictionary[risk.name] = base_risk
    return risks_dictionary


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
]


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
        ("nigeria", "Nigeria"),
        ("ghana", "Ghana"),
        ("other", "Other"),
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
    week_of_pregnancy = models.IntegerField(null=True, blank=True)

    tracking_enabled = models.BooleanField(default=False)
    notifications_enabled = models.BooleanField(default=False)

    def __str__(self):
        if self.name:
            return f"{self.name} ({self.email})"
        else:
            return f"{self.email}"

    @property
    def bmi(self):
        return self.weight_pre_pregnancy / ((self.height / 100) ** 2)

    @property
    def full_year(self):
        return (
            date.today().year - self.date_of_birth.year if self.date_of_birth else None
        )

    @property
    def MVPA(self):
        pass

    def calculate_risk_factors(self):
        life_style_risks = self.calculate_risk_factor_based_on_lifestyle()
        user_risks = self.calculate_risk_factor_based_on_user_fields()
        aq_risks, pollutants = self.calculate_risk_factor_based_on_aq()
        exposure_value = calculate_exposure(aq_risks)
        Exposure.set_for_date(user=self, level=exposure_value, pollutants=pollutants)
        risks = RiskDefinition.objects.filter(is_enabled=True)
        risk_dictionary = {}
        for risk in risks:
            if risk.name in life_style_risks:
                life_style_multiplier = life_style_risks[risk.name]
            else:
                life_style_multiplier = 1
            if risk.name in user_risks:
                user_risks_multiplier = user_risks[risk.name]
            else:
                user_risks_multiplier = 1
            if risk.name in aq_risks:
                aq_risks_multiplier = aq_risks[risk.name]
            else:
                aq_risks_multiplier = 1

            risk.risk_factor_multiplier = (
                life_style_multiplier * user_risks_multiplier * aq_risks_multiplier
            )

            risk_dictionary[risk.name] = {
                "risk_value": risk.risk_factor_multiplier,
                "priority": risk.priority,
            }
        return risk_dictionary

    def calculate_risk_factor_based_on_user_fields(self):

        risks = RiskDefinition.objects.filter(is_enabled=True)
        risk_dictionary = _calculate_risks(
            risks=risks, object=self, fields=USER_RISK_FACTORS, RiskModel=UserRiskFactor
        )
        return risk_dictionary

    def calculate_risk_factor_based_on_lifestyle(self):

        user_life_style = UserLifeStyle.objects.get(user=self.id)
        risks = RiskDefinition.objects.filter(is_enabled=True)

        field_names = [field.name for field in UserLifeStyle._meta.fields]

        risk_dictionary = _calculate_risks(
            risks=risks,
            object=user_life_style,
            fields=field_names,
            RiskModel=LifestyleRiskFactor,
        )
        return risk_dictionary

    def calculate_risk_factor_based_on_aq(self, aq_data=None):
        if aq_data is None:
            aq_data = self.get_air_quality_inputs_for_risks()
        risks = RiskDefinition.objects.filter(is_enabled=True)
        # field_names = [field.name for field in aq_data.keys()]
        field_names = aq_data.keys()
        risk_dictionary = _calculate_risks(
            risks=risks,
            object=aq_data,
            fields=field_names,
            RiskModel=AQRiskFactor,
        )
        return risk_dictionary, aq_data

    def get_mommy_symptoms_for_checking(self):
        """
        Return a dictionary of mommy symptoms for each risk factor, sorted by value in descending order.
        The keys are the risk factor names, the values are dictionaries with "value" and "symptoms" keys.
        The "value" key stores the risk factor multiplier, and the "symptoms" key stores a list of symptom names.

        :return: A dictionary of mommy symptoms for each risk factor
        :rtype: dict
        """
        risks = self.calculate_risk_factors()
        risk_list = [(key, value) for key, value in risks.items()]
        risk_list.sort(key=lambda x: x[1]["risk_value"], reverse=True)
        risk_list.sort(key=lambda x: x[1]["priority"], reverse=False)
        all_risk_symptoms_for_mommy = {}
        for risk_tuple in risk_list:
            risk = RiskDefinition.objects.get(name=risk_tuple[0])
            risk_symptoms = RiskDefinitionMommySymptom.objects.filter(
                risk_definition=risk
            )
            all_risk_symptoms_for_mommy[risk_tuple[0]] = {
                "value": risk_tuple[1],
                "symptoms": [symptom.symptom.name for symptom in risk_symptoms],
            }

        symptoms = []
        for risk, data in all_risk_symptoms_for_mommy.items():
            symptoms.extend(data["symptoms"])
        return symptoms[0:5]

    def get_baby_symptoms_for_checking(self):
        """
        :return: A dictionary of baby symptoms for each risk factor
        :rtype: dict
        """
        rdbs = RiskDefinitionBabySymptom.objects.all()
        symptoms = [symptom.symptom.name for symptom in rdbs]
        return symptoms

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

        pm25_24h = _safe_mean(hourly["pm25"])
        no2_24h = _safe_mean(hourly["no2"])
        so2_24h = _safe_mean(hourly["so2"])
        o3_24h = _safe_mean(hourly["o3"])
        co_24h = _safe_mean(hourly["co"])

        o3_8hmax = _rolling_8h_max(hourly["o3"])
        co_8hmax = _rolling_8h_max(hourly["co"])

        return {
            # значения для формул рисков (mg/м³), без суффиксов
            "pm25": pm25_24h,
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
        # shift work
        # standart work
        # work hours уберу
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

    activity_duration_minutes = models.IntegerField(
        null=True, blank=True
    )  # в минутах в неделю

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

    class Meta:
        abstract = True
        ordering = ["name"]

    def __str__(self):
        return self.name


class MommySymptom(Symptom):
    pass


class BabySymptom(models.Model):
    pass


class RiskDefinitionMommySymptom(models.Model):
    risk_definition = models.ForeignKey(
        RiskDefinition, on_delete=models.CASCADE, related_name="mommy_symptom_links"
    )
    symptom = models.ForeignKey("MommySymptom", on_delete=models.CASCADE)

    class Meta:
        unique_together = ("risk_definition", "symptom")


class RiskDefinitionBabySymptom(models.Model):
    risk_definition = models.ForeignKey(
        RiskDefinition, on_delete=models.CASCADE, related_name="baby_symptom_links"
    )
    symptom = models.ForeignKey("BabySymptom", on_delete=models.CASCADE)

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


class Movement(models.Model):

    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="movements")
    latitude = models.FloatField()
    longitude = models.FloatField()
    timestamp = models.DateTimeField()

    class Meta:
        db_table = "movements"  # existing table name
        ordering = ["-timestamp"]

    def __str__(self):
        return f"{self.user.email} @ {self.timestamp}"


class AirExposureLog(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="air_exposure_logs"
    )
    timestamp = models.DateTimeField()  # когда получены данные
    latitude = models.FloatField()
    longitude = models.FloatField()

    aqi = models.FloatField()  # Air Quality Index
    pm25 = models.FloatField(null=True, blank=True)
    pm10 = models.FloatField(null=True, blank=True)
    no2 = models.FloatField(null=True, blank=True)
    so2 = models.FloatField(null=True, blank=True)
    co = models.FloatField(null=True, blank=True)
    o3 = models.FloatField(null=True, blank=True)  # ozone
    aqi = models.IntegerField(null=True, blank=True)  # Air Quality Index
    temperature = models.FloatField(null=True, blank=True)
    humidity = models.FloatField(null=True, blank=True)
    wind_speed = models.FloatField(null=True, blank=True)  # wind speed in m/s

    exposure_minutes = models.IntegerField(
        default=60
    )  # сколько минут пользователь находился в этих условиях
    activity_level = models.CharField(
        max_length=32, blank=True, null=True
    )  # "low", "moderate", "high"
    indoor = models.BooleanField(default=False)  # если ты планируешь учитывать это

    class Meta:
        ordering = ["-timestamp"]


class HealthInsightSnapshot(models.Model):
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="health_insights"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    # риски по категориям
    mommy_risk = models.JSONField()  # {"fatigue": 3, "headache": 2}
    baby_risk = models.JSONField()  # {"reduced_movement": 2}

    # рекомендации
    recommendations = (
        models.JSONField()
    )  # список строк: ["Avoid charcoal cooking", "Increase rest"]

    # метаинформация

    source = models.CharField(max_length=32, default="engine")  # или "ml"
    trigger_event = models.CharField(
        max_length=64, blank=True, null=True
    )  # "manual", "login", "auto"

    class Meta:
        ordering = ["-created_at"]


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
        new_formua = self.formula.replace("param", str(param))
        return multiplier * eval(new_formua)


class Exposure(models.Model):
    user = models.ForeignKey(
        "api.User", on_delete=models.CASCADE, related_name="exposures"
    )
    timestamp = models.DateField(default=timezone.localdate, editable=False)
    exposure_level = models.FloatField()
    updated_at = models.DateTimeField(auto_now=True)
    pollutants = models.JSONField(default=dict)

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
    def set_for_date(cls, user, level: float, pollutants=None, date=None):
        """Upsert на (user, date). Заменяет exposure_level и pollutants за этот день."""
        date = date or timezone.localdate()
        with transaction.atomic():
            obj, _created = cls.objects.update_or_create(
                user=user,
                timestamp=date,
                defaults={
                    "exposure_level": level,
                    "pollutants": pollutants or {},
                },
            )
        return obj
