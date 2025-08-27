# api/views.py

import csv
from io import TextIOWrapper
from rest_framework.parsers import MultiPartParser
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from drf_spectacular.types import OpenApiTypes

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.token_blacklist.models import (
    BlacklistedToken,
    OutstandingToken,
)

from django.utils.translation import gettext as _
from django.contrib.auth import get_user_model

from django.contrib.auth import authenticate, login

from django.shortcuts import render, redirect

from drf_spectacular.utils import (
    extend_schema,
    OpenApiResponse,
    OpenApiExample,
    OpenApiParameter,
)

from rest_framework import generics, permissions

from rest_framework.response import Response
from django.utils import timezone
from .models import (
    Movement,
    HealthInsightSnapshot,
    AirExposureLog,
    WeeklyExposure,
    LANGUAGE_CHOICES,
    User,
)
from .serializers import (
    RegisterSerializer,
    UserProfileSerializer,
    UserLifeStyleSerializer,
    UserMommySymptomsSerializer,
    UserBabySymptomsSerializer,
    HealthInsightSerializer,
    AirExposureLogSerializer,
    AdviceTemplateSerializer,
    PasswordChangeSerializer,
    LogoutSerializer,
    ErrorResponseSerializer,
    WeeklyExposureSerializer,
    SummaryResponseSerializer,
)

from .services import (
    get_current_advices,
    get_air_quality_summary,
    get_weather_summary,
    get_uv_index,
    get_exposure_summary,
    get_risks_delta,
    get_current_recommendations,
    get_today_journey,
)
from .permissions import HasValidRegistrationAPIKey

from api.models import (
    LANGUAGE_CHOICES,
    EXPOSURE_LEVEL_CHOICES,
    UserLifeStyle,
)


@extend_schema(
    summary="Register a new user account",
    description="Registers a new user. Requires a valid API key in the `X-API-Key` header.",
    request=RegisterSerializer,
    responses={
        201: OpenApiExample(
            name="User created",
            value={"message": "User created successfully"},
            response_only=True,
        ),
        403: OpenApiExample(
            name="Invalid API key",
            value={"detail": "Invalid or missing API key."},
            response_only=True,
        ),
    },
    parameters=[
        OpenApiParameter(
            name="X-API-Key",
            type=str,
            location=OpenApiParameter.HEADER,
            required=True,
            description="API key for registration",
        )
    ],
)
class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = [AllowAny, HasValidRegistrationAPIKey]

    def create(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        return Response(
            {"message": "User created successfully"}, status=status.HTTP_201_CREATED
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
        user: User = self.request.user
        symptoms = user.get_mommy_symptoms_for_checking()
        return symptoms

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


class CurrentAdviceView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AdviceTemplateSerializer

    def get(self, request):
        week = request.query_params.get("week")

        try:
            pregnancy_week = int(week)
        except (TypeError, ValueError):
            pregnancy_week = None

        advices = get_current_advices(request.user, pregnancy_week)
        serializer = AdviceTemplateSerializer(advices, many=True)
        return Response(serializer.data)


@extend_schema(
    summary="Log out user and blacklist refresh token",
    description="Logs out the authenticated user by blacklisting the provided refresh token.",
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "refresh": {"type": "string", "example": "your_refresh_token_here"}
            },
            "required": ["refresh"],
        }
    },
    responses={
        205: OpenApiExample(
            "Successfully logged out",
            value={"detail": "Successfully logged out"},
            response_only=True,
        ),
        400: OpenApiExample(
            "Invalid token",
            value={"error": "Invalid refresh token"},
            response_only=True,
        ),
    },
)
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LogoutSerializer

    @extend_schema(
        request=LogoutSerializer,
        responses={
            205: OpenApiTypes.NONE,
            400: ErrorResponseSerializer,
        },
    )
    def post(self, request):
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            refresh_token = serializer.validated_data["refresh"]
            token = RefreshToken(refresh_token)
            token.blacklist()

            return Response(
                {"detail": "Successfully logged out."},
                status=status.HTTP_205_RESET_CONTENT,
            )
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


# views.py


@extend_schema(
    summary="Delete current user account",
    description="Deletes the authenticated user's account from the system. This action is irreversible.",
    responses={
        204: OpenApiExample(
            "Account deleted",
            value={"detail": "Account deleted successfully"},
            response_only=True,
        )
    },
)
class DeleteAccountView(APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request):
        user = request.user
        user.delete()
        return Response(
            {"detail": "Account deleted successfully"},
            status=status.HTTP_204_NO_CONTENT,
        )


