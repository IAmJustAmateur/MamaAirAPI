# recommendations/admin.py
from django.contrib import admin
from .models import RecommendationRule


@admin.register(RecommendationRule)
class RecommendationRuleAdmin(admin.ModelAdmin):
    list_display = (
        "rule_id",
        "version",
        "enabled",
        "severity",
        "category",
        "priority",
        "updated_at",
    )
    list_filter = ("enabled", "severity", "category")
    search_fields = ("rule_id", "title", "condition", "message")
    ordering = ("priority", "-updated_at")
