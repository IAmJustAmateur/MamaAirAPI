# api/serializers.py

from rest_framework import serializers
from drf_spectacular.utils import extend_schema_field
from .models import (
    User,
    UserLifeStyle,
    UserMommySymptoms,
    UserBabySymptoms,
    Movement,
    HealthInsightSnapshot,
    AirExposureLog,
    AdviceTemplate,
    Exposure,
    RecommendationCompletion,
    DailyAction,
    DailyPlan,
    Wellbeing,
    DailyCheckin,
    DailyTask,
    UserDailyTaskCompletion,
    UserWellbeingLog,
    EXPOSURE_LEVEL_CHOICES,
)


from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.db import transaction
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ("email", "password")

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)


class UserProfileSerializer(serializers.ModelSerializer):
    week_of_pregnancy = serializers.IntegerField(required=False, allow_null=True)
    pregnancy_number = serializers.IntegerField(
        required=False, allow_null=True, min_value=1
    )
    avatar_url = serializers.URLField(allow_null=True, required=False)

    bmi = serializers.FloatField(read_only=True)

    class Meta:
        model = User
        exclude = [
            "password",
            "groups",
            "user_permissions",
            "is_superuser",
            "is_staff",
            "avatar",
        ]
        read_only_fields = (
            "registered_at",
            # "current_pregnancy_week",
            # "pregnancy_start_date",
            "bmi",
        )

    def validate(self, attrs):
        """Set or clear the consent timestamp consistently with consent."""
        consent = attrs.get("consent", getattr(self.instance, "consent", None))

        # attrs uses the field name rather than its source.
        consent_accepted_at = attrs.get(
            "consent_accepted_at",
            getattr(self.instance, "consent_accepted_at", None),
        )

        if consent is True and not consent_accepted_at:
            attrs["consent_accepted_at"] = timezone.now()

        if consent is False:
            attrs["consent_accepted_at"] = None

        return attrs

    def validate_timezone(self, value):
        if value in (None, ""):
            return None
        try:
            ZoneInfo(value)
        except ZoneInfoNotFoundError:
            raise serializers.ValidationError(
                "Invalid timezone. Use an IANA timezone, e.g. Europe/Minsk."
            )
        return value

    def validate(self, attrs):
        """
        Consent and onboarding field consistency:
        - set consent_accepted_at automatically when consent becomes true
        - keep notification window as a complete same-day HH:MM interval
        - mirror pregnancy_number into legacy is_first_pregnancy
        """
        attrs = super().validate(attrs) if hasattr(super(), "validate") else attrs
        consent = attrs.get("consent", getattr(self.instance, "consent", None))

        consent_accepted_at = attrs.get(
            "consent_accepted_at",
            getattr(self.instance, "consent_accepted_at", None),
        )

        if consent is True and not consent_accepted_at:
            attrs["consent_accepted_at"] = timezone.now()

        if consent is False:
            attrs["consent_accepted_at"] = None

        window_from = attrs.get(
            "notification_window_from",
            getattr(self.instance, "notification_window_from", None),
        )
        window_to = attrs.get(
            "notification_window_to",
            getattr(self.instance, "notification_window_to", None),
        )
        if (window_from is None) != (window_to is None):
            raise serializers.ValidationError(
                {
                    "notification_window": (
                        "notification_window_from and notification_window_to "
                        "must be provided together."
                    )
                }
            )
        if window_from is not None and window_to is not None and window_from >= window_to:
            raise serializers.ValidationError(
                {
                    "notification_window_to": (
                        "Must be later than notification_window_from."
                    )
                }
            )

        if "pregnancy_number" in attrs and attrs["pregnancy_number"] is not None:
            attrs["is_first_pregnancy"] = attrs["pregnancy_number"] == 1

        return attrs

    def to_representation(self, instance):
        data = super().to_representation(instance)
        if instance.avatar:
            request = self.context.get("request")
            avatar_url = instance.avatar.url
            if request is not None:
                avatar_url = request.build_absolute_uri(avatar_url)
            data["avatar_url"] = avatar_url
        return data