@extend_schema(
    summary="Change user password",
    description="Allows an authenticated user to change their password by providing the current and new password.",
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "old_password": {"type": "string", "example": "testpass123"},
                "new_password": {"type": "string", "example": "newpass456"},
            },
            "required": ["old_password", "new_password"],
        }
    },
    responses={
        200: OpenApiExample(
            "Password changed",
            value={"detail": "Password changed successfully"},
            response_only=True,
        ),
        400: OpenApiExample(
            "Wrong old password",
            value={"old_password": "Wrong password."},
            response_only=True,
        ),
    },
)
class PasswordChangeView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = PasswordChangeSerializer

    def get_object(self):
        return self.request.user

    def post(self, request):
        user = request.user
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        if not user.check_password(serializer.validated_data["old_password"]):
            return Response(
                {"old_password": "Wrong password."}, status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(serializer.validated_data["new_password"])
        user.save()
        return Response(
            {"detail": "Password changed successfully"}, status=status.HTTP_200_OK
        )


@extend_schema(
    summary="Get exposure levels per pregnancy week",
    description="Returns weekly air quality exposure levels for the current user.",
    responses={
        200: OpenApiResponse(
            response=WeeklyExposureSerializer(many=True),
            description="A dictionary where each key is the pregnancy week and value is exposure level.",
            examples=[
                OpenApiExample(
                    "Example output",
                    value={
                        "12": {"level": "moderate"},
                        "13": {"level": "unhealthy"},
                        "14": {"level": "clean"},
                    },
                    response_only=True,
                )
            ],
        )
    },
)
class WeeklyExposureView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        exposures = WeeklyExposure.objects.filter(user=request.user)
        result = {
            item.pregnancy_week: {"level": item.exposure_level} for item in exposures
        }
        return Response(result)


@extend_schema(
    summary="Get integrated summary",
    description="Returns air quality, weather, exposure history, risk change and recommendations for mother and baby.",
    responses={200: SummaryResponseSerializer},
)
class SummaryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        user = request.user
        data = {
            "air_quality": get_air_quality_summary(user),
            "weather": get_weather_summary(user),
            "UV": get_uv_index(user),
            "mom_exposure": get_exposure_summary(user, target="mom"),
            "baby_exposure": get_exposure_summary(user, target="baby"),
            "risks_delta": get_risks_delta(user),
            "recommendations": get_current_recommendations(user),
            "today_journey": get_today_journey(user),
        }
        return Response(data)


@extend_schema(
    summary="Set preferred language for current user",
    description=(
        "Allows the user to update their preferred interface language. "
        "This language will be used by the backend to localize responses like advice, messages, etc."
    ),
    request={
        "application/json": {
            "type": "object",
            "properties": {
                "language": {
                    "type": "string",
                    "enum": [code for code, _ in LANGUAGE_CHOICES],
                    "description": "Language code, e.g., 'en', 'fr', 'sw', 'ig'",
                }
            },
            "required": ["language"],
        }
    },
    responses={
        200: OpenApiExample(
            "Success",
            value={"message": "Language updated", "language": "fr"},
            response_only=True,
        ),
        400: OpenApiExample(
            "Invalid language",
            value={"error": "Invalid language code"},
            response_only=True,
        ),
    },
)
class SetLanguageView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request):
        lang = request.data.get("language")

        if lang not in dict(LANGUAGE_CHOICES):
            return Response(
                {"error": "Invalid language code"}, status=status.HTTP_400_BAD_REQUEST
            )

        request.user.language = lang
        request.user.save()

        return Response({"message": "Language updated", "language": lang})


from django.contrib.auth import authenticate, login
from django.http import HttpResponse


def test_login(request):
    user = authenticate(request, username="admin@example.com", password="admin")
    if user is not None:
        login(request, user)
        return HttpResponse("✅ Logged in. Check your cookies.")
    return HttpResponse("❌ Login failed.")


def login_view(request):
    if request.method == "POST":
        email = request.POST.get("email")
        password = request.POST.get("password")
        user = authenticate(request, username=email, password=password)
        if user is not None:
            login(request, user)
            return HttpResponse("Logged in successfully")
        else:
            return HttpResponse("Invalid credentials", status=401)
    return render(request, "api/custom_login.html")  # Render a simple login form


def _map_choices(choices):
    """[(value, label), ...] -> [{'value': v, 'label': str(label)}, ...]"""
    return [{"value": v, "label": str(lbl)} for v, lbl in choices]


class MetaChoicesView(APIView):
    authentication_classes = []  # публично (можно включить JWT, если нужно)
    permission_classes = []

    def get(self, request):
        # Можно также доставать choices через поля модели, чтобы не дублировать:
        # user_model = get_user_model()
        # race_choices = user_model._meta.get_field("race").choices
        # но ниже — напрямую из констант (эквивалентно и быстрее)
        data = {
            "languages": _map_choices(LANGUAGE_CHOICES),
            "races": _map_choices(User.RACE_CHOICES),
            "countries": _map_choices(User.COUNTRY_CHOICES),
            "work_types": _map_choices(UserLifeStyle.WORK_TYPE_CHOICES),
            "diet_types": _map_choices(UserLifeStyle.DIET_TYPE_CHOICES),
            "cooking_methods": _map_choices(UserLifeStyle.COOKING_METHOD_CHOICES),
            "exposure_levels": _map_choices(EXPOSURE_LEVEL_CHOICES),
        }
        return Response(data)
