# api/views.py
import datetime as dt

from zoneinfo import ZoneInfo
from io import TextIOWrapper
from rest_framework.parsers import MultiPartParser
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError
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
from django.db import transaction
from django.conf import settings

from drf_spectacular.utils import (
    extend_schema,
    OpenApiResponse,
    OpenApiExample,
    OpenApiParameter,
    inline_serializer,
)

from rest_framework import generics, permissions, serializers

from rest_framework.response import Response
from django.utils import timezone
from .models import (
    Movement,
    HealthInsightSnapshot,
    AirExposureLog,
    WeeklyExposure,
    LANGUAGE_CHOICES,
    User,
    UserMommySymptoms,
    MommySymptom,
    BabySymptom,
    UserBabySymptoms,
    Exposure,
)
from .choices_emoji import (
    map_choices_with_emoji,
    COOKING_METHOD_EMOJI,
    DIET_TYPE_EMOJI,
    WORK_TYPE_EMOJI,
)
from .serializers import (
    RegisterSerializer,
    UserProfileSerializer,
    UserLifeStyleSerializer,
    HealthInsightSerializer,
    AirExposureLogSerializer,
    AdviceTemplateSerializer,
    PasswordChangeSerializer,
    LogoutSerializer,
    ErrorResponseSerializer,
    WeeklyExposureSerializer,
    SummaryResponseSerializer,
    SymptomSelectionSerializer,
    ChecklistItemSerializer,
    ExposureHistoryResponseSerializer,
    ExposureHistoryItemSerializer,
)

from .services.services import (
    get_current_advices,
)
from .services.analytics import get_today_journey
from .services.air_exposure import ingest_movements_batch
from .services.air_exposure_daily import recompute_daily_exposure
from .services.helpers import parse_csv_to_records
from .permissions import HasValidRegistrationAPIKey
from .services.aq_logs_services import update_air_exposure_log_with_weather

from api.models import (
    LANGUAGE_CHOICES,
    EXPOSURE_LEVEL_CHOICES,
    UserLifeStyle,
)


from datetime import date as date_cls
from django.utils.dateparse import parse_datetime


def _parse_recorded_at_param(request):
    """
    Извлекает recorded_at из query (?recorded_at=) или body, приводит к aware datetime.
    Если нет — now() в settings.TIME_ZONE.
    """
    raw = request.query_params.get("recorded_at") or request.data.get("recorded_at")
    if not raw:
        return timezone.now()
    dt = parse_datetime(raw)
    if dt is None:
        raise ValidationError(
            {
                "recorded_at": "Invalid datetime. Use ISO-8601, e.g. 2025-09-01T08:30:00+03:00"
            }
        )
    if timezone.is_naive(dt):
        dt = timezone.make_aware(dt, timezone.get_default_timezone())
    return dt


def _target_date_from_request(request):
    """
    Принимает либо ?date=YYYY-MM-DD, либо recorded_at (query/body).
    Приоритет: ?date → recorded_at → today.
    """
    raw_date = request.query_params.get("date")
    if raw_date:
        try:
            return date_cls.fromisoformat(raw_date)
        except ValueError:
            raise ValidationError({"date": "Invalid date. Use YYYY-MM-DD."})
    return _parse_recorded_at_param(request).date()


class ChoiceSchema(serializers.Serializer):
    value = serializers.CharField()
    label = serializers.CharField()


class MetaChoicesResponseSchema(serializers.Serializer):
    languages = ChoiceSchema(many=True)
    races = ChoiceSchema(many=True)
    countries = ChoiceSchema(many=True)
    work_types = ChoiceSchema(many=True)
    diet_types = ChoiceSchema(many=True)
    cooking_methods = ChoiceSchema(many=True)
    exposure_levels = ChoiceSchema(many=True)


# ---- Symptom checklists & selection ----
class ChecklistItemSchema(serializers.Serializer):
    id = serializers.IntegerField(allow_null=True)
    name = serializers.CharField()


class ChecklistResponseSchema(serializers.Serializer):
    symptoms = ChecklistItemSchema(many=True)


class SymptomSelectionRequestSchema(serializers.Serializer):
    symptom_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), allow_empty=True
    )
    recorded_at = serializers.DateTimeField(
        required=False,
        help_text="ISO-8601. If timezone is omitted, interpreted in server TIME_ZONE.",
    )


class SymptomSelectionResponseSchema(serializers.Serializer):
    date = serializers.DateField()
    recorded_at = serializers.DateTimeField(required=False, allow_null=True)
    symptom_ids = serializers.ListField(child=serializers.IntegerField())


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


