# api/views.py
import datetime as dt
import logging

from zoneinfo import ZoneInfo

# from io import TextIOWrapper
from rest_framework.parsers import FormParser, JSONParser, MultiPartParser
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
    RecommendationCompletionValidationErrorSerializer,
)

# from django.utils.translation import gettext as _


from django.contrib.auth import authenticate, login

from django.shortcuts import get_object_or_404, render
from django.db import transaction
from django.db.models import Count
from django.conf import settings


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
    RiskDefinitionBabySymptom,
    SYMPTOM_CLASS_METADATA,
    BabySymptom,
    UserBabySymptoms,
    Exposure,
    DailyExposure,
    RecommendationCompletion,
    Wellbeing,
    DailyCheckin,
    DailyTask,
    UserDailyTaskCompletion,
    DailyAction,
    DailyPlan,
    UserWellbeingLog,
    SYMPTOM_CHECKLIST_MOMMY,
    SYMPTOM_CHECKLIST_BABY,
)
from recommendations.services.symptom_monitoring import (
    InvalidSymptomChecklist,
    get_or_create_daily_checklist,
    get_user_timezone,
    local_date_for_user,
    local_day_bounds,
    record_response,
)
from .choices_emoji import (
    map_choices_with_emoji,
    COOKING_METHOD_EMOJI,
    DIET_TYPE_EMOJI,
    WORK_TYPE_EMOJI,
)
from .serializers import (
    RegisterSerializer,
    UserAvatarUploadSerializer,
    UserProfileSerializer,
    UserLifeStyleSerializer,
    HealthInsightSerializer,
    HealthInsightResponseSerializer,
    AirExposureLogSerializer,
    AdviceTemplateSerializer,
    PasswordChangeSerializer,
    LogoutSerializer,
    ErrorResponseSerializer,
    WEEKLY_EXPOSURE_RESPONSE_SCHEMA,
    ErrorSerializer,
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
    DailyPlanResponseSerializer,
    DailyActionCompletionUpdateSerializer,
    DailyActionCompletionResponseSerializer,
)

from .services.services import (
    get_current_advices,
)
from .services.analytics import get_today_journey
from .services.air_exposure import ingest_movements_batch
from .services.air_exposure_daily import recompute_daily_exposure
from .services.helpers import parse_csv_to_records, parse_json_to_records
from .services.h3_grid import InvalidCoordinatesError
from .permissions import HasValidRegistrationAPIKey
from .services.aq_logs_services import update_air_exposure_log_with_weather

from api.models import (
    LANGUAGE_CHOICES,
    EXPOSURE_LEVEL_CHOICES,
    UserLifeStyle,
)


from datetime import date as date_cls
from django.utils.dateparse import parse_datetime

logger = logging.getLogger(__name__)


def _active_daily_task_rows():
    return list(DailyTask.objects.filter(is_active=True).values("code", "category"))


def _task_completion_counts(task_codes, active_tasks=None):
    completed_codes = set(task_codes)
    counts = {
        category: {"done": 0, "total": 0}
        for category, _label in DailyTask.CATEGORY_CHOICES
    }
    for task in active_tasks if active_tasks is not None else _active_daily_task_rows():
        category = task["category"]
        if category not in counts:
            continue
        counts[category]["total"] += 1
        if task["code"] in completed_codes:
            counts[category]["done"] += 1
    return counts


def _task_completion_history(user, start_date, end_date):
    active_tasks = _active_daily_task_rows()
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
        {
            "date": completion_date,
            "tasks": tasks,
            "counts": _task_completion_counts(tasks, active_tasks=active_tasks),
        }
        for completion_date, tasks in by_date.items()
    ]


def _payload_keys(payload):
    if hasattr(payload, "keys"):
        return sorted(str(key) for key in payload.keys())
    return []


