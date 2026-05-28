# api/views.py
import datetime as dt
import logging

from zoneinfo import ZoneInfo

from django.contrib.auth import authenticate, login
from django.http import HttpResponse

from django.shortcuts import render
from django.db import transaction
from django.db.models import Count

from django.conf import settings

# from io import TextIOWrapper
from rest_framework.parsers import JSONParser, MultiPartParser
from rest_framework import status
from rest_framework.permissions import IsAuthenticated, AllowAny
from rest_framework.views import APIView
from rest_framework.exceptions import ValidationError
from drf_spectacular.types import OpenApiTypes

from rest_framework_simplejwt.tokens import RefreshToken

# from rest_framework_simplejwt.token_blacklist.models import (
#     BlacklistedToken,
#     OutstandingToken,
# )
from api.services.guidelines import compute_pollutant_compliance

from rest_framework.response import Response

from drf_spectacular.utils import (
    extend_schema,
    OpenApiParameter,
    OpenApiExample,
    OpenApiResponse,
    inline_serializer,
)
from rest_framework import serializers, generics, permissions


from .serializers import (
    RecommendationCompletionUpsertSerializer,
    RecommendationCompletionSerializer,
)

# from django.utils.translation import gettext as _


from django.utils import timezone
from .models import (
    # Movement,
    AirExposureLog,
    WeeklyExposure,
    LANGUAGE_CHOICES,
    User,
    UserMommySymptoms,
    MommySymptom,
    RiskDefinitionMommySymptom,
    BabySymptom,
    UserBabySymptoms,
    Exposure,
    DailyExposure,
    RecommendationCompletion,
    Wellbeing,
    DailyCheckin,
    DailyTask,
    UserDailyTaskCompletion,
    UserWellbeingLog,
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
    WellbeingItemSerializer,
    DailyCheckinSerializer,
    DailyCheckinCreateSerializer,
    DailyTaskSerializer,
    TaskCompletionDaySerializer,
    TaskCompletionUpsertSerializer,
    UserWellbeingLogSerializer,
    UserWellbeingLogUpsertSerializer,
)

from .services.services import (
    get_current_advices,
)
from .services.analytics import get_today_journey
from .services.air_exposure import ingest_movements_batch
from .services.air_exposure_daily import recompute_daily_exposure
from .services.helpers import parse_csv_to_records, parse_json_to_records
from .permissions import HasValidRegistrationAPIKey
from .services.aq_logs_services import update_air_exposure_log_with_weather

from api.models import (
    EXPOSURE_LEVEL_CHOICES,
    UserLifeStyle,
)


from datetime import date as date_cls
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)


def _task_completion_history(user, start_date, end_date):
    completions = (
        UserDailyTaskCompletion.objects.filter(
            user=user,
            date__gte=start_date,
            date__lte=end_date,
            completed=True,
            task__is_active=True,
        )
        .select_related("task")
        .order_by("date", "task__sort_order", "task__title")
    )
    by_date = {}
    for completion in completions:
        by_date.setdefault(completion.date, []).append(completion.task.code)
    return [
        {"date": completion_date, "tasks": tasks}
        for completion_date, tasks in by_date.items()
    ]


def _payload_keys(payload):
    if hasattr(payload, "keys"):
        return sorted(str(key) for key in payload.keys())
    return []


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


def _date_period_from_request(request):
    raw_date = request.query_params.get("date")
    raw_start_date = request.query_params.get("start_date")
    raw_end_date = request.query_params.get("end_date")

    if raw_date:
        try:
            target_date = date_cls.fromisoformat(raw_date)
        except ValueError:
            raise ValidationError({"date": "Invalid date. Use YYYY-MM-DD."})
        return target_date, target_date

    if raw_start_date or raw_end_date:
        if not raw_start_date or not raw_end_date:
            raise ValidationError(
                {
                    "detail": "start_date and end_date query params must be provided together (YYYY-MM-DD)."
                }
            )
        try:
            start_date = date_cls.fromisoformat(raw_start_date)
            end_date = date_cls.fromisoformat(raw_end_date)
        except ValueError:
            raise ValidationError(
                {
                    "detail": "Invalid date range. Use YYYY-MM-DD for start_date and end_date."
                }
            )
        if start_date > end_date:
            raise ValidationError(
                {"detail": "start_date must be less than or equal to end_date."}
            )
        return start_date, end_date

    today = timezone.localdate()
    week_start = today - dt.timedelta(days=today.weekday())
    return week_start, today


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


