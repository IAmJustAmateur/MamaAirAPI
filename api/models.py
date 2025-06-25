# api/models.py

import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser
from datetime import date

from django.utils.translation import gettext_lazy as _


class User(AbstractUser):

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

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = ["username"]

    name = models.CharField(max_length=255, null=True, blank=True)
    registered_at = models.DateTimeField(auto_now_add=True)

    # demographic data
    date_of_birth = models.IntegerField(null=True, blank=True)
    height = models.FloatField(null=True, blank=True)
    weight_pre_pregnancy = models.FloatField(null=True, blank=True)

    race = models.CharField(max_length=255, null=True, blank=True, choices=RACE_CHOICES)
    country = models.CharField(
        max_length=255, null=True, blank=True, choices=COUNTRY_CHOICES
    )
    is_first_pregnancy = models.BooleanField(null=True, blank=True)
    trimester = models.IntegerField(
        null=True, blank=True
    )  # 1, 2, 3, or 4 (4 = postpartum)

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
        ("Physical", -("Physical")),
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
    severity = models.IntegerField()  # 1-5 scale
    date_recorded = models.DateField(default=date.today)

    class Meta:
        db_table = "user_mommy_symptoms"  # existing table name
        ordering = ["-date_recorded"]

    def __str__(self):
        return f"{self.user.email} - {self.symptom} ({self.severity})"


class UserBabySymptoms(models.Model):
    BABY_SYMPTOM_CHOICES = [
        ("Kicking", _("Kicking")),
        ("Hiccups", _("Hiccups")),
        ("Fetal Movement", _("Fetal Movement")),
        ("Reduced Movement", _("Reduced Movement")),
    ]
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="symptoms")
    symptom = models.CharField(max_length=255, choices=BABY_SYMPTOM_CHOICES)
    severity = models.IntegerField(blank=True, null=True)  # 1-5 scale
    date_recorded = models.DateField(default=date.today)

    class Meta:
        db_table = "user_symptoms"  # existing table name
        ordering = ["-date_recorded"]

    def __str__(self):
        return f"{self.user.email} - {self.symptom} ({self.severity})"


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


class DailyExposureSummary(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="summaries")
    analysis_date = models.DateField()
    pm25_avg = models.FloatField()
    no2_peak = models.FloatField()
    o3_peak = models.FloatField()
    exposure_hours = models.FloatField()
    baby_risk_score = models.FloatField()
    mommy_risk_score = models.FloatField()
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "daily_exposure_summary"  # existing table name
        ordering = ["-analysis_date"]

    def __str__(self):
        return f"{self.user.email} – {self.analysis_date}"
