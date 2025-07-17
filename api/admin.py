# api/admin.py

from django.contrib import admin
from .models import (
    User,
    UserLifeStyle,
    UserMommySymptoms,
    UserBabySymptoms,
    Movement,
    AirExposureLog,
    HealthInsightSnapshot,
)
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = (
        "email",
        "name",
        "country",
        "race",
        "week_of_pregnancy",
        "registered_at",
    )
    list_filter = ("country", "race", "week_of_pregnancy", "tracking_enabled")
    search_fields = ("email", "name")
    ordering = ("-registered_at",)
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Personal info",
            {
                "fields": (
                    "name",
                    "date_of_birth",
                    "height",
                    "weight_pre_pregnancy",
                )
            },
        ),
        (
            "Pregnancy",
            {"fields": ("race", "country", "is_first_pregnancy", "trimester")},
        ),
        ("Settings", {"fields": ("tracking_enabled", "notifications_enabled")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
    )
    add_fieldsets = (
        (
            None,
            {
                "classes": ("wide",),
                "fields": ("email", "password1", "password2"),
            },
        ),
    )
    filter_horizontal = ("groups", "user_permissions")


@admin.register(UserLifeStyle)
class UserLifeStyleAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "average_sleep_hours",
        "work_type",
        "diet_type",
        "cooking_method",
    )
    search_fields = ("user__email",)


@admin.register(UserMommySymptoms)
class UserMommySymptomsAdmin(admin.ModelAdmin):
    list_display = ("user", "symptom", "severity", "date_recorded")
    list_filter = ("symptom", "date_recorded")
    search_fields = ("user__email",)


@admin.register(UserBabySymptoms)
class UserBabySymptomsAdmin(admin.ModelAdmin):
    list_display = ("user", "symptom", "severity", "date_recorded")
    list_filter = ("symptom", "date_recorded")
    search_fields = ("user__email",)


@admin.register(Movement)
class MovementAdmin(admin.ModelAdmin):
    list_display = ("user", "latitude", "longitude", "timestamp")
    search_fields = ("user__email",)
    list_filter = ("timestamp",)


@admin.register(AirExposureLog)
class AirExposureLogAdmin(admin.ModelAdmin):
    list_display = ("user", "timestamp", "aqi", "pm25", "pm10", "indoor")
    list_filter = ("indoor", "timestamp")
    search_fields = ("user__email",)


@admin.register(HealthInsightSnapshot)
class HealthInsightSnapshotAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "source")
    list_filter = ("source", "created_at")
    search_fields = ("user__email",)
