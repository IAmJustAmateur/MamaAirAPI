from django.conf import settings
from django.db import models


class Advertiser(models.Model):
    name = models.CharField(max_length=255)
    contact_email = models.EmailField(blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name


class AdCampaign(models.Model):
    STATUS_DRAFT = "draft"
    STATUS_ACTIVE = "active"
    STATUS_PAUSED = "paused"
    STATUS_ENDED = "ended"

    STATUS_CHOICES = [
        (STATUS_DRAFT, "Draft"),
        (STATUS_ACTIVE, "Active"),
        (STATUS_PAUSED, "Paused"),
        (STATUS_ENDED, "Ended"),
    ]

    advertiser = models.ForeignKey(
        Advertiser, on_delete=models.PROTECT, related_name="campaigns"
    )
    name = models.CharField(max_length=255)
    status = models.CharField(
        max_length=16, choices=STATUS_CHOICES, default=STATUS_DRAFT
    )
    starts_at = models.DateTimeField(null=True, blank=True)
    ends_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-created_at", "name"]
        indexes = [
            models.Index(fields=["status", "starts_at", "ends_at"]),
        ]

    def __str__(self):
        return f"{self.name} ({self.status})"


class AdPlacement(models.Model):
    DAY_ENTRY = "day_entry"
    DIGITAL_TWIN_BABY = "digital_twin_baby"

    code = models.SlugField(max_length=64, unique=True)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["code"]

    def __str__(self):
        return self.name


class AdCreative(models.Model):
    FORMAT_NATIVE_CARD = "native_card"
    FORMAT_BANNER = "banner"

    FORMAT_CHOICES = [
        (FORMAT_NATIVE_CARD, "Native card"),
        (FORMAT_BANNER, "Banner"),
    ]

    campaign = models.ForeignKey(
        AdCampaign, on_delete=models.CASCADE, related_name="creatives"
    )
    placement = models.ForeignKey(
        AdPlacement, on_delete=models.PROTECT, related_name="creatives"
    )
    format = models.CharField(
        max_length=32, choices=FORMAT_CHOICES, default=FORMAT_NATIVE_CARD
    )
    title = models.CharField(max_length=255)
    body = models.TextField(blank=True, default="")
    image = models.ImageField(upload_to="ads/", null=True, blank=True)
    cta_text = models.CharField(max_length=64, blank=True, default="")
    target_url = models.URLField()
    sponsor_label = models.CharField(max_length=64, default="Sponsored")
    locale = models.CharField(max_length=10, blank=True, default="")
    country = models.CharField(max_length=10, blank=True, default="")
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["created_at", "id"]
        indexes = [
            models.Index(fields=["is_active", "locale", "country"]),
            models.Index(fields=["placement", "is_active"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.placement.code})"


class BaseAdInteraction(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    creative = models.ForeignKey(AdCreative, on_delete=models.PROTECT)
    campaign = models.ForeignKey(AdCampaign, on_delete=models.PROTECT)
    placement = models.ForeignKey(AdPlacement, on_delete=models.PROTECT)
    request_id = models.UUIDField()

    class Meta:
        abstract = True
        indexes = [
            models.Index(fields=["user", "request_id"]),
            models.Index(fields=["creative", "request_id"]),
        ]


class AdImpression(BaseAdInteraction):
    shown_at = models.DateTimeField(auto_now_add=True)

    class Meta(BaseAdInteraction.Meta):
        ordering = ["-shown_at"]
        indexes = BaseAdInteraction.Meta.indexes + [
            models.Index(fields=["campaign", "-shown_at"]),
            models.Index(fields=["placement", "-shown_at"]),
        ]

    def __str__(self):
        return f"Impression {self.creative_id} for user {self.user_id}"


class AdClick(BaseAdInteraction):
    clicked_at = models.DateTimeField(auto_now_add=True)

    class Meta(BaseAdInteraction.Meta):
        ordering = ["-clicked_at"]
        indexes = BaseAdInteraction.Meta.indexes + [
            models.Index(fields=["campaign", "-clicked_at"]),
            models.Index(fields=["placement", "-clicked_at"]),
        ]

    def __str__(self):
        return f"Click {self.creative_id} for user {self.user_id}"

# Create your models here.
