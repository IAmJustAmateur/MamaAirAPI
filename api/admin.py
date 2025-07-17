from django import forms
from django.contrib import admin
from django.contrib.admin import AdminSite
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.forms import AuthenticationForm
from django.utils.translation import gettext_lazy as _
from .models import (
    User,
    UserLifeStyle,
    UserMommySymptoms,
    UserBabySymptoms,
    Movement,
    AirExposureLog,
    HealthInsightSnapshot,
)


# 👤 Форма логина по email для админки
class EmailAdminAuthenticationForm(AuthenticationForm):
    username = forms.EmailField(
        label=_("Email"), widget=forms.TextInput(attrs={"autofocus": True})
    )

    def confirm_login_allowed(self, user):
        pass


# 👤 Кастомный сайт админки с формой логина по email
class CustomAdminSite(AdminSite):
    login_form = EmailAdminAuthenticationForm


admin_site = CustomAdminSite(name="custom_admin")


# 👤 UserAdmin без username
@admin.register(User, site=admin_site)
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
            {"fields": ("name", "date_of_birth", "height", "weight_pre_pregnancy")},
        ),
        (
            "Pregnancy",
            {"fields": ("race", "country", "is_first_pregnancy", "week_of_pregnancy")},
        ),
        (
            "Settings",
            {"fields": ("language", "tracking_enabled", "notifications_enabled")},
        ),
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
                "fields": (
                    "email",
                    "password1",
                    "password2",
                    "is_staff",
                    "is_superuser",
                ),
            },
        ),
    )
    filter_horizontal = ("groups", "user_permissions")


@admin.register(UserLifeStyle, site=admin_site)
class UserLifeStyleAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "average_sleep_hours",
        "work_type",
        "diet_type",
        "cooking_method",
    )
    search_fields = ("user__email",)


@admin.register(UserMommySymptoms, site=admin_site)
class UserMommySymptomsAdmin(admin.ModelAdmin):
    list_display = ("user", "symptom", "severity", "date_recorded")
    list_filter = ("symptom", "date_recorded")
    search_fields = ("user__email",)


@admin.register(UserBabySymptoms, site=admin_site)
class UserBabySymptomsAdmin(admin.ModelAdmin):
    list_display = ("user", "symptom", "severity", "date_recorded")
    list_filter = ("symptom", "date_recorded")
    search_fields = ("user__email",)


@admin.register(Movement, site=admin_site)
class MovementAdmin(admin.ModelAdmin):
    list_display = ("user", "latitude", "longitude", "timestamp")
    search_fields = ("user__email",)
    list_filter = ("timestamp",)


@admin.register(AirExposureLog, site=admin_site)
class AirExposureLogAdmin(admin.ModelAdmin):
    list_display = ("user", "timestamp", "aqi", "pm25", "pm10", "indoor")
    list_filter = ("indoor", "timestamp")
    search_fields = ("user__email",)


@admin.register(HealthInsightSnapshot, site=admin_site)
class HealthInsightSnapshotAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "source")
    list_filter = ("source", "created_at")
    search_fields = ("user__email",)