class UserAvatarUploadSerializer(serializers.Serializer):
    avatar = serializers.ImageField(write_only=True)

    allowed_content_types = {
        "image/jpeg": "jpg",
        "image/png": "png",
        "image/webp": "webp",
    }
    max_size_bytes = 5 * 1024 * 1024

    def validate_avatar(self, value):
        content_type = getattr(value, "content_type", "")
        if content_type not in self.allowed_content_types:
            raise serializers.ValidationError(
                "Unsupported image type. Use JPEG, PNG, or WebP."
            )
        if value.size > self.max_size_bytes:
            raise serializers.ValidationError("Avatar image must be 5 MB or smaller.")
        value.name = f"avatar.{self.allowed_content_types[content_type]}"
        return value


class UserLifeStyleSerializer(serializers.ModelSerializer):
    user = serializers.PrimaryKeyRelatedField(read_only=True)

    class Meta:
        model = UserLifeStyle
        fields = [
            "id",
            "user",
            "average_sleep_hours",
            "work_type",
            "diet_type",
            "cooking_method",
            "activity_duration_minutes",
            "work_schedule_pattern",
            "standing_hours_per_day",
            "area",
            "time_spent",
            "time_of_day",
            # new fields
            "commute_mode",
            "hydration_target_ml_per_day",
            "sleep_target_window",
            "rest_microbreak_preference",
            "supplement_preferences",
            "cooking_venue",
            "ventilation_level",
        ]


class SymptomSelectionSerializer(serializers.Serializer):
    """Validate symptom IDs and an optional ISO-8601 user timestamp."""

    symptom_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=True,
        required=True,
    )
    recorded_at = serializers.CharField(required=False, allow_blank=False)
    checklist_id = serializers.UUIDField(required=False, allow_null=True)

    def validate_recorded_at(self, value: str):
        if not value:
            return value
        dt = parse_datetime(value)
        if dt is None:
            raise serializers.ValidationError(
                "Invalid datetime. Use ISO-8601, e.g. 2025-09-01T08:30:00+03:00"
            )
        if timezone.is_naive(dt):
            from recommendations.services.symptom_monitoring import get_user_timezone

            user = self.context.get("user")
            tz = get_user_timezone(user) if user else timezone.get_default_timezone()
            dt = timezone.make_aware(dt, tz)
        return dt

    def to_internal_value(self, data):
        ret = super().to_internal_value(data)
        # Convert recorded_at to an aware datetime or None.
        ra = data.get("recorded_at")
        if ra:
            ret["recorded_at"] = self.validate_recorded_at(ra)
        else:
            ret["recorded_at"] = timezone.now()
        return ret


class ChecklistItemSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    code = serializers.CharField()
    name = serializers.CharField()


class UserMommySymptomsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserMommySymptoms
        fields = "__all__"


class UserBabySymptomsSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserBabySymptoms
        fields = "__all__"


class MovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Movement
        fields = "__all__"


class HealthInsightSerializer(serializers.ModelSerializer):
    class Meta:
        model = HealthInsightSnapshot
        exclude = ["user"]


class AirExposureLogSerializer(serializers.ModelSerializer):
    class Meta:
        model = AirExposureLog
        exclude = ["user"]


class AdviceTemplateSerializer(serializers.ModelSerializer):
    class Meta:
        model = AdviceTemplate
        fields = ["id", "title", "text", "category"]


class LogoutSerializer(serializers.Serializer):
    refresh = serializers.CharField()


class ErrorResponseSerializer(serializers.Serializer):
    error = serializers.CharField()


WEEKLY_EXPOSURE_LEVEL_VALUES = [
    value for value, _label in EXPOSURE_LEVEL_CHOICES
]


class WeeklyExposureLevelSerializer(serializers.Serializer):
    level = serializers.ChoiceField(
        choices=WEEKLY_EXPOSURE_LEVEL_VALUES,
        help_text="Exposure classification for the pregnancy week.",
    )