@extend_schema(
    tags=["Lifestyle"],
    summary="Get current user lifestyle (auto-created if missing)",
    responses={200: UserLifeStyleSerializer},
    methods=["GET"],
)
@extend_schema(
    tags=["Lifestyle"],
    summary="Update current user lifestyle",
    request=UserLifeStyleSerializer,
    responses={200: UserLifeStyleSerializer},
    methods=["PATCH"],
)
class UserLifestyleView(generics.RetrieveUpdateAPIView):
    serializer_class = UserLifeStyleSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        obj, _created = UserLifeStyle.objects.get_or_create(user=self.request.user)
        return obj


# ---------- MOMMY ----------


@extend_schema(
    tags=["Symptoms – Mommy"],
    summary="Mommy symptoms checklist (id + name)",
    responses={200: ChecklistResponseSchema},
    examples=[
        OpenApiExample(
            "Checklist",
            value={
                "symptoms": [
                    {"id": 10, "name": "Headache"},
                    {"id": 12, "name": "Nausea"},
                ]
            },
            response_only=True,
        )
    ],
)
class MommySymptomsChecklistView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user: User = request.user
        names = user.get_mommy_symptoms_for_checking()  # list[str]
        qs = MommySymptom.objects.filter(name__in=names).values("id", "name")
        by_name = {row["name"]: row for row in qs}
        items = [
            {"id": (by_name[n]["id"] if n in by_name else None), "name": n}
            for n in names
        ]
        # сериалайзер для единообразия валидации/формата (не обязательно)
        data = ChecklistItemSerializer(items, many=True).data
        return Response({"symptoms": data})


@extend_schema(
    tags=["Symptoms – Mommy"],
    summary="Get mommy selection for a date",
    parameters=[
        OpenApiParameter(
            name="date",
            location=OpenApiParameter.QUERY,
            required=False,
            description="Calendar date (YYYY-MM-DD). Overrides recorded_at if both provided.",
            type=str,
        ),
        OpenApiParameter(
            name="recorded_at",
            location=OpenApiParameter.QUERY,
            required=False,
            description="ISO-8601 datetime. If timezone omitted, interpreted in server TIME_ZONE.",
            type=str,
        ),
    ],
    responses={200: SymptomSelectionResponseSchema},
    methods=["GET"],
)
@extend_schema(
    tags=["Symptoms – Mommy"],
    summary="Replace mommy selection for recorded_at day",
    request=SymptomSelectionRequestSchema,
    responses={200: SymptomSelectionResponseSchema},
    examples=[
        OpenApiExample(
            "Request",
            value={"symptom_ids": [10, 12], "recorded_at": "2025-09-01T08:30:00+03:00"},
            request_only=True,
        ),
        OpenApiExample(
            "Response",
            value={
                "date": "2025-09-01",
                "recorded_at": "2025-09-01T08:30:00+03:00",
                "symptom_ids": [10, 12],
            },
            response_only=True,
        ),
    ],
    methods=["POST"],
)
class UserMommySymptomsSelectionView(APIView):
    """
    Replace-all за день, определяемый:
    - либо ?date=YYYY-MM-DD,
    - либо recorded_at (из body/query),
    - иначе сегодня в settings.TIME_ZONE.
    """

    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user: User = request.user
        target_date = _target_date_from_request(request)
        ids = list(
            UserMommySymptoms.objects.filter(
                user=user, recorded_at__date=target_date
            ).values_list("symptom_id", flat=True)
        )
        return Response({"date": target_date.isoformat(), "symptom_ids": ids})

    @transaction.atomic
    def post(self, request):
        user: User = request.user
        ser = SymptomSelectionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ids = ser.validated_data["symptom_ids"]
        recorded_at = ser.validated_data["recorded_at"]
        target_date = recorded_at.date()

        # Валидация существования ID
        existing = set(
            MommySymptom.objects.filter(id__in=ids).values_list("id", flat=True)
        )
        missing = sorted(set(ids) - existing)
        if missing:
            raise ValidationError({"symptom_ids": f"Unknown ids: {missing}"})

        # Полная замена набора за день
        UserMommySymptoms.objects.filter(
            user=user, recorded_at__date=target_date
        ).delete()
        bulk = [
            UserMommySymptoms(user=user, symptom_id=sid, recorded_at=recorded_at)
            for sid in existing
        ]
        if bulk:
            UserMommySymptoms.objects.bulk_create(bulk)

        return Response(
            {
                "date": target_date.isoformat(),
                "recorded_at": recorded_at.isoformat(),
                "symptom_ids": sorted(list(existing)),
            }
        )


