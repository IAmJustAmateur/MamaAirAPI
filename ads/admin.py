from django.contrib import admin

from .models import (
    AdCampaign,
    AdClick,
    AdCreative,
    AdImpression,
    AdPlacement,
    Advertiser,
)


@admin.register(Advertiser)
class AdvertiserAdmin(admin.ModelAdmin):
    list_display = ("id", "name", "contact_email", "is_active", "created_at")
    list_filter = ("is_active",)
    search_fields = ("name", "contact_email")


@admin.register(AdCampaign)
class AdCampaignAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "advertiser",
        "status",
        "starts_at",
        "ends_at",
        "created_at",
    )
    list_filter = ("status", "advertiser")
    search_fields = ("name", "advertiser__name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(AdPlacement)
class AdPlacementAdmin(admin.ModelAdmin):
    list_display = ("id", "code", "name", "is_active")
    list_filter = ("is_active",)
    search_fields = ("code", "name")


@admin.register(AdCreative)
class AdCreativeAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "title",
        "campaign",
        "placement",
        "format",
        "locale",
        "country",
        "is_active",
        "created_at",
    )
    list_filter = ("format", "placement", "is_active", "locale", "country")
    search_fields = ("title", "body", "campaign__name", "campaign__advertiser__name")
    readonly_fields = ("created_at", "updated_at")


@admin.register(AdImpression)
class AdImpressionAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "creative", "placement", "request_id", "shown_at")
    list_filter = ("placement", "shown_at")
    search_fields = ("user__email", "creative__title", "request_id")
    readonly_fields = ("shown_at",)


@admin.register(AdClick)
class AdClickAdmin(admin.ModelAdmin):
    list_display = ("id", "user", "creative", "placement", "request_id", "clicked_at")
    list_filter = ("placement", "clicked_at")
    search_fields = ("user__email", "creative__title", "request_id")
    readonly_fields = ("clicked_at",)