class MommySymptomStatisticItemSchema(serializers.Serializer):
    symptom_name = serializers.CharField()
    symptom_id = serializers.IntegerField()
    quantity = serializers.IntegerField()
    risk_name = serializers.CharField()
    risk_id = serializers.IntegerField()


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
        logger.info(
            "RegisterView POST, payload_keys=%s, has_api_key=%s",
            _payload_keys(request.data),
            bool(request.headers.get("X-API-Key")),
        )
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_create(serializer)
        logger.info("RegisterView created user_id=%s", serializer.instance.id)
        return Response(
            {"message": "User created successfully"}, status=status.HTTP_201_CREATED
        )


class UserProfileView(generics.RetrieveUpdateAPIView):
    serializer_class = UserProfileSerializer
    permission_classes = [permissions.IsAuthenticated]

    def get_object(self):
        return self.request.user

    def retrieve(self, request, *args, **kwargs):
        logger.info("UserProfileView GET, user=%s", request.user)
        return super().retrieve(request, *args, **kwargs)

    def update(self, request, *args, **kwargs):
        partial = kwargs.pop("partial", False)
        instance = self.get_object()
        serializer = self.get_serializer(instance, data=request.data, partial=partial)
        serializer.is_valid(raise_exception=True)

        user = serializer.save()

        if "week_of_pregnancy" in serializer.validated_data:
            user.set_pregnancy_start_date()
            user.save(update_fields=["pregnancy_start_date"])

        return Response(self.get_serializer(user).data)

    def partial_update(self, request, *args, **kwargs):
        logger.info(
            "UserProfileView PATCH, user=%s, payload_keys=%s",
            request.user,
            _payload_keys(request.data),
        )
        response = super().partial_update(request, *args, **kwargs)
        logger.info("UserProfileView PATCH completed, user=%s", request.user)
        return response

    # def perform_update(self, serializer):
    #     user = serializer.save()

    #     week_of_pregnancy = serializer.validated_data.get("week_of_pregnancy")
    #     if week_of_pregnancy is not None:
    #         user.set_pregnancy_start_date(week_of_pregnancy)
    #         user.save(update_fields=["pregnancy_start_date"])


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

    def retrieve(self, request, *args, **kwargs):
        logger.info("UserLifestyleView GET, user=%s", request.user)
        return super().retrieve(request, *args, **kwargs)

    def partial_update(self, request, *args, **kwargs):
        logger.info(
            "UserLifestyleView PATCH, user=%s, payload_keys=%s",
            request.user,
            _payload_keys(request.data),
        )
        response = super().partial_update(request, *args, **kwargs)
        logger.info("UserLifestyleView PATCH completed, user=%s", request.user)
        return response


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
        """Mommy symptoms checklist (id + name)"""
        logger.info("MommySymptomsChecklistView GET, user=%s", request.user)
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
        logger.info("UserMommySymptomsSelectionView GET, user=%s", request.user)
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
        logger.info(
            "UserMommySymptomsSelectionView POST, user=%s, data=%s",
            request.user,
            request.data,
        )
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


@extend_schema(
    tags=["Symptoms Statistics – Mommy"],
    summary="Get mommy symptoms statistics by risk for a period",
    parameters=[
        OpenApiParameter(
            name="date",
            location=OpenApiParameter.QUERY,
            required=False,
            description="Calendar date (YYYY-MM-DD). Overrides start_date/end_date if both are provided.",
            type=str,
        ),
        OpenApiParameter(
            name="start_date",
            location=OpenApiParameter.QUERY,
            required=False,
            description="Period start date (YYYY-MM-DD), inclusive.",
            type=str,
        ),
        OpenApiParameter(
            name="end_date",
            location=OpenApiParameter.QUERY,
            required=False,
            description="Period end date (YYYY-MM-DD), inclusive.",
            type=str,
        ),
    ],
    responses={200: MommySymptomStatisticItemSchema(many=True)},
    examples=[
        OpenApiExample(
            "Statistics",
            value=[
                {
                    "symptom_name": "Headache",
                    "symptom_id": 10,
                    "quantity": 3,
                    "risk_name": "Air pollution sensitivity",
                    "risk_id": 5,
                }
            ],
            response_only=True,
        )
    ],
)
class UserMommySymptomsStatisticsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        start_date, end_date = _date_period_from_request(request)
        logger.info(
            "UserMommySymptomsStatisticsView GET, user=%s, start_date=%s, end_date=%s",
            request.user,
            start_date,
            end_date,
        )

        symptom_counts = list(
            UserMommySymptoms.objects.filter(
                user=request.user,
                recorded_at__date__gte=start_date,
                recorded_at__date__lte=end_date,
            )
            .values("symptom_id", "symptom__name")
            .annotate(quantity=Count("id"))
            .order_by("symptom__name", "symptom_id")
        )
        quantities_by_symptom_id = {
            item["symptom_id"]: item["quantity"] for item in symptom_counts
        }
        names_by_symptom_id = {
            item["symptom_id"]: item["symptom__name"] for item in symptom_counts
        }

        links = (
            RiskDefinitionMommySymptom.objects.filter(
                symptom_id__in=quantities_by_symptom_id.keys(),
                risk_definition__is_enabled=True,
            )
            .select_related("risk_definition", "symptom")
            .order_by(
                "symptom__name", "risk_definition__priority", "risk_definition__name"
            )
        )

        data = [
            {
                "symptom_name": names_by_symptom_id[link.symptom_id],
                "symptom_id": link.symptom_id,
                "quantity": quantities_by_symptom_id[link.symptom_id],
                "risk_name": link.risk_definition.name,
                "risk_id": link.risk_definition_id,
            }
            for link in links
        ]
        return Response(data)