# ---------- BABY ----------


@extend_schema(
    tags=["Symptoms – Baby"],
    summary="Baby symptoms checklist (id + name)",
    responses={200: ChecklistResponseSchema},
)
class BabySymptomsChecklistView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user: User = request.user
        names = user.get_baby_symptoms_for_checking()  # list[str]
        qs = BabySymptom.objects.filter(name__in=names).values("id", "name")
        by_name = {row["name"]: row for row in qs}
        items = [
            {"id": (by_name[n]["id"] if n in by_name else None), "name": n}
            for n in names
        ]
        data = ChecklistItemSerializer(items, many=True).data
        return Response({"symptoms": data})


@extend_schema(
    tags=["Symptoms – Baby"],
    summary="Get baby selection for a date",
    parameters=[
        OpenApiParameter(
            name="date",
            location=OpenApiParameter.QUERY,
            required=False,
            type=str,
            description="Calendar date (YYYY-MM-DD). Overrides recorded_at if both provided.",
        ),
        OpenApiParameter(
            name="recorded_at",
            location=OpenApiParameter.QUERY,
            required=False,
            type=str,
            description="ISO-8601 datetime. If timezone omitted, interpreted in server TIME_ZONE.",
        ),
    ],
    responses={200: SymptomSelectionResponseSchema},
    methods=["GET"],
)
@extend_schema(
    tags=["Symptoms – Baby"],
    summary="Replace baby selection for recorded_at day",
    request=SymptomSelectionRequestSchema,
    responses={200: SymptomSelectionResponseSchema},
    methods=["POST"],
)
class UserBabySymptomsSelectionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        user: User = request.user
        target_date = _target_date_from_request(request)
        ids = list(
            UserBabySymptoms.objects.filter(
                user=user, recorded_at__date=target_date
            ).values_list("symptom_id", flat=True)
        )
        return Response({"date": target_date.isoformat(), "symptom_ids": ids})

    @transaction.atomic
    def post(self, request):
        user: User = request.user
        ser = SymptomSelectionSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ids = ser.validated_data["symptom_ids"]
        recorded_at = ser.validated_data["recorded_at"]
        target_date = recorded_at.date()

        existing = set(
            BabySymptom.objects.filter(id__in=ids).values_list("id", flat=True)
        )
        missing = sorted(set(ids) - existing)
        if missing:
            raise ValidationError({"symptom_ids": f"Unknown ids: {missing}"})

        UserBabySymptoms.objects.filter(
            user=user, recorded_at__date=target_date
        ).delete()
        bulk = [
            UserBabySymptoms(user=user, symptom_id=sid, recorded_at=recorded_at)
            for sid in existing
        ]
        if bulk:
            UserBabySymptoms.objects.bulk_create(bulk)

        return Response(
            {
                "date": target_date.isoformat(),
                "recorded_at": recorded_at.isoformat(),
                "symptom_ids": sorted(list(existing)),
            }
        )


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

        records, errors = parse_csv_to_records(request.FILES["file"])

        if not records and errors:
            return Response(
                {"status": "error", "imported": 0, "errors": errors}, status=400
            )

        try:
            summary = ingest_movements_batch(user_id=request.user.id, records=records)
        except Exception as e:
            return Response({"status": "error", "detail": str(e)}, status=500)

        tz = ZoneInfo(getattr(settings, "TIME_ZONE", "UTC"))
        affected_dates = {timezone.localtime(rec["ts"], tz).date() for rec in records}

        exposures_recomputed = 0
        exposure_errors = []
        for d in sorted(affected_dates):
            try:
                recompute_daily_exposure(request.user.id, d)
                exposures_recomputed += 1
            except Exception as e:
                # не валим весь ответ, просто фиксируем ошибку расчёта конкретного дня
                exposure_errors.append({"date": d.isoformat(), "error": str(e)})

        payload = {
            "status": "ok",
            **summary,  # imported, air_exposure_created, air_exposure_updated
            "exposures_recomputed": exposures_recomputed,
            "exposure_errors": exposure_errors,
            "errors": errors,  # ошибки парсинга CSV
        }
        return Response(
            payload, status=status.HTTP_201_CREATED if summary["imported"] > 0 else 207
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
        from recommendations.evaluator import get_or_create_fresh_snapshot

        snapshot = get_or_create_fresh_snapshot(
            request.user, fresh_for_hours=6, trigger_event="login"
        )
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
        latest_log = update_air_exposure_log_with_weather(latest_log)

        # current_weather = get_current_weather(latest_log.latitude, latest_log.longitude)
        # latest_log.temperature = current_weather["temp_c"]
        # latest_log.humidity = current_weather["humidity"]
        # latest_log.pressure = current_weather["pressure"]
        # latest_log.uvi = current_weather["uvi"]
        # latest_log.uvi_level = current_weather["uvi_level"]
        # latest_log.save()

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
        latest_log = (
            AirExposureLog.objects.filter(user=request.user)
            .order_by("-timestamp")
            .first()
        )
        # air quality, weather, uv index
        aq_weater_uv = update_air_exposure_log_with_weather(latest_log)

        from recommendations.evaluator import get_or_create_fresh_snapshot

        # recommendations
        snapshot = get_or_create_fresh_snapshot(
            request.user, fresh_for_hours=6, trigger_event="login"
        )
        recommendations = snapshot.recommendations
        #  exposure
        exposures = Exposure.objects.filter(user=request.user).order_by("-timestamp")[
            :2
        ]
        exposure = exposures[0] if exposures else None
        risk_delta = (
            exposure.exposure_level - exposures[1].exposure_level
            if exposures and len(exposures) > 1
            else None
        )

        user: User = request.user
        data = {
            # "air_quality": get_air_quality_summary(user),
            # "weather": get_weather_summary(user),
            # "UV": get_uv_index(user),
            "aq_weather_uv": aq_weater_uv,
            # "mom_exposure": get_exposure_summary(user, target="mom"),
            # "baby_exposure": get_exposure_summary(user, target="baby"),
            "risks_delta": {"mom": risk_delta, "baby": risk_delta},
            "mom_exposure": exposure,
            "baby_exposure": exposure,
            # "risks_delta": get_risks_delta(user),
            "recommendations": recommendations,
            # "recommendations": get_current_recommendations(user),
            "today_journey": get_today_journey(user),
            "mama_air_speaks": user.mama_air_speaks(),
        }
        serializer = SummaryResponseSerializer(data)
        return Response(serializer.data)


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


@extend_schema(
    tags=["Meta"],
    summary="Meta choices for dropdowns",
    responses={200: MetaChoicesResponseSchema},
    examples=[
        OpenApiExample(
            "Example",
            value={
                "languages": [{"value": "en", "label": "English"}],
                "races": [{"value": "caucasian", "label": "Caucasian"}],
                "countries": [{"value": "nigeria", "label": "Nigeria"}],
                "work_types": [{"value": "Desk", "label": "Desk"}],
                "diet_types": [{"value": "carnivore", "label": "Carnivore"}],
                "cooking_methods": [{"value": "gas", "label": "Gas"}],
                "exposure_levels": [{"value": "Clean", "label": "Clean"}],
            },
            response_only=True,
        )
    ],
)
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
            "work_types": map_choices_with_emoji(
                UserLifeStyle.WORK_TYPE_CHOICES, WORK_TYPE_EMOJI
            ),
            "diet_types": map_choices_with_emoji(
                UserLifeStyle.DIET_TYPE_CHOICES, DIET_TYPE_EMOJI
            ),
            "cooking_methods": map_choices_with_emoji(
                UserLifeStyle.COOKING_METHOD_CHOICES, COOKING_METHOD_EMOJI
            ),
            "exposure_levels": _map_choices(EXPOSURE_LEVEL_CHOICES),
        }
        return Response(data)


@extend_schema(
    tags=["Exposure"],
    summary="Exposure history (integrated score)",
    description=(
        "Returns the user's integrated exposure score history for the last N calendar days "
        "(default 7, up to 90). Missing days are simply absent from the list."
    ),
    parameters=[
        OpenApiParameter(
            name="days",
            description="Number of calendar days to return (default 7, min 1, max 90).",
            required=False,
            type=int,
            location=OpenApiParameter.QUERY,
        ),
    ],
    responses=ExposureHistoryResponseSerializer,
)
class ExposureHistoryView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request, *args, **kwargs):
        # parse & clamp days
        try:
            days = int(request.query_params.get("days", 7))
        except (TypeError, ValueError):
            days = 7
        days = max(1, min(days, 90))

        end_date = timezone.localdate()
        start_date = end_date - dt.timedelta(days=days - 1)

        qs = Exposure.objects.filter(
            user=request.user,
            timestamp__gte=start_date,
            timestamp__lte=end_date,
        ).order_by("timestamp")

        items = ExposureHistoryItemSerializer(qs, many=True).data
        payload = {
            "start_date": start_date,
            "end_date": end_date,
            "days_requested": days,
            "items": items,
        }
        return Response(payload)
