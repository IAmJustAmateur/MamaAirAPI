# api/models.py

import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser, BaseUserManager
from datetime import date

from django.utils.translation import gettext_lazy as _

from django.utils.translation import gettext_lazy as _


# models.py

from django.contrib.auth.models import BaseUserManager


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


class User(AbstractUser):

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
    email = models.EmailField(unique=True)
    username = None

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    name = models.CharField(max_length=255, null=True, blank=True)
    registered_at = models.DateTimeField(auto_now_add=True)

    language = models.CharField(max_length=10, choices=LANGUAGE_CHOICES, default="en")

    # demographic data
    date_of_birth = models.IntegerField(null=True, blank=True)
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
        return f"{self.name} ({self.email})"

    @property
    def bmi(self):
        return self.weight_pre_pregnancy / ((self.height / 100) ** 2)

    @property
    def MVPA(self):
        pass


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

    activity_duration_minutes = models.IntegerField(null=True, blank=True)

    def __str__(self):
        return f"{self.user.email} Lifestyle"


class UserMommySymptoms(models.Model):
    MOMMY_SYMPTOM_CHOICES = [
        ("Headache", _("Headache")),
        ("Nausea", _("Nausea")),
        ("Fatigue", _("Fatigue")),
        ("Back Pain", ("Back Pain")),
        ("Mood Swings", _("Mood Swings")),
    ]
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="mommy_symptoms"
    )
    symptom = models.CharField(max_length=255, choices=MOMMY_SYMPTOM_CHOICES)
    date_recorded = models.DateField(default=date.today)

    class Meta:
        db_table = "user_mommy_symptoms"  # existing table name
        ordering = ["-date_recorded"]

    def __str__(self):
        return f"{self.user.email} - {self.symptom}"


class UserBabySymptoms(models.Model):
    BABY_SYMPTOM_CHOICES = [
        ("Kicking", _("Kicking")),
        ("Hiccups", _("Hiccups")),
        ("Fetal Movement", _("Fetal Movement")),
        ("Reduced Movement", _("Reduced Movement")),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="symptoms")
    symptom = models.CharField(max_length=255, choices=BABY_SYMPTOM_CHOICES)
    date_recorded = models.DateField(default=date.today)

    class Meta:
        db_table = "user_symptoms"  # existing table name
        ordering = ["-date_recorded"]

    def __str__(self):
        return f"{self.user.email} - {self.symptom}"


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
