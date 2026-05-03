# api/serializers.py

from rest_framework import serializers
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
    Wellbeing,
    DailyCheckin,
    DailyTask,
    UserDailyTaskCompletion,
    UserWellbeingLog,
)


from django.utils import timezone
from django.utils.dateparse import parse_datetime
from django.db import transaction


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
    week_of_pregnancy = serializers.IntegerField()

    bmi = serializers.FloatField(read_only=True)

    class Meta:
        model = User
        exclude = [
            "password",
            "groups",
            "user_permissions",
            "is_superuser",
            "is_staff",
        ]
        read_only_fields = (
            "registered_at",
            # "current_pregnancy_week",
            # "pregnancy_start_date",
            "bmi",
        )

    def validate(self, attrs):
        """
        Мягкая логика согласия:
        - если consent=True и consent_accepted_at не передали — ставим сейчас
        - если consent=False — можно (по желанию) чистить consent_accepted_at
        """
        consent = attrs.get("consent", getattr(self.instance, "consent", None))

        # consent_accepted_at в attrs лежит под своим именем (не source)
        consent_accepted_at = attrs.get(
            "consent_accepted_at",
            getattr(self.instance, "consent_accepted_at", None),
        )

        if consent is True and not consent_accepted_at:
            attrs["consent_accepted_at"] = timezone.now()

        if consent is False:
            attrs["consent_accepted_at"] = None

        return attrs


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
    """
    Универсальный сериалайзер для selection POST:
    - symptom_ids: список ID симптомов
    - recorded_at: дата-время пользователя (ISO-8601), опционально
    """

    symptom_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1),
        allow_empty=True,
        required=True,
    )
    recorded_at = serializers.CharField(required=False, allow_blank=False)

    def validate_recorded_at(self, value: str):
        if not value:
            return value
        dt = parse_datetime(value)
        if dt is None:
            raise serializers.ValidationError(
                "Invalid datetime. Use ISO-8601, e.g. 2025-09-01T08:30:00+03:00"
            )
        if timezone.is_naive(dt):
            # Локализуем в settings.TIME_ZONE, если не указана таймзона
            tz = timezone.get_fixed_timezone(
                timezone.get_current_timezone().utcoffset(None).total_seconds() / 60
            )
            # На самом деле лучше settings.TIME_ZONE:
            tz = timezone.get_default_timezone()  # эквивалент settings.TIME_ZONE
            dt = timezone.make_aware(dt, tz)
        return dt

    def to_internal_value(self, data):
        ret = super().to_internal_value(data)
        # Преобразуем recorded_at в aware datetime или None
        ra = data.get("recorded_at")
        if ra:
            ret["recorded_at"] = self.validate_recorded_at(ra)
        else:
            ret["recorded_at"] = timezone.now()
        return ret


class ChecklistItemSerializer(serializers.Serializer):
    id = serializers.IntegerField(allow_null=True)
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


class WeeklyExposureSerializer(serializers.Serializer):
    pregnancy_week = serializers.IntegerField()
    exposure_level = serializers.CharField()


class PollutantSerializer(serializers.Serializer):
    value = serializers.FloatField()
    who_limit = serializers.FloatField(source="who limit")


class SimpleExposureSerializer(serializers.ModelSerializer):
    """
    Минимальный сериалайзер для Exposure.
    Берём только гарантированные поля, чтобы избежать расхождений со схемой.
    """

    class Meta:
        model = Exposure
        fields = ("id", "timestamp", "exposure_level", "risks")


# class RecommendationSerializer(serializers.Serializer):
#     """
#     Отбираем только нужные поля из recommendation-объектов.
#     Остальные ключи игнорируются без ошибок.
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
    """
    Поля, как ты указал:
      - distance_m: округляем и возвращаем как число (float)
      - distance_km: float
      - points: список произвольных dict (оставляем как есть)
    """

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


class TaskCompletionDaySerializer(serializers.Serializer):
    date = serializers.DateField()
    tasks = serializers.ListField(child=serializers.SlugField())


class SummaryResponseSerializer(serializers.Serializer):
    """
    Гибкий ответ для /summary:
    - aq_weather_uv: что вернёт update_air_exposure_log_with_weather (dict) — принимаем как JSON.
    - mom_exposure: последняя экспозиция (может быть None).
    - risks_delta: изменение уровня риска (float | null).
    - recommendations: что вернёт snapshot.recommendations (list|dict) — принимаем как JSON.
    - today_journey: структура маршрута/дня — тоже JSON (dict|list).
    """

    aq_weather_uv = AirExposureLogSerializer()
    mom_exposure = SimpleExposureSerializer(allow_null=True)
    baby_exposure = SimpleExposureSerializer(allow_null=True)

    recommendations = RecommendationSerializer(many=True)

    today_journey = TodayJourneySerializer()
    risks_delta = RiskDeltaSerializer()
    week_info = serializers.JSONField()
    daily_exposure_level = serializers.CharField(allow_null=True)
    daily_checkins = serializers.ListField(child=serializers.DateField())
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
        # На выходе — список объектов согласно RecommendationSerializer
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


class WellbeingItemSerializer(serializers.ModelSerializer):
    class Meta:
        model = Wellbeing
        fields = [
            "id",
            "kind",
            "code",
            "title",
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
    water_amount = serializers.FloatField(required=False, default=0)
    water_unit = serializers.CharField(required=False, default="fl_oz")
    mood_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, default=list
    )
    feeling_ids = serializers.ListField(
        child=serializers.IntegerField(min_value=1), required=False, default=list
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
        log.water_amount = self.validated_data.get("water_amount", log.water_amount)
        log.water_unit = self.validated_data.get("water_unit", log.water_unit)
        log.save()

        log.moods.set(self.validated_data.get("mood_ids", []))
        log.feelings.set(self.validated_data.get("feeling_ids", []))
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
        fields = ("code", "title", "sort_order")


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
