from django.contrib import admin
from .models import User, Movement, DailyExposureSummary


@admin.register(User)
class UserAdmin(admin.ModelAdmin):
    list_display = ("email", "username", "is_staff", "is_active")
    search_fields = ("email", "username")


@admin.register(Movement)
class MovementAdmin(admin.ModelAdmin):
    list_display = ("user", "timestamp", "latitude", "longitude")
    list_filter = ("user",)
    ordering = ("-timestamp",)


@admin.register(DailyExposureSummary)
class DailyExposureSummaryAdmin(admin.ModelAdmin):
    list_display = ("user", "analysis_date", "fetal_risk_score")
    list_filter = ("user", "analysis_date")
    ordering = ("-analysis_date",)
