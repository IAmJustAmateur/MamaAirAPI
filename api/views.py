# api/views.py

import csv
from io import TextIOWrapper
from rest_framework.parsers import MultiPartParser
from rest_framework import status
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView
from rest_framework.response import Response


from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample

from rest_framework import generics, permissions

from rest_framework.response import Response
from django.utils import timezone
from .models import (
    Movement,
    HealthInsightSnapshot,
    AirExposureLog,
)
from .serializers import (
    UserProfileSerializer,
    UserLifeStyleSerializer,
    UserMommySymptomsSerializer,
    UserBabySymptomsSerializer,
    HealthInsightSerializer,
    AirExposureLogSerializer,
)


class UserProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user


class UserLifestyleView(generics.RetrieveUpdateAPIView):
    serializer_class = UserLifeStyleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user.lifestyle


class UserMommySymptomsView(generics.ListCreateAPIView):
    serializer_class = UserMommySymptomsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return self.request.user.mommy_symptoms.all()

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


class UserBabySymptomsView(generics.ListCreateAPIView):
    serializer_class = UserBabySymptomsSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_queryset(self):
        return self.request.user.symptoms.all()

    def perform_create(self, serializer):
        serializer.save(user=self.request.user)


@extend_schema(
    summary="Upload user movements via CSV",
    description=(
        "Allows uploading a CSV file with user location data (latitude, longitude, timestamp). "
        "Each row in the file is parsed and stored as a Movement object associated with the authenticated user. "
        "The endpoint accepts a `multipart/form-data` request with a `file` field."
    ),
    request={
        "multipart/form-data": {
            "type": "object",
            "properties": {
                "file": {
                    "type": "string",
                    "format": "binary",
                    "description": "CSV file with columns: latitude, longitude, timestamp",
                }
            },
            "required": ["file"],
        }
    },
    responses={
        201: OpenApiResponse(
            description="Movements uploaded successfully.",
            examples=[
                OpenApiExample(
                    "Success Example",
                    value={"status": "ok", "imported": 42, "errors": []},
                    response_only=True,
                )
            ],
        ),
        400: OpenApiResponse(
            description="Invalid or missing CSV data.",
            examples=[
                OpenApiExample(
                    "Missing file",
                    value={"error": "No file provided."},
                    response_only=True,
                ),
                OpenApiExample(
                    "Row error",
                    value={
                        "status": "ok",
                        "imported": 10,
                        "errors": [{"row": 11, "error": "Invalid timestamp format"}],
                    },
                    response_only=True,
                ),
            ],
        ),
    },
)
class MovementCSVUploadView(APIView):
    parser_classes = [MultiPartParser]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        if "file" not in request.FILES:
            return Response({"error": "No file provided."}, status=400)

        file = request.FILES["file"]
        decoded_file = TextIOWrapper(file, encoding="utf-8")
        reader = csv.DictReader(decoded_file)

        count = 0
        errors = []

        for i, row in enumerate(reader, start=1):
            try:
                movement = Movement(
                    user=request.user,
                    latitude=float(row["latitude"]),
                    longitude=float(row["longitude"]),
                    timestamp=row["timestamp"],
                )
                movement.save()
                count += 1
            except Exception as e:
                errors.append({"row": i, "error": str(e)})

        return Response(
            {"status": "ok", "imported": count, "errors": errors},
            status=status.HTTP_201_CREATED if count > 0 else 400,
        )


@extend_schema(
    summary="Get health risks and recommendations",
    description=(
        "Returns the latest generated health insight snapshot for the authenticated user. "
        "Includes risk levels for both the mother and the baby, as well as personalized recommendations. "
        "This endpoint is typically used to populate the user's dashboard."
    ),
    responses={
        200: HealthInsightSerializer,
        204: OpenApiResponse(
            description="No health insight data available for the user."
        ),
    },
)
class HealthInsightView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        snapshot = (
            HealthInsightSnapshot.objects.filter(user=request.user)
            .order_by("-created_at")
            .first()
        )
        if not snapshot:
            return Response({"detail": "No health insights available."}, status=204)
        return Response(HealthInsightSerializer(snapshot).data)


@extend_schema(
    summary="Get current air quality and weather data",
    description=(
        "Returns the most recent air quality and weather data "
        "based on the user's recorded exposure logs."
    ),
    responses={
        200: AirExposureLogSerializer,
        204: OpenApiResponse(description="No air exposure data available."),
    },
)
class EnvironmentView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        latest_log = (
            AirExposureLog.objects.filter(user=request.user)
            .order_by("-timestamp")
            .first()
        )
        if not latest_log:
            return Response({"detail": "No air exposure data found."}, status=204)
        return Response(AirExposureLogSerializer(latest_log).data)