# ---------- BABY ----------


@extend_schema(
    tags=["Symptoms – Baby"],
    summary="Baby symptoms checklist (id + name)",
    responses={200: ChecklistResponseSchema},
)
class BabySymptomsChecklistView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Baby symptoms checklist (id + name)"""
        logger.info("BabySymptomsChecklistView GET, user=%s", request.user)
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
        logger.info("UserBabySymptomsSelectionView GET, user=%s", request.user)
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
        logger.info(
            "UserBabySymptomsSelectionView POST, user=%s, data=%s",
            request.user,
            request.data,
        )
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
        logger.info(
            "MovementCSVUploadView POST, user=%s, files=%s, payload_keys=%s",
            request.user,
            sorted(request.FILES.keys()),
            _payload_keys(request.data),
        )
        if "file" not in request.FILES:
            logger.warning("MovementCSVUploadView missing file, user=%s", request.user)
            return Response({"error": "No file provided."}, status=400)

        records, errors = parse_csv_to_records(request.FILES["file"])
        logger.info(
            "MovementCSVUploadView parsed CSV, user=%s, records=%s, errors=%s",
            request.user,
            len(records),
            len(errors),
        )

        if not records and errors:
            logger.warning(
                "MovementCSVUploadView rejected CSV, user=%s, errors=%s",
                request.user,
                errors,
            )
            return Response(
                {"status": "error", "imported": 0, "errors": errors}, status=400
            )

        try:
            summary = ingest_movements_batch(user_id=request.user.id, records=records)
        except Exception as e:
            logger.exception(
                "MovementCSVUploadView ingest failed, user=%s", request.user
            )
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
                logger.warning(
                    "MovementCSVUploadView recompute failed, user=%s, date=%s, error=%s",
                    request.user,
                    d,
                    e,
                )
                exposure_errors.append({"date": d.isoformat(), "error": str(e)})

        payload = {
            "status": "ok",
            **summary,  # imported, air_exposure_created, air_exposure_updated
            "exposures_recomputed": exposures_recomputed,
            "exposure_errors": exposure_errors,
            "errors": errors,  # ошибки парсинга CSV
        }
        logger.info(
            "MovementCSVUploadView completed, user=%s, imported=%s, parse_errors=%s, recomputed=%s, recompute_errors=%s",
            request.user,
            summary.get("imported"),
            len(errors),
            exposures_recomputed,
            len(exposure_errors),
        )
        return Response(
            payload, status=status.HTTP_201_CREATED if summary["imported"] > 0 else 207
        )


class MovementJSONItemSchema(serializers.Serializer):
    latitude = serializers.FloatField()
    longitude = serializers.FloatField()
    timestamp = serializers.DateTimeField()
    indoor = serializers.BooleanField(required=False)


class MovementJSONUploadRequestSchema(serializers.Serializer):
    movements = MovementJSONItemSchema(many=True)


@extend_schema(
    summary="Upload user movements via JSON",
    description=(
        "Allows uploading movement data as JSON with latitude, longitude and timestamp. "
        "Each item is parsed and stored as a Movement object associated with the authenticated user. "
        "The endpoint accepts an `application/json` request with a `movements` array."
    ),
    request=MovementJSONUploadRequestSchema,
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
            description="Invalid or missing JSON data.",
            examples=[
                OpenApiExample(
                    "Missing movements",
                    value={
                        "status": "error",
                        "imported": 0,
                        "errors": [{"error": "Missing 'movements' field."}],
                    },
                    response_only=True,
                ),
                OpenApiExample(
                    "Item error",
                    value={
                        "status": "ok",
                        "imported": 10,
                        "errors": [
                            {"row": 11, "error": "Bad value: Invalid isoformat string"}
                        ],
                    },
                    response_only=True,
                ),
            ],
        ),
    },
)
class MovementJSONUploadView(APIView):
    parser_classes = [JSONParser]
    permission_classes = [IsAuthenticated]

    def post(self, request, *args, **kwargs):
        logger.info(
            "MovementJSONUploadView POST, user=%s, payload_keys=%s",
            request.user,
            _payload_keys(request.data),
        )

        records, errors = parse_json_to_records(request.data)
        logger.info(
            "MovementJSONUploadView parsed JSON, user=%s, records=%s, errors=%s",
            request.user,
            len(records),
            len(errors),
        )

        if not records and errors:
            logger.warning(
                "MovementJSONUploadView rejected JSON, user=%s, errors=%s",
                request.user,
                errors,
            )
            return Response(
                {"status": "error", "imported": 0, "errors": errors}, status=400
            )

        try:
            summary = ingest_movements_batch(user_id=request.user.id, records=records)
        except Exception as e:
            logger.exception(
                "MovementJSONUploadView ingest failed, user=%s", request.user
            )
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
                logger.warning(
                    "MovementJSONUploadView recompute failed, user=%s, date=%s, error=%s",
                    request.user,
                    d,
                    e,
                )
                exposure_errors.append({"date": d.isoformat(), "error": str(e)})

        payload = {
            "status": "ok",
            **summary,
            "exposures_recomputed": exposures_recomputed,
            "exposure_errors": exposure_errors,
            "errors": errors,
        }
        logger.info(
            "MovementJSONUploadView completed, user=%s, imported=%s, parse_errors=%s, recomputed=%s, recompute_errors=%s",
            request.user,
            summary.get("imported"),
            len(errors),
            exposures_recomputed,
            len(exposure_errors),
        )
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

        logger.info("HealthInsightView GET, user=%s", request.user)

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
        logger.info("EnvironmentView GET, user=%s", request.user)
        latest_log = (
            AirExposureLog.objects.filter(user=request.user)
            .order_by("-timestamp")
            .first()
        )
        if not latest_log:
            logger.warning("EnvironmentView no latest log, user=%s", request.user)
            return Response({"detail": "No air exposure data found."}, status=204)

        latest_log = update_air_exposure_log_with_weather(latest_log)

        # current_weather = get_current_weather(latest_log.latitude, latest_log.longitude)
        # latest_log.temperature = current_weather["temp_c"]
        # latest_log.humidity = current_weather["humidity"]
        # latest_log.pressure = current_weather["pressure"]
        # latest_log.uvi = current_weather["uvi"]
        # latest_log.uvi_level = current_weather["uvi_level"]
        # latest_log.save()

        logger.info(
            "EnvironmentView returning latest_log_id=%s for user=%s",
            latest_log.id,
            request.user,
        )
        return Response(AirExposureLogSerializer(latest_log).data)


class CurrentAdviceView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = AdviceTemplateSerializer

    def get(self, request):
        logger.info("CurrentAdviceView GET, user=%s", request.user)
        week = request.query_params.get("week")

        try:
            pregnancy_week = int(week)
        except (TypeError, ValueError):
            pregnancy_week = None

        advices = get_current_advices(request.user, pregnancy_week)
        logger.info(
            "CurrentAdviceView resolved week=%s, advice_count=%s, user=%s",
            pregnancy_week,
            len(advices),
            request.user,
        )
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
        logger.info("LogoutView POST, user=%s", request.user)
        serializer = LogoutSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            refresh_token = serializer.validated_data["refresh"]
            token = RefreshToken(refresh_token)
            token.blacklist()
            logger.info("LogoutView blacklisted refresh token, user=%s", request.user)

            return Response(
                {"detail": "Successfully logged out."},
                status=status.HTTP_205_RESET_CONTENT,
            )
        except Exception as e:
            logger.warning(
                "LogoutView invalid refresh token, user=%s, error=%s",
                request.user,
                e,
            )
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
        logger.info("DeleteAccountView DELETE, user=%s", request.user)
        user = request.user
        user_id = user.id
        user.delete()
        logger.info("DeleteAccountView deleted user_id=%s", user_id)
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
        logger.info("PasswordChangeView POST, user=%s", request.user)
        user = request.user
        serializer = self.serializer_class(data=request.data)
        serializer.is_valid(raise_exception=True)

        if not user.check_password(serializer.validated_data["old_password"]):
            logger.warning(
                "PasswordChangeView wrong old password, user=%s", request.user
            )
            return Response(
                {"old_password": "Wrong password."}, status=status.HTTP_400_BAD_REQUEST
            )

        user.set_password(serializer.validated_data["new_password"])
        user.save()
        logger.info("PasswordChangeView password changed, user=%s", request.user)
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
        logger.info("WeeklyExposureView GET, user=%s", request.user)
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
        logger.info("SummaryView GET, user=%s", request.user)

        latest_log = (
            AirExposureLog.objects.filter(user=request.user)
            .order_by("-timestamp")
            .first()
        )
        if not latest_log:
            logger.warning("SummaryView no latest log, user=%s", request.user)
            return Response({"detail": "No air exposure data found."}, status=204)

        # AQ + Weather + UV (returns AirExposureLog instance)
        aq_weater_uv = update_air_exposure_log_with_weather(latest_log)

        # Recommendations snapshot
        from recommendations.evaluator import get_or_create_fresh_snapshot

        snapshot = get_or_create_fresh_snapshot(
            request.user, fresh_for_hours=6, trigger_event="login"
        )
        recommendations = snapshot.recommendations

        # Latest exposure and delta (mom/baby are the same for now)
        exposures = list(
            Exposure.objects.filter(user=request.user).order_by("-timestamp")[:2]
        )
        exposure = exposures[0] if exposures else None
        risk_delta = (
            (exposures[0].exposure_level - exposures[1].exposure_level)
            if len(exposures) > 1
            else None
        )

        # Exposure history for last 7 calendar days
        end_date = timezone.localdate()
        start_date = end_date - dt.timedelta(days=7 - 1)
        qs_hist = Exposure.objects.filter(
            user=request.user,
            timestamp__gte=start_date,
            timestamp__lte=end_date,
        ).order_by("timestamp")

        exposure_history_payload = {
            "start_date": start_date,
            "end_date": end_date,
            "days_requested": 7,
            "items": qs_hist,
        }

        pollutant_compliance = compute_pollutant_compliance(
            request.user, latest_log, exposure
        )
        today = timezone.localdate()
        daily_exposure = DailyExposure.objects.filter(
            user=request.user, date=today
        ).first()
        week_start = today - dt.timedelta(days=today.weekday())
        daily_checkins = list(
            DailyCheckin.objects.filter(
                user=request.user,
                date__gte=week_start,
                date__lte=today,
            )
            .order_by("date")
            .values_list("date", flat=True)
        )
        task_completions = _task_completion_history(request.user, week_start, today)
        wellbeing_log = UserWellbeingLog.objects.filter(
            user=request.user, date=today
        ).first()
        water = {
            "date": today.isoformat(),
            "amount": wellbeing_log.water_amount if wellbeing_log else 0,
            "unit": wellbeing_log.water_unit if wellbeing_log else "ml",
        }

        user: User = request.user
        data = {
            # NEW: snapshot meta for mobile app
            "snapshot_id": snapshot.id,
            "snapshot_created_at": snapshot.created_at.isoformat(),
            "aq_weather_uv": aq_weater_uv,
            "risks_delta": {"mom": risk_delta, "baby": risk_delta},
            "mom_exposure": exposure,
            "baby_exposure": exposure,
            "recommendations": recommendations,
            "today_journey": get_today_journey(user),
            "week_info": user.week_info(),
            "daily_exposure_level": (
                daily_exposure.exposure_level if daily_exposure else None
            ),
            "daily_checkins": daily_checkins,
            "water": water,
            "task_completions": task_completions,
            "exposure_history": exposure_history_payload,
            "pollutant_compliance": pollutant_compliance,
        }

        serializer = SummaryResponseSerializer(data)
        logger.info(
            "SummaryView assembled response, user=%s, snapshot_id=%s, exposure_history_items=%s",
            request.user,
            snapshot.id,
            len(exposure_history_payload["items"]),
        )
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
        logger.info(
            "SetLanguageView POST, user=%s, payload_keys=%s",
            request.user,
            _payload_keys(request.data),
        )
        lang = request.data.get("language")

        if lang not in dict(LANGUAGE_CHOICES):
            logger.warning(
                "SetLanguageView invalid language, user=%s, language=%s",
                request.user,
                lang,
            )
            return Response(
                {"error": "Invalid language code"}, status=status.HTTP_400_BAD_REQUEST
            )

        request.user.language = lang
        request.user.save()
        logger.info(
            "SetLanguageView updated language, user=%s, language=%s",
            request.user,
            lang,
        )

        return Response({"message": "Language updated", "language": lang})


def test_login(request):
    user = authenticate(request, username="admin@example.com", password="admin")
    if user is not None:
        login(request, user)
        return HttpResponse("✅ Logged in. Check your cookies.")
    return HttpResponse("❌ Login failed.")


def login_view(request):
    if request.method == "POST":
        logger.info("LoginView POST, payload_keys=%s", _payload_keys(request.POST))
        email = request.POST.get("email")
        password = request.POST.get("password")
        user = authenticate(request, username=email, password=password)
        if user is not None:
            login(request, user)
            logger.info("LoginView authenticated user_id=%s", user.id)
            return HttpResponse("Logged in successfully")
        else:
            logger.warning("LoginView invalid credentials for email=%s", email)
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
        logger.info("MetaChoicesView GET")
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
        logger.info("ExposureHistoryView GET, user=%s", request.user)
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


@extend_schema(
    summary="List recommendation completions",
    description="Returns recommendation completion records for the authenticated user. "
    "Optional filtering by snapshot_id.",
    parameters=[
        OpenApiParameter(
            name="snapshot_id",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            description="Filter completions by snapshot ID",
            required=False,
        ),
    ],
    responses=RecommendationCompletionSerializer(many=True),
)
class RecommendationCompletionView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request):
        logger.info(
            "RecommendationCompletionView GET, user=%s, snapshot_id=%s",
            request.user,
            request.query_params.get("snapshot_id"),
        )
        qs = RecommendationCompletion.objects.filter(user=request.user).order_by(
            "-updated_at"
        )

        snapshot_id = request.query_params.get("snapshot_id")
        if snapshot_id:
            qs = qs.filter(snapshot_id=snapshot_id)

        data = RecommendationCompletionSerializer(qs, many=True).data
        logger.info(
            "RecommendationCompletionView returning %s items for user=%s",
            len(data),
            request.user,
        )
        return Response(data)

    def post(self, request):
        logger.info(
            "RecommendationCompletionView POST, user=%s, payload_keys=%s",
            request.user,
            _payload_keys(request.data),
        )
        s = RecommendationCompletionUpsertSerializer(
            data=request.data, context={"request": request}
        )
        s.is_valid(raise_exception=True)
        data = s.validated_data

        obj, created = RecommendationCompletion.objects.update_or_create(
            user=request.user,
            snapshot_id=data["snapshot_id"],
            rule_id=data["rule_id"],
            rule_version=data["rule_version"],
            dimension=data["dimension"],
            defaults={"status": data["status"]},
        )

        out = RecommendationCompletionSerializer(obj).data
        logger.info(
            "RecommendationCompletionView upserted completion_id=%s, created=%s, user=%s",
            obj.id,
            created,
            request.user,
        )
        return Response(
            out, status=status.HTTP_201_CREATED if created else status.HTTP_200_OK
        )


class WellbeingCatalogView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Wellbeing"],
        summary="Wellbeing catalog (water goal + mood chips + feeling chips)",
        responses={
            200: inline_serializer(
                name="WellbeingCatalogResponse",
                fields={
                    "water_goal": inline_serializer(
                        name="WaterGoal",
                        fields={
                            "value": serializers.FloatField(allow_null=True),
                            "unit": serializers.CharField(),
                        },
                    ),
                    "moods": WellbeingItemSerializer(many=True),
                    "feelings": WellbeingItemSerializer(many=True),
                },
            )
        },
        examples=[
            OpenApiExample(
                "Catalog example",
                value={
                    "water_goal": {"value": 2130, "unit": "ml"},
                    "moods": [
                        {
                            "id": 1,
                            "kind": "mood",
                            "code": "feel_sick",
                            "title": "Feel sick",
                            "emoji": "🤒",
                            "sort_order": 10,
                            "number_value": None,
                            "unit": "",
                            "is_active": True,
                        },
                    ],
                    "feelings": [
                        {
                            "id": 10,
                            "kind": "feeling",
                            "code": "headache",
                            "title": "Headache",
                            "emoji": "🤕",
                            "sort_order": 10,
                            "number_value": None,
                            "unit": "",
                            "is_active": True,
                        },
                    ],
                },
                response_only=True,
            )
        ],
    )
    def get(self, request):
        logger.info("WellbeingCatalogView GET, user=%s", request.user)
        moods = Wellbeing.objects.filter(kind="mood", is_active=True)
        feelings = Wellbeing.objects.filter(kind="feeling", is_active=True)
        water = (
            Wellbeing.objects.filter(kind="water_goal", is_active=True)
            .order_by("id")
            .first()
        )

        data = {
            "water_goal": {
                "value": water.number_value if water else None,
                "unit": water.unit if water else "ml",
            },
            "moods": WellbeingItemSerializer(moods, many=True).data,
            "feelings": WellbeingItemSerializer(feelings, many=True).data,
        }
        logger.info(
            "WellbeingCatalogView returning moods=%s, feelings=%s, user=%s",
            len(data["moods"]),
            len(data["feelings"]),
            request.user,
        )
        return Response(data)


class UserWellbeingLogView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Wellbeing"],
        summary="Get wellbeing log for date",
        parameters=[
            OpenApiParameter(
                name="date",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Date in YYYY-MM-DD",
            )
        ],
        responses={
            200: inline_serializer(
                name="UserWellbeingLogResponse",
                fields={
                    "date": serializers.DateField(),
                    "water_amount": serializers.FloatField(),
                    "water_unit": serializers.CharField(),
                    "moods": WellbeingItemSerializer(many=True),
                    "feelings": WellbeingItemSerializer(many=True),
                },
            ),
            400: inline_serializer(
                name="UserWellbeingLogBadRequest",
                fields={"detail": serializers.CharField()},
            ),
        },
        examples=[
            OpenApiExample(
                "Empty log example",
                value={
                    "date": "2026-02-28",
                    "water_amount": 0,
                    "water_unit": "ml",
                    "moods": [],
                    "feelings": [],
                },
                response_only=True,
            )
        ],
    )
    def get(self, request):
        logger.info(
            "UserWellbeingLogView GET, user=%s, date=%s",
            request.user,
            request.query_params.get("date"),
        )
        date = request.query_params.get("date")
        if not date:
            logger.warning(
                "UserWellbeingLogView missing date param, user=%s", request.user
            )
            return Response(
                {"detail": "date query param is required (YYYY-MM-DD)"}, status=400
            )

        log = UserWellbeingLog.objects.filter(user=request.user, date=date).first()
        if not log:
            logger.info(
                "UserWellbeingLogView returning empty state, user=%s, date=%s",
                request.user,
                date,
            )
            return Response(
                {
                    "date": date,
                    "water_amount": 0,
                    "water_unit": "ml",
                    "moods": [],
                    "feelings": [],
                }
            )

        logger.info(
            "UserWellbeingLogView returning existing log_id=%s, user=%s, date=%s",
            log.id,
            request.user,
            date,
        )
        return Response(UserWellbeingLogSerializer(log).data)

    @extend_schema(
        tags=["Wellbeing"],
        summary="Upsert wellbeing log for date",
        request=inline_serializer(
            name="UserWellbeingLogUpsertRequest",
            fields={
                "date": serializers.DateField(),
                "water_amount": serializers.FloatField(required=False, min_value=0),
                "water_unit": serializers.CharField(required=False, default="ml"),
                "mood_ids": serializers.ListField(
                    child=serializers.IntegerField(), required=False
                ),
                "feeling_ids": serializers.ListField(
                    child=serializers.IntegerField(), required=False
                ),
            },
        ),
        responses={
            201: inline_serializer(
                name="UserWellbeingLogUpsertResponse",
                fields={
                    "date": serializers.DateField(),
                    "water_amount": serializers.FloatField(),
                    "water_unit": serializers.CharField(),
                    "moods": WellbeingItemSerializer(many=True),
                    "feelings": WellbeingItemSerializer(many=True),
                },
            ),
            400: inline_serializer(
                name="UserWellbeingLogUpsertBadRequest",
                fields={"detail": serializers.CharField()},
            ),
        },
        examples=[
            OpenApiExample(
                "Upsert request example",
                value={
                    "date": "2026-02-28",
                    "water_amount": 250,
                    "water_unit": "ml",
                    "mood_ids": [1, 2],
                    "feeling_ids": [10],
                },
                request_only=True,
            )
        ],
    )
    def post(self, request):
        logger.info(
            "UserWellbeingLogView POST, user=%s, payload_keys=%s",
            request.user,
            _payload_keys(request.data),
        )
        s = UserWellbeingLogUpsertSerializer(
            data=request.data, context={"request": request}
        )
        s.is_valid(raise_exception=True)
        log = s.save()
        logger.info(
            "UserWellbeingLogView upserted log_id=%s, user=%s, date=%s",
            log.id,
            request.user,
            log.date,
        )
        return Response(UserWellbeingLogSerializer(log).data, status=201)


class DailyCheckinView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Wellbeing"],
        summary="Check whether daily checkin exists for date",
        parameters=[
            OpenApiParameter(
                name="date",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Date in YYYY-MM-DD",
            )
        ],
        responses={
            200: inline_serializer(
                name="DailyCheckinExistsResponse",
                fields={
                    "date": serializers.DateField(),
                    "exists": serializers.BooleanField(),
                },
            ),
            400: inline_serializer(
                name="DailyCheckinExistsBadRequest",
                fields={"detail": serializers.CharField()},
            ),
        },
    )
    def get(self, request):
        logger.info(
            "DailyCheckinView GET, user=%s, date=%s",
            request.user,
            request.query_params.get("date"),
        )
        date = request.query_params.get("date")
        if not date:
            logger.warning("DailyCheckinView missing date param, user=%s", request.user)
            return Response(
                {"detail": "date query param is required (YYYY-MM-DD)"}, status=400
            )

        exists = DailyCheckin.objects.filter(user=request.user, date=date).exists()
        return Response({"date": date, "exists": exists})

    @extend_schema(
        tags=["Wellbeing"],
        summary="Create daily checkin for date",
        request=inline_serializer(
            name="DailyCheckinCreateRequest",
            fields={"date": serializers.DateField()},
        ),
        responses={
            201: DailyCheckinSerializer,
            400: inline_serializer(
                name="DailyCheckinCreateBadRequest",
                fields={"detail": serializers.CharField()},
            ),
        },
        examples=[
            OpenApiExample(
                "Create daily checkin request",
                value={"date": "2026-04-21"},
                request_only=True,
            )
        ],
    )
    def post(self, request):
        logger.info(
            "DailyCheckinView POST, user=%s, payload_keys=%s",
            request.user,
            _payload_keys(request.data),
        )
        serializer = DailyCheckinCreateSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        daily_checkin = serializer.save()
        logger.info(
            "DailyCheckinView created id=%s, user=%s, date=%s",
            daily_checkin.id,
            request.user,
            daily_checkin.date,
        )
        return Response(DailyCheckinSerializer(daily_checkin).data, status=201)


class DailyTaskListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Wellbeing"],
        summary="Get active daily tasks",
        responses={200: DailyTaskSerializer(many=True)},
    )
    def get(self, request):
        logger.info("DailyTaskListView GET, user=%s", request.user)
        tasks = DailyTask.objects.filter(is_active=True).order_by("sort_order", "title")
        return Response(DailyTaskSerializer(tasks, many=True).data)


class TaskCompletionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Wellbeing"],
        summary="Get completed daily tasks for date",
        parameters=[
            OpenApiParameter(
                name="date",
                type=str,
                location=OpenApiParameter.QUERY,
                required=True,
                description="Date in YYYY-MM-DD",
            )
        ],
        responses={
            200: inline_serializer(
                name="TaskCompletionDayResponse",
                fields={
                    "date": serializers.DateField(),
                    "tasks": serializers.ListField(child=serializers.SlugField()),
                },
            ),
            400: inline_serializer(
                name="TaskCompletionBadRequest",
                fields={"detail": serializers.CharField()},
            ),
        },
    )
    def get(self, request):
        logger.info(
            "TaskCompletionView GET, user=%s, date=%s",
            request.user,
            request.query_params.get("date"),
        )
        date = request.query_params.get("date")
        if not date:
            logger.warning(
                "TaskCompletionView missing date param, user=%s", request.user
            )
            return Response(
                {"detail": "date query param is required (YYYY-MM-DD)"}, status=400
            )

        try:
            parsed_date = serializers.DateField().run_validation(date)
        except serializers.ValidationError as exc:
            return Response({"date": exc.detail}, status=400)

        tasks = list(
            UserDailyTaskCompletion.objects.filter(
                user=request.user,
                date=parsed_date,
                completed=True,
                task__is_active=True,
            )
            .select_related("task")
            .order_by("task__sort_order", "task__title")
            .values_list("task__code", flat=True)
        )
        data = {"date": parsed_date, "tasks": tasks}
        return Response(TaskCompletionDaySerializer(data).data)

    @extend_schema(
        tags=["Wellbeing"],
        summary="Replace completed daily tasks for date",
        request=inline_serializer(
            name="TaskCompletionUpsertRequest",
            fields={
                "date": serializers.DateField(),
                "tasks": serializers.ListField(child=serializers.SlugField()),
            },
        ),
        responses={
            201: inline_serializer(
                name="TaskCompletionUpsertResponse",
                fields={
                    "date": serializers.DateField(),
                    "tasks": serializers.ListField(child=serializers.SlugField()),
                },
            ),
            400: inline_serializer(
                name="TaskCompletionUpsertBadRequest",
                fields={"detail": serializers.CharField()},
            ),
        },
        examples=[
            OpenApiExample(
                "Task completion request",
                value={
                    "date": "2026-04-30",
                    "tasks": ["cooking_smoke", "drink_water"],
                },
                request_only=True,
            )
        ],
    )
    def post(self, request):
        logger.info(
            "TaskCompletionView POST, user=%s, payload_keys=%s",
            request.user,
            _payload_keys(request.data),
        )
        serializer = TaskCompletionUpsertSerializer(
            data=request.data, context={"request": request}
        )
        serializer.is_valid(raise_exception=True)
        data = serializer.save()
        logger.info(
            "TaskCompletionView upserted user=%s, date=%s, tasks=%s",
            request.user,
            data["date"],
            data["tasks"],
        )
        return Response(TaskCompletionDaySerializer(data).data, status=201)