def _parse_recorded_at_param(request):
    """
    Read recorded_at from the query string or body and return an aware datetime.
    Fall back to now() in settings.TIME_ZONE.
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
        dt = timezone.make_aware(dt, get_user_timezone(request.user))
    return dt


def _target_date_from_request(request):
    """
    Accept ?date=YYYY-MM-DD or recorded_at from the query string or body.
    Resolution priority is date, recorded_at, then today.
    """
    raw_date = request.query_params.get("date")
    if raw_date:
        try:
            return date_cls.fromisoformat(raw_date)
        except ValueError:
            raise ValidationError({"date": "Invalid date. Use YYYY-MM-DD."})
    return local_date_for_user(request.user, _parse_recorded_at_param(request))


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
    lifestyle_areas = ChoiceSchema(many=True)
    lifestyle_time_spent = ChoiceSchema(many=True)
    lifestyle_time_of_day = ChoiceSchema(many=True)
    exposure_levels = ChoiceSchema(many=True)


# ---- Symptom checklists & selection ----
class ChecklistItemSchema(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    name = serializers.CharField()


class ChecklistResponseSchema(serializers.Serializer):
    checklist_id = serializers.UUIDField()
    symptoms = ChecklistItemSchema(many=True)


class SymptomSelectionRequestSchema(serializers.Serializer):
    symptom_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), allow_empty=True
    )
    recorded_at = serializers.DateTimeField(
        required=False,
        help_text="ISO-8601. If timezone is omitted, interpreted in server TIME_ZONE.",
    )
    checklist_id = serializers.UUIDField(
        required=False,
        allow_null=True,
        help_text="Optional. Older mobile clients may omit it.",
    )


class SymptomSelectionResponseSchema(serializers.Serializer):
    date = serializers.DateField()
    recorded_at = serializers.DateTimeField(required=False, allow_null=True)
    symptom_ids = serializers.ListField(child=serializers.IntegerField())
    checklist_id = serializers.UUIDField(required=False, allow_null=True)


class MommySymptomStatisticItemSchema(serializers.Serializer):
    symptom_name = serializers.CharField()
    symptom_id = serializers.IntegerField()
    quantity = serializers.IntegerField()
    risk_name = serializers.CharField()
    risk_id = serializers.IntegerField()


class SymptomClassRiskSchema(serializers.Serializer):
    risk_id = serializers.IntegerField()
    risk_name = serializers.CharField()
    source_phrase = serializers.CharField(allow_blank=True)


class SymptomClassSymptomStatisticSchema(serializers.Serializer):
    symptom_name = serializers.CharField()
    symptom_id = serializers.IntegerField()
    quantity = serializers.IntegerField()
    risks = SymptomClassRiskSchema(many=True)


class SymptomClassStatisticSchema(serializers.Serializer):
    symptom_class = serializers.IntegerField()
    class_name = serializers.CharField()
    color_flag = serializers.CharField()
    quantity = serializers.IntegerField()
    symptoms = SymptomClassSymptomStatisticSchema(many=True)


class SymptomClassStatisticsResponseSchema(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    classes = SymptomClassStatisticSchema(many=True)


def _symptom_class_statistics(user, start_date, end_date, UserSymptomModel, LinkModel):
    symptom_counts = list(
        UserSymptomModel.objects.filter(
            user=user,
            recorded_at__date__gte=start_date,
            recorded_at__date__lte=end_date,
        )
        .values("symptom_id", "symptom__name")
        .annotate(quantity=Count("id"))
        .order_by("symptom__name", "symptom_id")
    )
    if not symptom_counts:
        return []

    quantities_by_symptom_id = {
        item["symptom_id"]: item["quantity"] for item in symptom_counts
    }
    names_by_symptom_id = {
        item["symptom_id"]: item["symptom__name"] for item in symptom_counts
    }
    class_values = sorted(SYMPTOM_CLASS_METADATA.keys())

    links = (
        LinkModel.objects.filter(
            symptom_id__in=quantities_by_symptom_id.keys(),
            symptom_class__in=class_values,
            risk_definition__is_enabled=True,
        )
        .select_related("risk_definition", "symptom")
        .order_by(
            "symptom_class",
            "symptom__name",
            "risk_definition__priority",
            "risk_definition__name",
        )
    )

    buckets = {}
    symptoms_by_class = {}
    for symptom_class in class_values:
        metadata = SYMPTOM_CLASS_METADATA[symptom_class]
        buckets[symptom_class] = {
            "symptom_class": symptom_class,
            "class_name": metadata["name"],
            "color_flag": metadata["color_flag"],
            "quantity": 0,
            "symptoms": [],
        }
        symptoms_by_class[symptom_class] = {}

    for link in links:
        symptom_class = link.symptom_class
        symptom_id = link.symptom_id
        class_symptoms = symptoms_by_class[symptom_class]
        if symptom_id not in class_symptoms:
            quantity = quantities_by_symptom_id[symptom_id]
            item = {
                "symptom_name": names_by_symptom_id[symptom_id],
                "symptom_id": symptom_id,
                "quantity": quantity,
                "risks": [],
            }
            class_symptoms[symptom_id] = item
            buckets[symptom_class]["symptoms"].append(item)
            buckets[symptom_class]["quantity"] += quantity

        class_symptoms[symptom_id]["risks"].append(
            {
                "risk_name": link.risk_definition.name,
                "risk_id": link.risk_definition_id,
                "source_phrase": link.source_phrase,
            }
        )

    return [bucket for bucket in buckets.values() if bucket["symptoms"]]


@extend_schema(
    summary="Register a new user account",
    description="Registers a new user. Requires a valid API key in the `X-API-Key` header.",
    request=RegisterSerializer,
    responses={
        201: OpenApiResponse(
            response=inline_serializer(
                name="RegisterSuccessResponse",
                fields={"message": serializers.CharField()},
            ),
            examples=[
                OpenApiExample(
                    name="User created",
                    value={"message": "User created successfully"},
                    response_only=True,
                )
            ],
        ),
        403: OpenApiResponse(
            response=ErrorResponseSerializer,
            examples=[
                OpenApiExample(
                    name="Invalid API key",
                    value={"detail": "Invalid or missing API key."},
                    response_only=True,
                )
            ],
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


@extend_schema(
    tags=["User"],
    summary="Get current user profile",
    description=(
        "Returns the authenticated user's profile and pregnancy settings. "
        "Use this after authentication to hydrate the mobile profile/onboarding state. "
        "`bmi` is calculated from `height` and `weight_pre_pregnancy` when both are present."
    ),
    responses={200: UserProfileSerializer},
    methods=["GET"],
)
@extend_schema(
    tags=["User"],
    summary="Update current user profile",
    description=(
        "Partially updates the authenticated user's profile. "
        "When `week_of_pregnancy` is changed the backend recalculates `pregnancy_start_date`. "
        "Choice values for `language`, `race`, `country`, and `preferred_share_channel` must match the API choices."
    ),
    request=UserProfileSerializer,
    responses={200: UserProfileSerializer},
    examples=[
        OpenApiExample(
            "Profile update",
            value={
                "name": "Jane Doe",
                "date_of_birth": "1994-06-20",
                "height": 168,
                "weight_pre_pregnancy": 64,
                "race": "african",
                "country": "NG",
                "is_first_pregnancy": True,
                "pregnancy_number": 1,
                "week_of_pregnancy": 24,
                "tracking_enabled": True,
                "notifications_enabled": True,
                "notification_window_from": "09:00",
                "notification_window_to": "21:00",
                "timezone": "Africa/Lagos",
                "consent": True,
                "preferred_share_channel": "whatsapp",
            },
            request_only=True,
        )
    ],
    methods=["PATCH", "PUT"],
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
    tags=["User"],
    summary="Upload current user avatar",
    description=(
        "Uploads a profile avatar image for the authenticated user. "
        "Send multipart/form-data with an `avatar` file. "
        "Supported image types are JPEG, PNG, and WebP up to 5 MB."
    ),
    request=UserAvatarUploadSerializer,
    responses={200: UserProfileSerializer, 400: ErrorResponseSerializer},
    examples=[
        OpenApiExample(
            "Avatar upload",
            value={"avatar": "<binary image file>"},
            request_only=True,
        )
    ],
    methods=["POST"],
)
@extend_schema(
    tags=["User"],
    summary="Delete current user uploaded avatar",
    description=(
        "Deletes the uploaded avatar image for the authenticated user. "
        "If a legacy social avatar_url exists, profile responses will fall back to it."
    ),
    responses={200: UserProfileSerializer},
    methods=["DELETE"],
)
class UserAvatarView(APIView):
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def post(self, request):
        logger.info(
            "UserAvatarView POST, user=%s, payload_keys=%s",
            request.user,
            _payload_keys(request.data),
        )
        serializer = UserAvatarUploadSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        user = request.user
        old_avatar_name = user.avatar.name if user.avatar else None
        user.avatar = serializer.validated_data["avatar"]
        user.save(update_fields=["avatar"])

        if old_avatar_name and old_avatar_name != user.avatar.name:
            user.avatar.storage.delete(old_avatar_name)

        logger.info("UserAvatarView uploaded avatar, user=%s", request.user)
        return Response(UserProfileSerializer(user, context={"request": request}).data)

    def delete(self, request):
        logger.info("UserAvatarView DELETE, user=%s", request.user)
        user = request.user
        old_avatar_name = user.avatar.name if user.avatar else None
        if old_avatar_name:
            storage = user.avatar.storage
            user.avatar = None
            user.save(update_fields=["avatar"])
            storage.delete(old_avatar_name)

        return Response(UserProfileSerializer(user, context={"request": request}).data)


@extend_schema(
    tags=["Lifestyle"],
    summary="Get current user lifestyle (auto-created if missing)",
    description=(
        "Returns the user's lifestyle profile. If it does not exist yet, the backend creates an empty one. "
        "Mobile clients can safely call this before showing lifestyle onboarding fields."
    ),
    responses={200: UserLifeStyleSerializer},
    methods=["GET"],
)
@extend_schema(
    tags=["Lifestyle"],
    summary="Update current user lifestyle",
    description=(
        "Partially updates lifestyle inputs used by risk calculations and recommendations. "
        "Choice values should be read from `GET /api/meta/choices/`."
    ),
    request=UserLifeStyleSerializer,
    responses={200: UserLifeStyleSerializer},
    examples=[
        OpenApiExample(
            "Lifestyle update",
            value={
                "average_sleep_hours": 7.5,
                "work_type": "Desk",
                "diet_type": "omnivore",
                "cooking_method": "gas",
                "activity_duration_minutes": 30,
                "standing_hours_per_day": 3,
                "area": "urban",
                "time_spent": "mostly_outdoors",
                "time_of_day": "morning_hours",
                "commute_mode": "car",
                "hydration_target_ml_per_day": 2200,
                "cooking_venue": "indoor",
                "ventilation_level": "medium",
            },
            request_only=True,
        )
    ],
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
    summary="Persistent mommy symptoms checklist",
    responses={200: ChecklistResponseSchema},
    examples=[
        OpenApiExample(
            "Checklist",
            value={
                "checklist_id": "67d6ca17-8fca-4739-865f-3d4d3f4b6945",
                "symptoms": [
                    {"id": 10, "code": "mommy.headache", "name": "Headache"},
                    {"id": 12, "code": "mommy.nausea", "name": "Nausea"},
                ]
            },
            response_only=True,
        )
    ],
)
class MommySymptomsChecklistView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Return the stable mommy checklist for the user's current local day."""
        logger.info("MommySymptomsChecklistView GET, user=%s", request.user)
        user: User = request.user
        checklist, _created = get_or_create_daily_checklist(
            user, SYMPTOM_CHECKLIST_MOMMY
        )
        items = [
            {
                "id": item.symptom_id_snapshot,
                "code": item.symptom_code,
                "name": item.display_name,
            }
            for item in checklist.items.all()
        ]
        data = ChecklistItemSerializer(items, many=True).data
        return Response({"checklist_id": checklist.id, "symptoms": data})


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
            value={
                "symptom_ids": [10, 12],
                "recorded_at": "2025-09-01T08:30:00+03:00",
                "checklist_id": "67d6ca17-8fca-4739-865f-3d4d3f4b6945",
            },
            request_only=True,
        ),
        OpenApiExample(
            "Response",
            value={
                "date": "2025-09-01",
                "recorded_at": "2025-09-01T08:30:00+03:00",
                "symptom_ids": [10, 12],
                "checklist_id": "67d6ca17-8fca-4739-865f-3d4d3f4b6945",
            },
            response_only=True,
        ),
    ],
    methods=["POST"],
)
class UserMommySymptomsSelectionView(APIView):
    """
    Replace all selections for the day resolved from, in priority order:
    `?date=YYYY-MM-DD`, `recorded_at` in the request body or query string,
    or the current date in `settings.TIME_ZONE`.
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
        ser = SymptomSelectionSerializer(data=request.data, context={"user": user})
        ser.is_valid(raise_exception=True)
        ids = ser.validated_data["symptom_ids"]
        recorded_at = ser.validated_data["recorded_at"]
        target_date = local_date_for_user(user, recorded_at)

        # Validate that every submitted ID exists.
        selected_symptoms = list(MommySymptom.objects.filter(id__in=ids))
        existing = {symptom.pk for symptom in selected_symptoms}
        missing = sorted(set(ids) - existing)
        if missing:
            raise ValidationError({"symptom_ids": f"Unknown ids: {missing}"})

        # Replace the complete selection for the resolved day.
        day_start, day_end = local_day_bounds(user, target_date)
        UserMommySymptoms.objects.filter(
            user=user,
            recorded_at__gte=day_start,
            recorded_at__lt=day_end,
        ).delete()
        bulk = [
            UserMommySymptoms(user=user, symptom_id=sid, recorded_at=recorded_at)
            for sid in existing
        ]
        if bulk:
            UserMommySymptoms.objects.bulk_create(bulk)

        try:
            response_event = record_response(
                user=user,
                checklist_type=SYMPTOM_CHECKLIST_MOMMY,
                recorded_at=recorded_at,
                selected_symptoms=selected_symptoms,
                checklist_id=ser.validated_data.get("checklist_id"),
            )
        except InvalidSymptomChecklist as exc:
            raise ValidationError({"checklist_id": str(exc)}) from exc

        response_data = {
            "date": target_date.isoformat(),
            "recorded_at": recorded_at.isoformat(),
            "symptom_ids": sorted(existing),
        }
        if response_event.checklist_id:
            response_data["checklist_id"] = response_event.checklist_id
        return Response(response_data)


@extend_schema(
    tags=["Symptoms Statistics Mommy"],
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
            .order_by("symptom__name", "risk_definition__priority", "risk_definition__name")
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


@extend_schema(
    tags=["Symptoms Statistics - Mommy"],
    summary="Get mommy symptoms statistics by symptom class for a period",
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
    responses={200: SymptomClassStatisticsResponseSchema},
    examples=[
        OpenApiExample(
            "Statistics by class",
            value={
                "start_date": "2026-03-01",
                "end_date": "2026-03-07",
                "classes": [
                    {
                        "symptom_class": 1,
                        "class_name": "Acute & Emergency Indicators",
                        "color_flag": "critical_red",
                        "quantity": 2,
                        "symptoms": [
                            {
                                "symptom_name": "vaginal bleeding",
                                "symptom_id": 10,
                                "quantity": 2,
                                "risks": [
                                    {
                                        "risk_name": "Preterm birth",
                                        "risk_id": 2,
                                        "source_phrase": "Vaginal bleeding",
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            response_only=True,
        )
    ],
)
class UserMommySymptomsClassStatisticsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        start_date, end_date = _date_period_from_request(request)
        logger.info(
            "UserMommySymptomsClassStatisticsView GET, user=%s, start_date=%s, end_date=%s",
            request.user,
            start_date,
            end_date,
        )
        classes = _symptom_class_statistics(
            request.user,
            start_date,
            end_date,
            UserMommySymptoms,
            RiskDefinitionMommySymptom,
        )
        return Response(
            {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "classes": classes,
            }
        )


# ---------- BABY ----------


@extend_schema(
    tags=["Symptoms – Baby"],
    summary="Persistent baby symptoms checklist",
    responses={200: ChecklistResponseSchema},
)
class BabySymptomsChecklistView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        """Return the stable baby checklist for the user's current local day."""
        logger.info("BabySymptomsChecklistView GET, user=%s", request.user)
        user: User = request.user
        checklist, _created = get_or_create_daily_checklist(
            user, SYMPTOM_CHECKLIST_BABY
        )
        items = [
            {
                "id": item.symptom_id_snapshot,
                "code": item.symptom_code,
                "name": item.display_name,
            }
            for item in checklist.items.all()
        ]
        data = ChecklistItemSerializer(items, many=True).data
        return Response({"checklist_id": checklist.id, "symptoms": data})


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
        ser = SymptomSelectionSerializer(data=request.data, context={"user": user})
        ser.is_valid(raise_exception=True)
        ids = ser.validated_data["symptom_ids"]
        recorded_at = ser.validated_data["recorded_at"]
        target_date = local_date_for_user(user, recorded_at)

        selected_symptoms = list(BabySymptom.objects.filter(id__in=ids))
        existing = {symptom.pk for symptom in selected_symptoms}
        missing = sorted(set(ids) - existing)
        if missing:
            raise ValidationError({"symptom_ids": f"Unknown ids: {missing}"})

        day_start, day_end = local_day_bounds(user, target_date)
        UserBabySymptoms.objects.filter(
            user=user,
            recorded_at__gte=day_start,
            recorded_at__lt=day_end,
        ).delete()
        bulk = [
            UserBabySymptoms(user=user, symptom_id=sid, recorded_at=recorded_at)
            for sid in existing
        ]
        if bulk:
            UserBabySymptoms.objects.bulk_create(bulk)

        try:
            response_event = record_response(
                user=user,
                checklist_type=SYMPTOM_CHECKLIST_BABY,
                recorded_at=recorded_at,
                selected_symptoms=selected_symptoms,
                checklist_id=ser.validated_data.get("checklist_id"),
            )
        except InvalidSymptomChecklist as exc:
            raise ValidationError({"checklist_id": str(exc)}) from exc

        response_data = {
            "date": target_date.isoformat(),
            "recorded_at": recorded_at.isoformat(),
            "symptom_ids": sorted(existing),
        }
        if response_event.checklist_id:
            response_data["checklist_id"] = response_event.checklist_id
        return Response(response_data)


