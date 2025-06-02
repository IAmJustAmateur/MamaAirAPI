# api/serializers.py

from rest_framework import serializers
from django.contrib.auth import get_user_model
from .models import Movement, DailyExposureSummary

User = get_user_model()


class RegisterSerializer(serializers.ModelSerializer):
    password = serializers.CharField(write_only=True)

    class Meta:
        model = User
        fields = ("email", "username", "password")

    def create(self, validated_data):
        user = User.objects.create_user(
            email=validated_data["email"],
            username=validated_data["username"],
            password=validated_data["password"],
        )
        return user


class MovementUploadSerializer(serializers.Serializer):
    file = serializers.FileField()


class DailyExposureSummarySerializer(serializers.ModelSerializer):
    class Meta:
        model = DailyExposureSummary
        fields = (
            "user",
            "analysis_date",
            "pm25_avg",
            "no2_peak",
            "o3_peak",
            "exposure_hours",
            "fetal_risk_score",
            "pdf",
        )


class MovementSerializer(serializers.ModelSerializer):
    class Meta:
        model = Movement
        fields = ("user", "latitude", "longitude", "timestamp")
