from django import forms
from django.contrib import admin

# from django.contrib.admin import AdminSite
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
    MommySymptom,
    BabySymptom,
    RiskDefinition,
    UserRiskFactor,
    LifestyleRiskFactor,
    RiskDefinitionBabySymptom,
    RiskDefinitionMommySymptom,
)
from django.contrib.auth import authenticate, login


# 👤 Форма логина по email для админки
# class EmailAdminAuthenticationForm(AuthenticationForm):
#     username = forms.EmailField(
#         label=_("Email"), widget=forms.TextInput(attrs={"autofocus": True})
#     )

#     def confirm_login_allowed(self, user):
#         login(self.request, user)


# 👤 Кастомный сайт админки с формой логина по email
# class CustomAdminSite(AdminSite):
#     login_form = EmailAdminAuthenticationForm


# admin_site = CustomAdminSite(name="custom_admin")


# 👤 UserAdmin без username


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


admin.site.register(User, UserAdmin)


class UserLifeStyleAdmin(admin.ModelAdmin):
    list_display = (
        "user",
        "average_sleep_hours",
        "work_type",
        "diet_type",
        "cooking_method",
    )
    search_fields = ("user__email",)


admin.site.register(UserLifeStyle, UserLifeStyleAdmin)


class UserMommySymptomsAdmin(admin.ModelAdmin):
    list_display = ("user", "symptom", "date_recorded")
    list_filter = ("symptom", "date_recorded")
    search_fields = ("user__email",)


admin.site.register(UserMommySymptoms, UserMommySymptomsAdmin)


class UserBabySymptomsAdmin(admin.ModelAdmin):
    list_display = ("user", "symptom", "date_recorded")
    list_filter = ("symptom", "date_recorded")
    search_fields = ("user__email",)


admin.site.register(UserBabySymptoms, UserBabySymptomsAdmin)


class MovementAdmin(admin.ModelAdmin):
    list_display = ("user", "latitude", "longitude", "timestamp")
    search_fields = ("user__email",)
    list_filter = ("timestamp",)


admin.site.register(Movement, MovementAdmin)


class AirExposureLogAdmin(admin.ModelAdmin):
    list_display = ("user", "timestamp", "aqi", "pm25", "pm10", "indoor")
    list_filter = ("indoor", "timestamp")
    search_fields = ("user__email",)


admin.site.register(AirExposureLog, AirExposureLogAdmin)


class HealthInsightSnapshotAdmin(admin.ModelAdmin):
    list_display = ("user", "created_at", "source")
    list_filter = ("source", "created_at")
    search_fields = ("user__email",)


admin.site.register(HealthInsightSnapshot, HealthInsightSnapshotAdmin)


admin.site.register(MommySymptom)
admin.site.register(BabySymptom)


@admin.register(RiskDefinition)
class RiskDefinitionAdmin(admin.ModelAdmin):
    list_display = ("name", "is_enabled")
    search_fields = ("name",)


@admin.register(UserRiskFactor)
class UserRiskFactorAdmin(admin.ModelAdmin):
    list_display = ("risk", "condition", "multiplier")
    search_fields = ("risk__name", "condition")
    list_filter = ("risk", "condition", "multiplier")


@admin.register(RiskDefinitionMommySymptom)
class RiskDefinitionMommySymptomAdmin(admin.ModelAdmin):
    list_display = ("risk_definition", "symptom")
    search_fields = ("risk_definition__name", "symptom__name")
    list_filter = ("risk_definition", "symptom")


@admin.register(RiskDefinitionBabySymptom)
class RiskDefinitionBabySymptomAdmin(admin.ModelAdmin):
    list_display = ("risk_definition", "symptom")
    search_fields = ("risk_definition__name", "symptom__name")
    list_filter = ("risk_definition", "symptom")


@admin.register(LifestyleRiskFactor)
class LifestyleRiskFactorAdmin(admin.ModelAdmin):
    list_display = ("risk", "condition", "multiplier")
    search_fields = ("risk__name", "condition")
    list_filter = ("risk", "condition", "multiplier")