class WeeklyExposureResponseSerializer(serializers.DictField):
    """Validate the existing dynamic pregnancy-week response map."""

    child = WeeklyExposureLevelSerializer()


WEEKLY_EXPOSURE_RESPONSE_SCHEMA = {
    "type": "object",
    "description": (
        "Map of decimal pregnancy-week keys to weekly exposure classifications."
    ),
    "additionalProperties": {
        "type": "object",
        "additionalProperties": False,
        "required": ["level"],
        "properties": {
            "level": {
                "type": "string",
                "enum": WEEKLY_EXPOSURE_LEVEL_VALUES,
                "description": "Exposure classification for the pregnancy week.",
            }
        },
    },
}


class PollutantSerializer(serializers.Serializer):
    value = serializers.FloatField()
    who_limit = serializers.FloatField(source="who limit")


class ExposureRiskMapField(serializers.DictField):
    """Describe calculated risk scores without changing their JSON representation."""

    child = serializers.FloatField()

    def to_representation(self, value):
        return value


class SimpleExposureSerializer(serializers.ModelSerializer):
    """Expose only guaranteed Exposure fields to keep the schema stable."""

    risks = ExposureRiskMapField()

    class Meta:
        model = Exposure
        fields = ("id", "timestamp", "exposure_level", "risks")


# class RecommendationSerializer(serializers.Serializer):
#     """
#     Select only supported fields from recommendation objects.
#     Ignore all other keys without raising validation errors.
#     """

#     id = serializers.CharField()
#     severity = serializers.CharField()
#     title = serializers.CharField()
#     message = serializers.CharField()
#     ttl_hours = serializers.IntegerField()
#     priority = serializers.IntegerField()


class RiskDeltaSerializer(serializers.Serializer):
    mom = serializers.FloatField(allow_null=True)
    baby = serializers.FloatField(allow_null=True)


class TodayJourneySerializer(serializers.Serializer):
    """Serialize journey distance and the unmodified list of route points."""

    distance_m = serializers.FloatField()
    distance_km = serializers.FloatField()


class ExposureHistoryItemSerializer(serializers.Serializer):
    date = serializers.DateField(source="timestamp")
    integrated_score = serializers.FloatField(source="exposure_level")


class ExposureHistoryResponseSerializer(serializers.Serializer):
    start_date = serializers.DateField()
    end_date = serializers.DateField()
    days_requested = serializers.IntegerField()
    items = ExposureHistoryItemSerializer(many=True)


class PollutantComplianceItemSerializer(serializers.Serializer):
    value = serializers.FloatField(allow_null=True)
    label = serializers.CharField()
    unit = serializers.CharField()
    avg_period_used = serializers.CharField()
    value_source = serializers.CharField()
    value_datetime = serializers.CharField(allow_null=True)
    limit = serializers.FloatField()
    limit_unit = serializers.CharField()
    limit_avg_period = serializers.CharField()
    compliance = serializers.BooleanField(allow_null=True)
    exceedance_pct = serializers.FloatField(allow_null=True)
    approximate = serializers.BooleanField()


class PollutantComplianceSerializer(serializers.Serializer):
    source = serializers.CharField()
    version = serializers.CharField()
    per_pollutant = serializers.DictField(child=PollutantComplianceItemSerializer())


class RecommendationSerializer(serializers.Serializer):
    id = serializers.CharField()
    rule_id = serializers.CharField(required=False, allow_blank=True)
    version = serializers.IntegerField(required=False)

    severity = serializers.CharField(required=False, allow_blank=True)
    category = serializers.CharField(required=False, allow_blank=True)
    priority = serializers.IntegerField(required=False)

    title = serializers.CharField(required=False, allow_blank=True)

    alert = serializers.CharField(required=False, allow_blank=True)

    recommendation_diet = serializers.CharField(required=False, allow_blank=True)
    recommendation_activity = serializers.CharField(required=False, allow_blank=True)
    recommendation_behavior = serializers.CharField(required=False, allow_blank=True)

    ttl_hours = serializers.IntegerField(required=False)

    # IMPORTANT: keep as string because snapshot stores JSON
    expires_at = serializers.CharField(required=False, allow_blank=True)

    sources = serializers.ListField(child=serializers.CharField(), required=False)
    engine_version = serializers.CharField(required=False, allow_blank=True)

    # Backward compatibility
    message = serializers.CharField(required=False, allow_blank=True)

    def to_representation(self, instance):
        data = super().to_representation(instance)

        # old -> new
        if not data.get("alert") and data.get("message"):
            data["alert"] = data["message"]

        # new -> old (temporary, for mobile)
        if not data.get("message") and data.get("alert"):
            data["message"] = data["alert"]

        return data


