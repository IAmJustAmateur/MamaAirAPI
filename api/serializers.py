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
)

from django.contrib.auth import get_user_model
from django.utils import timezone
from django.utils.dateparse import parse_datetime

User = get_user_model()


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
    current_pregnancy_week = serializers.IntegerField(
        source="current_week_of_pregnancy", read_only=True
    )
    pregnancy_start_date = serializers.DateField(read_only=True)

    read_only_fields = ("current_pregnancy_week", "pregnancy_start_date")

    class Meta:
        model = User
        exclude = ["password", "groups", "user_permissions", "is_superuser", "is_staff"]


class UserLifeStyleSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserLifeStyle
        fields = "__all__"


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


class RecommendationSerializer(serializers.Serializer):
    """
    Отбираем только нужные поля из recommendation-объектов.
    Остальные ключи игнорируются без ошибок.
    """

    id = serializers.CharField()
    severity = serializers.CharField()
    title = serializers.CharField()
    message = serializers.CharField()
    ttl_hours = serializers.IntegerField()
    priority = serializers.IntegerField()


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
    risks_delta = serializers.FloatField(allow_null=True)
    recommendations = serializers.SerializerMethodField()
    today_journey = TodayJourneySerializer()
    risks_delta = RiskDeltaSerializer()
    mama_air_speaks = serializers.JSONField()
    exposure_history = ExposureHistoryResponseSerializer()
    pollutant_compliance = PollutantComplianceSerializer()

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
