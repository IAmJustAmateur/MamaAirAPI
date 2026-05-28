from django.db.models import Q
from django.utils import timezone

from .models import AdCampaign, AdCreative, AdPlacement


def select_ad_creative(user, placement_code):
    """
    Temporary targeting stub.

    Later this function can become the real targeting engine without changing
    the public API contract.
    """
    now = timezone.now()

    placement = AdPlacement.objects.filter(code=placement_code, is_active=True).first()
    if not placement:
        return None

    campaigns = AdCampaign.objects.filter(
        advertiser__is_active=True,
        status=AdCampaign.STATUS_ACTIVE,
    ).filter(Q(starts_at__isnull=True) | Q(starts_at__lte=now))
    campaigns = campaigns.filter(Q(ends_at__isnull=True) | Q(ends_at__gte=now))

    creatives = (
        AdCreative.objects.select_related("campaign", "campaign__advertiser", "placement")
        .filter(
            campaign__in=campaigns,
            placement=placement,
            is_active=True,
        )
        .filter(Q(locale="") | Q(locale=getattr(user, "language", "")))
        .filter(Q(country="") | Q(country=getattr(user, "country", "")))
        .order_by("created_at", "id")
    )

    return creatives.first()