@extend_schema(
    tags=["Symptoms Statistics - Baby"],
    summary="Get baby symptoms statistics by symptom class for a period",
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
    responses={200: SymptomClassStatisticsResponseSchema},
)
class UserBabySymptomsClassStatisticsView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request):
        start_date, end_date = _date_period_from_request(request)
        logger.info(
            "UserBabySymptomsClassStatisticsView GET, user=%s, start_date=%s, end_date=%s",
            request.user,
            start_date,
            end_date,
        )
        classes = _symptom_class_statistics(
            request.user,
            start_date,
            end_date,
            UserBabySymptoms,
            RiskDefinitionBabySymptom,
        )
        return Response(
            {
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "classes": classes,
            }
        )


@extend_schema(
    summary="Upload user movements via CSV",
    description=(
        "Uploads a batch of timestamped location points for the authenticated user. "
        "The endpoint accepts `multipart/form-data` with a `file` field. "
        "CSV columns must be `latitude`, `longitude`, and `timestamp`; `timestamp` should be ISO-8601 and include a timezone when available. "
        "After import, daily exposure is recomputed for each affected calendar date."
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
                    value={
                        "status": "ok",
                        "imported": 24,
                        "air_exposure_created": 24,
                        "air_exposure_updated": 0,
                        "exposures_recomputed": 1,
                        "exposure_errors": [],
                        "errors": [],
                    },
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
        except InvalidCoordinatesError as e:
            logger.warning(
                "MovementCSVUploadView rejected coordinates, user=%s, error=%s",
                request.user,
                e,
            )
            return Response({"status": "error", "detail": str(e)}, status=400)
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
                # Preserve the response and record calculation errors per day.
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
            "errors": errors,  # CSV parsing errors
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
        "Uploads a batch of timestamped location points for the authenticated user as JSON. "
        "Each item in `movements` must include `latitude`, `longitude`, and ISO-8601 `timestamp`; `indoor` is optional. "
        "After import, daily exposure is recomputed for each affected calendar date. "
        "This is the preferred movement upload format for mobile clients."
    ),
    request=MovementJSONUploadRequestSchema,
    responses={
        201: OpenApiResponse(
            description="Movements uploaded successfully.",
            examples=[
                OpenApiExample(
                    "Success Example",
                    value={
                        "status": "ok",
                        "imported": 24,
                        "air_exposure_created": 24,
                        "air_exposure_updated": 0,
                        "exposures_recomputed": 1,
                        "exposure_errors": [],
                        "errors": [],
                    },
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
        except InvalidCoordinatesError as e:
            logger.warning(
                "MovementJSONUploadView rejected coordinates, user=%s, error=%s",
                request.user,
                e,
            )
            return Response({"status": "error", "detail": str(e)}, status=400)
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
        200: HealthInsightResponseSerializer,
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
            request.user,
            fresh_for_hours=settings.HEALTH_INSIGHT_SNAPSHOT_FRESH_HOURS,
            trigger_event="login",
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


@extend_schema(
    tags=["Advice"],
    summary="Get current static advice templates",
    description=(
        "Returns advice templates for the current user. "
        "If `week` is provided, advice can be filtered for that pregnancy week; invalid or missing values fall back to the user's current context."
    ),
    parameters=[
        OpenApiParameter(
            name="week",
            type=OpenApiTypes.INT,
            location=OpenApiParameter.QUERY,
            required=False,
            description="Optional pregnancy week.",
        )
    ],
    responses={200: AdviceTemplateSerializer(many=True)},
)
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
        205: OpenApiResponse(description="Successfully logged out."),
        400: OpenApiResponse(
            response=ErrorResponseSerializer,
            examples=[
                OpenApiExample(
                    "Invalid token",
                    value={"error": "Invalid refresh token"},
                    response_only=True,
                )
            ],
        ),
    },
)
class LogoutView(APIView):
    permission_classes = [IsAuthenticated]
    serializer_class = LogoutSerializer

    @extend_schema(
        request=LogoutSerializer,
        responses={
            205: OpenApiResponse(description="Successfully logged out."),
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
        204: OpenApiResponse(description="Account deleted successfully."),
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
        200: OpenApiResponse(
            response=inline_serializer(
                name="PasswordChangeSuccessResponse",
                fields={"detail": serializers.CharField()},
            ),
            examples=[
                OpenApiExample(
                    "Password changed",
                    value={"detail": "Password changed successfully"},
                    response_only=True,
                )
            ],
        ),
        400: OpenApiResponse(
            response=inline_serializer(
                name="PasswordChangeErrorResponse",
                fields={"old_password": serializers.CharField(required=False)},
            ),
            examples=[
                OpenApiExample(
                    "Wrong old password",
                    value={"old_password": "Wrong password."},
                    response_only=True,
                )
            ],
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
            response=WEEKLY_EXPOSURE_RESPONSE_SCHEMA,
            description=(
                "Object keyed by decimal pregnancy-week strings. Each present week "
                "contains a non-null exposure level. Missing weeks are omitted; users "
                "without weekly exposure records receive an empty object."
            ),
            examples=[
                OpenApiExample(
                    "Populated result",
                    value={
                        "12": {"level": "Moderate"},
                        "13": {"level": "Unhealthy"},
                    },
                    response_only=True,
                ),
                OpenApiExample(
                    "Partial result",
                    value={"13": {"level": "Unhealthy"}},
                    response_only=True,
                ),
                OpenApiExample(
                    "Empty result",
                    value={},
                    response_only=True,
                ),
            ],
        ),
        401: OpenApiResponse(
            response=ErrorSerializer,
            description="Authentication credentials were not provided or are invalid.",
            examples=[
                OpenApiExample(
                    "Authentication required",
                    value={"detail": "Authentication credentials were not provided."},
                    response_only=True,
                )
            ],
        ),
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
    tags=["Dashboard"],
    summary="Get integrated summary",
    description=(
        "Main dashboard payload for the mobile app. "
        "Returns the latest air quality/weather/UV values, current exposure, 7-day exposure history, "
        "risk delta, weekly check-in/task/water state, WHO pollutant compliance, and generated recommendations. "
        "`snapshot_id` should be stored by the client when marking a recommendation as completed."
    ),
    responses={
        200: SummaryResponseSerializer,
        204: OpenApiResponse(description="No air exposure data available for this user yet."),
    },
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
            request.user,
            fresh_for_hours=settings.HEALTH_INSIGHT_SNAPSHOT_FRESH_HOURS,
            trigger_event="login",
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
        200: OpenApiResponse(
            response=inline_serializer(
                name="SetLanguageSuccessResponse",
                fields={
                    "message": serializers.CharField(),
                    "language": serializers.ChoiceField(
                        choices=[code for code, _ in LANGUAGE_CHOICES]
                    ),
                },
            ),
            examples=[
                OpenApiExample(
                    "Success",
                    value={"message": "Language updated", "language": "fr"},
                    response_only=True,
                )
            ],
        ),
        400: OpenApiResponse(
            response=inline_serializer(
                name="SetLanguageErrorResponse",
                fields={"error": serializers.CharField()},
            ),
            examples=[
                OpenApiExample(
                    "Invalid language",
                    value={"error": "Invalid language code"},
                    response_only=True,
                )
            ],
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
                "lifestyle_areas": [{"value": "urban", "label": "Urban"}],
                "lifestyle_time_spent": [
                    {"value": "mostly_indoors", "label": "Mostly indoors"}
                ],
                "lifestyle_time_of_day": [
                    {"value": "morning_hours", "label": "Morning hours"}
                ],
                "exposure_levels": [{"value": "Clean", "label": "Clean"}],
            },
            response_only=True,
        )
    ],
)
class MetaChoicesView(APIView):
    authentication_classes = []  # Public endpoint; JWT can be enabled if needed.
    permission_classes = []

    def get(self, request):
        # Choices could also be read from model fields to avoid duplication,
        # user_model = get_user_model()
        # race_choices = user_model._meta.get_field("race").choices
        # but reading constants directly is equivalent and faster.
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
            "lifestyle_areas": _map_choices(UserLifeStyle.AREA_CHOICES),
            "lifestyle_time_spent": _map_choices(UserLifeStyle.TIME_SPENT_CHOICES),
            "lifestyle_time_of_day": _map_choices(UserLifeStyle.TIME_OF_DAY_CHOICES),
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
    tags=["Recommendations"],
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

    @extend_schema(
        tags=["Recommendations"],
        summary="Upsert a recommendation completion",
        description=(
            "Marks one recommendation dimension as completed for a specific generated summary snapshot. "
            "The upsert key is `snapshot_id`, `rule_id`, `rule_version`, and `dimension`; posting the same key again updates `status`."
        ),
        request=RecommendationCompletionUpsertSerializer,
        responses={
            201: RecommendationCompletionSerializer,
            200: RecommendationCompletionSerializer,
            400: RecommendationCompletionValidationErrorSerializer,
        },
        examples=[
            OpenApiExample(
                "Completion request",
                value={
                    "snapshot_id": 123,
                    "rule_id": "alert.pm25.daily",
                    "rule_version": 1,
                    "dimension": "behavior",
                    "status": "done",
                },
                request_only=True,
            )
        ],
    )
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
        description=(
            "Returns the selectable wellbeing catalog for the current user: water goal, mood chips, and feeling chips. "
            "Use the returned `id` values in `POST /api/wellbeing/log/`."
        ),
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
        description=(
            "Returns wellbeing state for one calendar date. "
            "If no log exists yet, the endpoint returns an empty state with `water_amount: 0`, `moods: []`, and `feelings: []`."
        ),
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
        description=(
            "Updates wellbeing state for one calendar date. "
            "`water_amount` is additive: posting `250` increases the stored daily amount by 250. "
            "`mood_ids` and `feeling_ids` replace the selected chips when provided; omit a field to keep its previous selection."
        ),
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
        description="Returns whether the user has already checked in on the requested calendar date.",
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
        description=(
            "Creates a daily check-in marker for one calendar date. "
            "Posting the same date twice returns a validation error because the marker is unique per user and date."
        ),
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


class DailyPlanView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Daily Plan"],
        summary="Get the stable daily plan",
        description=(
            "Returns the authenticated user's persisted plan for their current local date, "
            "or for an optional YYYY-MM-DD date. The plan composition is created once; "
            "completion state is adapted read-only from legacy completion records."
        ),
        parameters=[
            OpenApiParameter(
                name="date",
                type=OpenApiTypes.DATE,
                location=OpenApiParameter.QUERY,
                required=False,
                description="Optional user-local date in YYYY-MM-DD format.",
            )
        ],
        responses={
            200: DailyPlanResponseSerializer,
            400: inline_serializer(
                name="DailyPlanBadRequest",
                fields={"date": serializers.ListField(child=serializers.CharField())},
            ),
        },
    )
    def get(self, request):
        from api.services.daily_plan import (
            completion_states_for_plan,
            get_or_create_daily_plan,
        )

        requested_date = request.query_params.get("date")
        parsed_date = None
        if requested_date is not None:
            try:
                parsed_date = serializers.DateField().run_validation(requested_date)
            except serializers.ValidationError as exc:
                return Response({"date": exc.detail}, status=status.HTTP_400_BAD_REQUEST)

        plan = get_or_create_daily_plan(request.user, local_date=parsed_date)
        plan = DailyPlan.objects.prefetch_related("actions").get(pk=plan.pk)
        completion_states = completion_states_for_plan(plan)
        payload = DailyPlanResponseSerializer(
            plan,
            context={"completion_states": completion_states},
        ).data
        return Response(payload)


class DailyActionCompletionView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Daily Plan"],
        summary="Update a Daily Plan action completion state",
        description=(
            "Updates one action from the authenticated user's persisted Daily Plan. "
            "The backend maps the action UUID to its legacy task or recommendation "
            "completion record. Support actions are read-only."
        ),
        request={
            "application/json": {
                "type": "object",
                "properties": {
                    "completion_state": {
                        "type": "string",
                        "enum": ["completed", "skipped", "not_done"],
                    }
                },
                "required": ["completion_state"],
            }
        },
        responses={
            200: DailyActionCompletionResponseSerializer,
            400: ErrorResponseSerializer,
            404: ErrorResponseSerializer,
        },
    )
    def patch(self, request, action_id):
        from api.services.daily_plan import (
            DailyActionCompletionNotAllowed,
            set_daily_action_completion,
        )

        serializer = DailyActionCompletionUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        action = get_object_or_404(
            DailyAction.objects.select_related("plan"),
            id=action_id,
            plan__user=request.user,
        )
        try:
            completion_state = set_daily_action_completion(
                action, serializer.validated_data["completion_state"]
            )
        except DailyActionCompletionNotAllowed as exc:
            return Response(
                {"detail": str(exc)}, status=status.HTTP_400_BAD_REQUEST
            )

        payload = DailyActionCompletionResponseSerializer(
            {"id": action.id, "completion_state": completion_state}
        ).data
        return Response(payload, status=status.HTTP_200_OK)