class HealthInsightResponseSerializer(serializers.ModelSerializer):
    """OpenAPI-only contract for the existing health insight response."""

    recommendations = RecommendationSerializer(many=True)

    class Meta:
        model = HealthInsightSnapshot
        exclude = ["user"]


class TaskCompletionCategoryCountSerializer(serializers.Serializer):
    done = serializers.IntegerField()
    total = serializers.IntegerField()


class TaskCompletionCountsSerializer(serializers.Serializer):
    diet = TaskCompletionCategoryCountSerializer()
    activity = TaskCompletionCategoryCountSerializer()
    behavior = TaskCompletionCategoryCountSerializer()
    mental = TaskCompletionCategoryCountSerializer()


class TaskCompletionDaySerializer(serializers.Serializer):
    date = serializers.DateField()
    tasks = serializers.ListField(child=serializers.SlugField())
    counts = TaskCompletionCountsSerializer()


class WeekInfoSerializer(serializers.Serializer):
    week = serializers.IntegerField(min_value=1, max_value=40)
    locale = serializers.CharField()
    text = serializers.CharField()
    source = serializers.ChoiceField(choices=["db"])


class SummaryWaterSerializer(serializers.Serializer):
    date = serializers.DateField()
    amount = serializers.FloatField(min_value=0)
    unit = serializers.CharField()


class SummaryResponseSerializer(serializers.Serializer):
    """Existing mobile dashboard response contract."""

    aq_weather_uv = AirExposureLogSerializer()
    mom_exposure = SimpleExposureSerializer(allow_null=True)
    baby_exposure = SimpleExposureSerializer(allow_null=True)

    recommendations = RecommendationSerializer(many=True)

    today_journey = TodayJourneySerializer()
    risks_delta = RiskDeltaSerializer()
    week_info = WeekInfoSerializer(allow_null=True)
    daily_exposure_level = serializers.ChoiceField(
        choices=WEEKLY_EXPOSURE_LEVEL_VALUES,
        allow_null=True,
    )
    daily_checkins = serializers.ListField(child=serializers.DateField())
    water = SummaryWaterSerializer()
    task_completions = TaskCompletionDaySerializer(many=True)
    exposure_history = ExposureHistoryResponseSerializer()
    pollutant_compliance = PollutantComplianceSerializer()

    snapshot_id = serializers.IntegerField()
    snapshot_created_at = serializers.CharField()

    def get_recommendations(self, obj):
        """
        Return a list of recommendation objects based on obj["recommendations"].
        If obj["recommendations"] is a dictionary, it is expected to have an "items" key.
        The returned list is serialized according to RecommendationSerializer.
        """
        recs = obj.get("recommendations", [])
        if isinstance(recs, dict):
            recs = recs.get("items", [])
        # Return objects that conform to RecommendationSerializer.
        return RecommendationSerializer(recs, many=True).data

    def get_exposure_history(self, obj):
        """
        Return a list of exposure history items based on obj["exposure_history"].
        The returned list is serialized according to ExposureHistoryItemSerializer.
        """
        history = obj.get("exposure_history", [])
        return ExposureHistoryItemSerializer(history, many=True).data


class GoogleAuthRequestSerializer(serializers.Serializer):
    id_token = serializers.CharField(
        write_only=True, help_text="Google ID token from Android app"
    )


class GoogleAuthUserSerializer(serializers.Serializer):
    id = serializers.IntegerField()
    email = serializers.EmailField()
    name = serializers.CharField(allow_blank=True)
    avatar_url = serializers.URLField(allow_null=True, required=False)
    provider = serializers.CharField()


