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
    AQRiskFactor,
    Exposure,
    GuidelineLimit,
    RecommendationCompletion,
    WeeklyExposure,
    DailyExposure,
    Wellbeing,
    UserWellbeingLog,
    DailyCheckin,
    DailyTask,
    UserDailyTaskCompletion,
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
        "current_week_of_pregnancy",
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
                    "avatar",
                    "avatar_url",
                )
            },
        ),
        (
            "Pregnancy",
            {
                "fields": (
                    "race",
                    "country",
                    "is_first_pregnancy",
                    "pregnancy_number",
                    "week_of_pregnancy",
                )
            },
        ),
        (
            "Settings",
            {
                "fields": (
                    "language",
                    "timezone",
                    "tracking_enabled",
                    "notifications_enabled",
                    "notification_window_from",
                    "notification_window_to",
                )
            },
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
        "area",
        "time_spent",
        "time_of_day",
    )
    search_fields = ("user__email",)


admin.site.register(UserLifeStyle, UserLifeStyleAdmin)


class UserMommySymptomsAdmin(admin.ModelAdmin):
    list_display = ("user", "symptom", "recorded_at")
    list_filter = ("symptom", "recorded_at")
    search_fields = ("user__email",)


admin.site.register(UserMommySymptoms, UserMommySymptomsAdmin)


class UserBabySymptomsAdmin(admin.ModelAdmin):
    list_display = ("user", "symptom", "recorded_at")
    list_filter = ("symptom", "recorded_at")
    search_fields = ("user__email",)


admin.site.register(UserBabySymptoms, UserBabySymptomsAdmin)


class MovementAdmin(admin.ModelAdmin):
    list_display = ("user", "latitude", "longitude", "timestamp")
    search_fields = ("user__email",)
    list_filter = ("timestamp", "user")


admin.site.register(Movement, MovementAdmin)


class AirExposureLogAdmin(admin.ModelAdmin):
    list_display = ("user", "timestamp", "aqi", "pm25", "pm10", "indoor")
    list_filter = ("indoor", "timestamp")
    search_fields = ("user__email",)


admin.site.register(AirExposureLog, AirExposureLogAdmin)


class WeeklyExposureAdmin(admin.ModelAdmin):
    list_display = ("user", "pregnancy_week", "exposure_level", "recorded_at")
    list_filter = ("user", "pregnancy_week", "recorded_at", "exposure_level")
    search_fields = ("user__email",)


admin.site.register(WeeklyExposure, WeeklyExposureAdmin)


class DailyExposureAdmin(admin.ModelAdmin):
    list_display = ("user", "date", "exposure_level", "recorded_at")
    list_filter = ("user", "date", "recorded_at", "exposure_level")
    search_fields = ("user__email",)


admin.site.register(DailyExposure, DailyExposureAdmin)


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
    list_display = ("risk_definition", "symptom", "symptom_class", "source_phrase")
    search_fields = ("risk_definition__name", "symptom__name", "source_phrase")
    list_filter = ("risk_definition", "symptom", "symptom_class")


@admin.register(RiskDefinitionBabySymptom)
class RiskDefinitionBabySymptomAdmin(admin.ModelAdmin):
    list_display = ("risk_definition", "symptom", "symptom_class", "source_phrase")
    search_fields = ("risk_definition__name", "symptom__name", "source_phrase")
    list_filter = ("risk_definition", "symptom", "symptom_class")


@admin.register(LifestyleRiskFactor)
class LifestyleRiskFactorAdmin(admin.ModelAdmin):
    list_display = ("risk", "condition", "multiplier")
    search_fields = ("risk__name", "condition")
    list_filter = ("risk", "condition", "multiplier")


@admin.register(AQRiskFactor)
class AQRiskFactorAdmin(admin.ModelAdmin):
    list_display = ("risk", "condition", "multiplier", "formula")
    search_fields = ("risk__name", "condition", "formula")
    list_filter = ("risk", "condition", "multiplier", "formula")


@admin.register(Exposure)
class ExposureAdmin(admin.ModelAdmin):
    list_display = ("user", "timestamp", "exposure_level")
    list_filter = ("user", "timestamp")
    search_fields = ("user__email",)


@admin.register(GuidelineLimit)
class GuidelineLimitAdmin(admin.ModelAdmin):
    list_display = (
        "pollutant",
        "avg_period",
        "value",
        "unit",
        "source",
        "version",
        "is_active",
        "valid_from",
        "valid_to",
        "updated_at",
    )
    list_filter = ("pollutant", "avg_period", "source", "version", "is_active")
    search_fields = ("pollutant", "version", "source")
    readonly_fields = ("created_at", "updated_at")
    ordering = ("pollutant", "avg_period", "-is_active", "version")

    actions = ["activate_selected", "deactivate_selected"]

    @admin.action(description="Mark selected limits as active")
    def activate_selected(self, request, queryset):
        queryset.update(is_active=True)

    @admin.action(description="Mark selected limits as inactive")
    def deactivate_selected(self, request, queryset):
        queryset.update(is_active=False)


@admin.register(RecommendationCompletion)
class RecommendationCompletionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "snapshot_id",
        "rule_id",
        "rule_version",
        "dimension",
        "status",
        "updated_at",
        "created_at",
    )
    list_filter = ("dimension", "status", "created_at", "updated_at")
    search_fields = ("user__email", "rule_id")
    ordering = ("-updated_at",)
    readonly_fields = ("created_at", "updated_at")

    # Чтобы было проще разбирать конкретный snapshot
    list_select_related = ("user", "snapshot")


@admin.register(Wellbeing)
class WellbeingAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "kind",
        "title",
        "emoji",
        "code",
        "number_value",
        "unit",
        "sort_order",
        "is_active",
    )
    list_filter = ("kind", "is_active", "unit")
    search_fields = ("title", "emoji", "code")
    ordering = ("kind", "sort_order", "title")
    list_editable = ("emoji", "sort_order", "is_active")
    fieldsets = (
        ("Common", {"fields": ("kind", "is_active", "sort_order")}),
        ("Mood/Feeling fields", {"fields": ("title", "emoji", "code")}),
        ("Water goal fields", {"fields": ("number_value", "unit")}),
    )

    def get_readonly_fields(self, request, obj=None):
        # Optional: nothing readonly
        return ()


@admin.register(UserWellbeingLog)
class UserWellbeingLogAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "date", "water_amount", "water_unit")
    list_filter = ("water_unit", "date")
    search_fields = ("user__email", "user__name", "user__username")
    date_hierarchy = "date"
    ordering = ("-date",)
    raw_id_fields = ("user",)
    filter_horizontal = ("moods", "feelings")


@admin.register(DailyCheckin)
class DailyCheckinAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "date", "created_at")
    search_fields = ("user__email", "date")
    date_hierarchy = "date"
    ordering = ("-date",)
    raw_id_fields = ("user",)


@admin.register(DailyTask)
class DailyTaskAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "code",
        "title",
        "category",
        "sort_order",
        "is_active",
        "created_at",
    )
    list_filter = ("category", "is_active")
    search_fields = ("code", "title")
    ordering = ("sort_order", "title")


@admin.register(UserDailyTaskCompletion)
class UserDailyTaskCompletionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "user",
        "task",
        "date",
        "completed",
        "created_at",
        "updated_at",
    )
    list_filter = ("completed", "task", "date")
    search_fields = (
        "user__email",
        "user__name",
        "user__username",
        "task__code",
        "task__title",
    )
    date_hierarchy = "date"
    ordering = ("-date", "task__sort_order", "task__title")
    raw_id_fields = ("user", "task")