class DailyTaskListView(APIView):
    permission_classes = [permissions.IsAuthenticated]

    @extend_schema(
        tags=["Wellbeing"],
        summary="Get active daily tasks",
        description="Returns active task definitions ordered by `sort_order` and title. Use `code` values in task completion requests.",
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
        description=(
            "Returns the list of active task codes completed by the user on the requested calendar date, "
            "plus per-category done/total counts for active tasks."
        ),
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
            200: TaskCompletionDaySerializer,
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
        data = {
            "date": parsed_date,
            "tasks": tasks,
            "counts": _task_completion_counts(tasks),
        }
        return Response(TaskCompletionDaySerializer(data).data)

    @extend_schema(
        tags=["Wellbeing"],
        summary="Replace completed daily tasks for date",
        description=(
            "Replaces the completed task set for one calendar date. "
            "Send the full desired list of task `code` values; sending an empty list clears completions for that date. "
            "The response includes per-category done/total counts for active tasks."
        ),
        request=inline_serializer(
            name="TaskCompletionUpsertRequest",
            fields={
                "date": serializers.DateField(),
                "tasks": serializers.ListField(child=serializers.SlugField()),
            },
        ),
        responses={
            201: TaskCompletionDaySerializer,
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
        data["counts"] = _task_completion_counts(data["tasks"])
        return Response(TaskCompletionDaySerializer(data).data, status=201)