class GoogleAuthResponseSerializer(serializers.Serializer):
    access = serializers.CharField()
    refresh = serializers.CharField()
    user = GoogleAuthUserSerializer()


class ErrorSerializer(serializers.Serializer):
    detail = serializers.CharField()


class RecommendationCompletionUpsertSerializer(serializers.Serializer):
    snapshot_id = serializers.IntegerField()
    rule_id = serializers.CharField(max_length=128)
    rule_version = serializers.IntegerField(min_value=1, default=1)
    dimension = serializers.ChoiceField(
        choices=[c[0] for c in RecommendationCompletion.DIMENSION_CHOICES]
    )
    status = serializers.ChoiceField(
        choices=[c[0] for c in RecommendationCompletion.STATUS_CHOICES], default="done"
    )

    def validate_snapshot_id(self, value):
        request = self.context["request"]
        if not HealthInsightSnapshot.objects.filter(
            id=value, user=request.user
        ).exists():
            raise serializers.ValidationError("Snapshot not found for this user.")
        return value


class RecommendationCompletionValidationErrorSerializer(serializers.Serializer):
    """Field-level validation errors returned by the completion endpoint."""

    snapshot_id = serializers.ListField(
        child=serializers.CharField(), required=False
    )
    rule_id = serializers.ListField(child=serializers.CharField(), required=False)
    rule_version = serializers.ListField(
        child=serializers.CharField(), required=False
    )
    dimension = serializers.ListField(child=serializers.CharField(), required=False)
    status = serializers.ListField(child=serializers.CharField(), required=False)
    non_field_errors = serializers.ListField(
        child=serializers.CharField(), required=False
    )


class RecommendationCompletionSerializer(serializers.ModelSerializer):
    snapshot_id = serializers.IntegerField(read_only=True)

    class Meta:
        model = RecommendationCompletion
        fields = [
            "id",
            "snapshot_id",
            "rule_id",
            "rule_version",
            "dimension",
            "status",
            "created_at",
            "updated_at",
        ]


class DailyActionResponseSerializer(serializers.ModelSerializer):
    completion_state = serializers.SerializerMethodField()

    class Meta:
        model = DailyAction
        fields = [
            "id",
            "domain",
            "title",
            "description",
            "timing",
            "duration_minutes",
            "context",
            "completion_state",
        ]

    @extend_schema_field(
        serializers.ChoiceField(choices=["not_done", "completed", "skipped"])
    )
    def get_completion_state(self, obj):
        return self.context["completion_states"].get(str(obj.id), "not_done")


class DailySupportActionResponseSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyAction
        fields = [
            "id",
            "domain",
            "title",
            "description",
            "timing",
            "duration_minutes",
            "context",
        ]


class DailyPlanResponseSerializer(serializers.ModelSerializer):
    date = serializers.DateField(source="local_date")
    primary_actions = serializers.SerializerMethodField()
    additional_actions = serializers.SerializerMethodField()
    support_actions = serializers.SerializerMethodField()

    class Meta:
        model = DailyPlan
        fields = [
            "date",
            "timezone",
            "primary_actions",
            "additional_actions",
            "support_actions",
        ]

    def _actions_for_role(self, obj, role):
        actions = [action for action in obj.actions.all() if action.role == role]
        serializer_class = (
            DailySupportActionResponseSerializer
            if role == "support"
            else DailyActionResponseSerializer
        )
        return serializer_class(actions, many=True, context=self.context).data

    @extend_schema_field(DailyActionResponseSerializer(many=True))
    def get_primary_actions(self, obj):
        return self._actions_for_role(obj, "primary")

    @extend_schema_field(DailyActionResponseSerializer(many=True))
    def get_additional_actions(self, obj):
        return self._actions_for_role(obj, "additional")

    @extend_schema_field(DailySupportActionResponseSerializer(many=True))
    def get_support_actions(self, obj):
        return self._actions_for_role(obj, "support")


class WellbeingItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wellbeing
        fields = [
            "id",
            "kind",
            "code",
            "title",
            "emoji",
            "sort_order",
            "number_value",
            "unit",
            "is_active",
        ]


class UserWellbeingLogSerializer(serializers.ModelSerializer):
    moods = WellbeingItemSerializer(many=True)
    feelings = WellbeingItemSerializer(many=True)

    class Meta:
        model = UserWellbeingLog
        fields = ["date", "water_amount", "water_unit", "moods", "feelings"]


class UserWellbeingLogUpsertSerializer(serializers.Serializer):
    date = serializers.DateField()
    water_amount = serializers.FloatField(required=False, min_value=0)
    water_unit = serializers.CharField(required=False, default="ml")
    mood_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False
    )
    feeling_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False
    )

    def validate(self, attrs):
        mood_ids = set(attrs.get("mood_ids", []))
        feeling_ids = set(attrs.get("feeling_ids", []))

        if mood_ids:
            ok = Wellbeing.objects.filter(
                id__in=mood_ids, kind="mood", is_active=True
            ).count()
            if ok != len(mood_ids):
                raise serializers.ValidationError(
                    "Some mood_ids not found/inactive or wrong kind."
                )

        if feeling_ids:
            ok = Wellbeing.objects.filter(
                id__in=feeling_ids, kind="feeling", is_active=True
            ).count()
            if ok != len(feeling_ids):
                raise serializers.ValidationError(
                    "Some feeling_ids not found/inactive or wrong kind."
                )

        return attrs

    def save(self, **kwargs):
        user = self.context["request"].user
        date = self.validated_data["date"]

        log, _ = UserWellbeingLog.objects.get_or_create(user=user, date=date)
        if "water_amount" in self.validated_data:
            log.water_amount += self.validated_data["water_amount"]
        log.water_unit = self.validated_data.get("water_unit", log.water_unit)
        log.save()

        if "mood_ids" in self.validated_data:
            log.moods.set(self.validated_data["mood_ids"])
        if "feeling_ids" in self.validated_data:
            log.feelings.set(self.validated_data["feeling_ids"])
        return log


class DailyCheckinSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyCheckin
        fields = ("id", "date", "created_at")
        read_only_fields = ("id", "created_at")


class DailyCheckinCreateSerializer(serializers.Serializer):
    date = serializers.DateField()

    def validate(self, attrs):
        user = self.context["request"].user
        if DailyCheckin.objects.filter(user=user, date=attrs["date"]).exists():
            raise serializers.ValidationError(
                {"date": "DailyCheckin for this date already exists."}
            )
        return attrs

    def create(self, validated_data):
        user = self.context["request"].user
        return DailyCheckin.objects.create(user=user, **validated_data)


class DailyTaskSerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyTask
        fields = ("code", "title", "category", "sort_order")


class TaskCompletionUpsertSerializer(serializers.Serializer):
    date = serializers.DateField()
    tasks = serializers.ListField(
        child=serializers.SlugField(max_length=64),
        allow_empty=True,
    )

    def validate_tasks(self, value):
        codes = list(dict.fromkeys(value))
        found = set(
            DailyTask.objects.filter(code__in=codes, is_active=True).values_list(
                "code", flat=True
            )
        )
        missing = [code for code in codes if code not in found]
        if missing:
            raise serializers.ValidationError(
                f"Unknown or inactive task code(s): {', '.join(missing)}"
            )
        return codes

    def save(self, **kwargs):
        user = self.context["request"].user
        date = self.validated_data["date"]
        task_codes = self.validated_data["tasks"]
        tasks_by_code = DailyTask.objects.in_bulk(task_codes, field_name="code")

        with transaction.atomic():
            UserDailyTaskCompletion.objects.filter(user=user, date=date).update(
                completed=False
            )
            for code in task_codes:
                UserDailyTaskCompletion.objects.update_or_create(
                    user=user,
                    task=tasks_by_code[code],
                    date=date,
                    defaults={"completed": True},
                )

        return {"date": date, "tasks": task_codes}
