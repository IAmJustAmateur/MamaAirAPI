import uuid

from drf_spectacular.utils import OpenApiParameter, extend_schema
from rest_framework import permissions, status
from rest_framework.response import Response
from rest_framework.views import APIView

from .models import AdClick, AdImpression
from .serializers import (
    AdClickSerializer,
    AdCreativeSerializer,
    AdImpressionSerializer,
    AdInteractionCreateSerializer,
    AdResponseSerializer,
)
from .services import select_ad_creative


class AdView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Ads"],
        summary="Get ad creative for placement",
        parameters=[
            OpenApiParameter(
                name="placement",
                required=True,
                type=str,
                location=OpenApiParameter.QUERY,
                description="Ad placement code, e.g. day_entry or digital_twin_baby.",
            )
        ],
        responses={200: AdResponseSerializer},
    )
    def get(self, request):
        placement = request.query_params.get("placement")
        if not placement:
            return Response(
                {"detail": "placement query param is required."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        creative = select_ad_creative(request.user, placement)
        data = {
            "request_id": uuid.uuid4(),
            "placement": placement,
            "creative": (
                AdCreativeSerializer(creative, context={"request": request}).data
                if creative
                else None
            ),
        }
        return Response(data)


class AdImpressionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Ads"],
        summary="Record ad impression",
        request=AdInteractionCreateSerializer,
        responses={201: AdImpressionSerializer},
    )
    def post(self, request):
        serializer = AdInteractionCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        impression = serializer.create_interaction(AdImpression)
        return Response(AdImpressionSerializer(impression).data, status=201)


class AdClickView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Ads"],
        summary="Record ad click",
        request=AdInteractionCreateSerializer,
        responses={201: AdClickSerializer},
    )
    def post(self, request):
        serializer = AdInteractionCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        click = serializer.create_interaction(AdClick)
        return Response(AdClickSerializer(click).data, status=201)
