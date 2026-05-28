from rest_framework import serializers

from .models import AdClick, AdCreative, AdImpression, AdPlacement


class AdCreativeSerializer(serializers.ModelSerializer):
    campaign_id = serializers.IntegerField(source="campaign.id", read_only=True)
    advertiser_name = serializers.CharField(
        source="campaign.advertiser.name", read_only=True
    )
    image_url = serializers.SerializerMethodField()
    placement = serializers.CharField(source="placement.code", read_only=True)

    class Meta:
        model = AdCreative
        fields = [
            "id",
            "campaign_id",
            "advertiser_name",
            "placement",
            "format",
            "title",
            "body",
            "image_url",
            "cta_text",
            "target_url",
            "sponsor_label",
        ]

    def get_image_url(self, obj):
        if not obj.image:
            return ""

        url = obj.image.url
        request = self.context.get("request")
        if request:
            return request.build_absolute_uri(url)
        return url


class AdResponseSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    placement = serializers.CharField()
    creative = AdCreativeSerializer(allow_null=True)


class AdInteractionCreateSerializer(serializers.Serializer):
    request_id = serializers.UUIDField()
    creative_id = serializers.IntegerField(min_value=1)
    placement = serializers.CharField(max_length=64)

    def validate(self, attrs):
        try:
            creative = (
                AdCreative.objects.select_related("campaign", "placement")
                .filter(id=attrs["creative_id"], is_active=True)
                .get()
            )
        except AdCreative.DoesNotExist:
            raise serializers.ValidationError({"creative_id": "Creative not found."})

        if creative.placement.code != attrs["placement"]:
            raise serializers.ValidationError(
                {"placement": "Placement does not match creative."}
            )

        attrs["creative"] = creative
        return attrs

    def create_interaction(self, model_class):
        creative = self.validated_data["creative"]
        request = self.context["request"]
        return model_class.objects.create(
            user=request.user,
            creative=creative,
            campaign=creative.campaign,
            placement=creative.placement,
            request_id=self.validated_data["request_id"],
        )


class AdImpressionSerializer(serializers.ModelSerializer):
    campaign_id = serializers.IntegerField(read_only=True)
    creative_id = serializers.IntegerField(read_only=True)
    placement = serializers.CharField(source="placement.code", read_only=True)

    class Meta:
        model = AdImpression
        fields = [
            "id",
            "request_id",
            "campaign_id",
            "creative_id",
            "placement",
            "shown_at",
        ]


class AdClickSerializer(serializers.ModelSerializer):
    campaign_id = serializers.IntegerField(read_only=True)
    creative_id = serializers.IntegerField(read_only=True)
    placement = serializers.CharField(source="placement.code", read_only=True)

    class Meta:
        model = AdClick
        fields = [
            "id",
            "request_id",
            "campaign_id",
            "creative_id",
            "placement",
            "clicked_at",
        ]


class AdPlacementSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdPlacement
        fields = ["code", "name"]
