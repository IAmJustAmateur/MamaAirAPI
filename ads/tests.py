import uuid
from datetime import timedelta

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase

from .models import (
    AdCampaign,
    AdClick,
    AdCreative,
    AdImpression,
    AdPlacement,
    Advertiser,
)


class AdsApiTests(APITestCase):
    @classmethod
    def setUpTestData(cls):
        User = get_user_model()
        cls.user = User.objects.create_user(
            email="ads@example.com",
            password="pass12345",
            language="en",
            country="GH",
        )
        cls.advertiser = Advertiser.objects.create(name="CleanAir Partner")
        cls.placement, _ = AdPlacement.objects.get_or_create(
            code=AdPlacement.DAY_ENTRY,
            defaults={"name": "Day entry"},
        )
        cls.campaign = AdCampaign.objects.create(
            advertiser=cls.advertiser,
            name="Day Entry Campaign",
            status=AdCampaign.STATUS_ACTIVE,
            starts_at=timezone.now() - timedelta(days=1),
            ends_at=timezone.now() + timedelta(days=1),
        )
        cls.creative = AdCreative.objects.create(
            campaign=cls.campaign,
            placement=cls.placement,
            format=AdCreative.FORMAT_NATIVE_CARD,
            title="Cleaner air at home",
            body="Special offer for expecting mothers.",
            cta_text="View offer",
            target_url="https://example.com/offer",
            sponsor_label="Sponsored",
            locale="en",
            country="GH",
        )

    def setUp(self):
        self.client.force_authenticate(self.user)

    def test_get_ad_returns_active_creative_for_placement(self):
        resp = self.client.get(reverse("ads"), {"placement": AdPlacement.DAY_ENTRY})

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["placement"] == AdPlacement.DAY_ENTRY
        assert resp.data["request_id"]
        assert resp.data["creative"]["id"] == self.creative.id
        assert resp.data["creative"]["campaign_id"] == self.campaign.id
        assert resp.data["creative"]["advertiser_name"] == self.advertiser.name
        assert resp.data["creative"]["format"] == AdCreative.FORMAT_NATIVE_CARD

    def test_get_ad_returns_null_when_no_creative_matches(self):
        resp = self.client.get(
            reverse("ads"), {"placement": AdPlacement.DIGITAL_TWIN_BABY}
        )

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["placement"] == AdPlacement.DIGITAL_TWIN_BABY
        assert resp.data["creative"] is None

    def test_get_ad_requires_placement(self):
        resp = self.client.get(reverse("ads"))

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert resp.data["detail"] == "placement query param is required."

    def test_inactive_campaign_is_not_selected(self):
        self.campaign.status = AdCampaign.STATUS_PAUSED
        self.campaign.save(update_fields=["status"])

        resp = self.client.get(reverse("ads"), {"placement": AdPlacement.DAY_ENTRY})

        assert resp.status_code == status.HTTP_200_OK
        assert resp.data["creative"] is None

    def test_records_impression(self):
        request_id = uuid.uuid4()

        resp = self.client.post(
            reverse("ads-impression"),
            {
                "request_id": str(request_id),
                "creative_id": self.creative.id,
                "placement": AdPlacement.DAY_ENTRY,
            },
            format="json",
        )

        assert resp.status_code == status.HTTP_201_CREATED
        impression = AdImpression.objects.get()
        assert impression.user == self.user
        assert impression.creative == self.creative
        assert impression.campaign == self.campaign
        assert impression.placement == self.placement
        assert impression.request_id == request_id

    def test_records_click(self):
        request_id = uuid.uuid4()

        resp = self.client.post(
            reverse("ads-click"),
            {
                "request_id": str(request_id),
                "creative_id": self.creative.id,
                "placement": AdPlacement.DAY_ENTRY,
            },
            format="json",
        )

        assert resp.status_code == status.HTTP_201_CREATED
        click = AdClick.objects.get()
        assert click.user == self.user
        assert click.creative == self.creative
        assert click.campaign == self.campaign
        assert click.placement == self.placement
        assert click.request_id == request_id

    def test_interaction_rejects_wrong_placement(self):
        AdPlacement.objects.get_or_create(
            code=AdPlacement.DIGITAL_TWIN_BABY,
            defaults={"name": "Digital twin baby"},
        )

        resp = self.client.post(
            reverse("ads-click"),
            {
                "request_id": str(uuid.uuid4()),
                "creative_id": self.creative.id,
                "placement": AdPlacement.DIGITAL_TWIN_BABY,
            },
            format="json",
        )

        assert resp.status_code == status.HTTP_400_BAD_REQUEST
        assert "placement" in resp.data

    def test_endpoints_require_auth(self):
        self.client.force_authenticate(user=None)

        resp = self.client.get(reverse("ads"), {"placement": AdPlacement.DAY_ENTRY})

        assert resp.status_code in (
            status.HTTP_401_UNAUTHORIZED,
            status.HTTP_403_FORBIDDEN,
        )
