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
)

from django.contrib.auth import get_user_model

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True, min_length=6)

    class Meta:
        model = User
        fields = ("email", "username", "password")

    def create(self, validated_data):
        return User.objects.create_user(**validated_data)


class PasswordChangeSerializer(serializers.Serializer):
    old_password = serializers.CharField(required=True)
    new_password = serializers.CharField(required=True)


class UserProfileSerializer(serializers.ModelSerializer):
    class Meta:
        model = User
        exclude = ["password", "groups", "user_permissions", "is_superuser", "is_staff"]


class UserLifeStyleSerializer(serializers.ModelSerializer):
    class Meta:
        model = UserLifeStyle
        fields = "__all__"


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


class AirQualityBlockSerializer(serializers.Serializer):
    pm25 = PollutantSerializer()
    pm10 = PollutantSerializer()
    no2 = PollutantSerializer()
    so2 = PollutantSerializer()
    o3 = PollutantSerializer()
    co = PollutantSerializer()
    aqi = serializers.FloatField()


class WeatherBlockSerializer(serializers.Serializer):
    temperature = serializers.FloatField()
    humidity = serializers.FloatField()
    pressure = serializers.FloatField()
    wind_speed = serializers.FloatField()
    condition = serializers.CharField()


class UVBlockSerializer(serializers.Serializer):
    value = serializers.FloatField()
    level = serializers.CharField()


class ExposureLevelSerializer(serializers.Serializer):
    date = serializers.DateField()
    level = serializers.IntegerField()


class ExposureBlockSerializer(serializers.Serializer):
    total_score = serializers.CharField()
    last_updated = serializers.DateTimeField()
    exposure_levels = ExposureLevelSerializer(many=True)


class RisksDeltaSerializer(serializers.Serializer):
    mom = serializers.FloatField()
    baby = serializers.FloatField()


class RecommendationsSerializer(serializers.Serializer):
    mom = serializers.ListField(child=serializers.CharField())
    baby = serializers.ListField(child=serializers.CharField())


class JourneyBlockSerializer(serializers.Serializer):
    length = serializers.FloatField()
    time = serializers.FloatField()


class SummaryResponseSerializer(serializers.Serializer):
    air_quality = AirQualityBlockSerializer()
    weather = WeatherBlockSerializer()
    UV = UVBlockSerializer()
    mom_exposure = ExposureBlockSerializer()
    baby_exposure = ExposureBlockSerializer()
    risks_delta = RisksDeltaSerializer()
    recommendations = RecommendationsSerializer()
    today_journey = JourneyBlockSerializer()
