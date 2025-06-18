# api/models.py

import uuid
from django.db import models
from django.contrib.auth.models import AbstractUser
from datetime import date


RACE_CHOICES = [
    ("caucasian", "Caucasian"),
    ("african", "African"),
    ("asian", "Asian"),
    ("hispanic", "Hispanic"),
    ("mixed", "Mixed"),
]


class User(AbstractUser):
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
    is_first_pregnancy = models.BooleanField(null=True, blank=True)
    conception_date = models.DateField(null=True, blank=True)

    def __str__(self):
        return self.email

    @property
    def bmi(self):
        return self.weight_pre_pregnancy / ((self.height / 100) ** 2)

    @property
    def pregnancy_trimester(self):
        """
        Determine the current pregnancy trimester based on the conception date.

        Returns:
            int: The pregnancy trimester (1, 2, 3, or 4). Returns 1 if no conception date is provided.
                - 1: First trimester (up to 12 weeks).
                - 2: Second trimester (13 to 27 weeks).
                - 3: Third trimester (28 to 40 weeks).
                - 4: Beyond 40 weeks.
        """

        if not self.conception_date:
            return 1

        days_pregnant = (date.today() - self.conception_date).days
        weeks_pregnant = days_pregnant // 7

        if weeks_pregnant <= 12:
            return 1
        elif weeks_pregnant <= 27:
            return 2
        elif weeks_pregnant <= 40:
            return 3
        else:
            return 4

    @property
    def MVPA(self):
        pass


MEDICAL_CONDITION_CATEGORIES = [
    ("light", "Light"),
    ("moderate", "Moderate"),
    ("severe", "Severe"),
]


class MedicalCondition(models.Model):
    name = models.CharField(max_length=255)
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="medical_conditions"
    )
    category = models.CharField(max_length=255, choices=MEDICAL_CONDITION_CATEGORIES)
    risk_coefficients = models.JSONField(default=dict)

    def __str__(self):
        return f"{self.name} ({self.category})"


class Medication(models.Model):
    name = models.CharField(max_length=255)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="medications")
    risk_coefficients = models.JSONField(
        default=dict
    )  # ! TO DO: explain risk coefficients
    pregnancy_safety = models.CharField(max_length=255, blank=True, null=True)
    medication_class = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
        return f"{self.name} ({self.category})"


class PatientMedication(models.Model):
    patient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="patient_medications"
    )
    medication = models.ForeignKey(Medication, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    dosage = models.CharField(max_length=255)
    frequency = models.CharField(max_length=255)
    prescribed_by = models.CharField(max_length=255)


class Supplement(models.Model):
    name = models.CharField(max_length=255)
    type = models.CharField(max_length=255)
    risk_coefficients = models.JSONField(
        default=dict
    )  # ! TO DO: explain risk coefficients
    components = models.JSONField(default=dict, blank=True, null=True)

    def __str__(self):
        return f"{self.name} ({self.type})"


class PatientSupplements(models.Model):
    patient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="patient_supplements"
    )
    supplement = models.ForeignKey(Supplement, on_delete=models.CASCADE)
    start_date = models.DateField()
    dosage = models.CharField(max_length=255)
    frequency = models.CharField(max_length=255)
    prescribed_by = models.CharField(max_length=255)


class PatientLyfeStyleTracker(models.Model):
    WORK_TYPES = [
        ("Office", "Office"),
        ("Home", "Home"),
        ("Other", "Other"),
    ]
    patient = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name="patient_lifestyle"
    )
    work_type = models.CharField(max_length=255, choices=WORK_TYPES)
    work_hours_daily = models.FloatField()
    work_stress_level = models.FloatField()  # 1-10
    activity_hours = models.FloatField()  # per week
    sleep_hours_daily = models.FloatField()
    sleep_quality = models.FloatField()  # 1-10

    work_details = models.JSONField(default=dict, blank=True, null=True)
    exercise_details = models.JSONField(default=dict, blank=True, null=True)
    nutrition_data = models.JSONField(default=dict, blank=True, null=True)
    household_data = models.JSONField(default=dict, blank=True, null=True)

    day = models.DateField(auto_now_add=True)


class Movement(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
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
    fetal_risk_score = models.FloatField()
    pdf = models.FileField(upload_to="reports/", null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "daily_exposure_summary"  # existing table name
        ordering = ["-analysis_date"]

    def __str__(self):
        return f"{self.user.email} – {self.analysis_date}"
