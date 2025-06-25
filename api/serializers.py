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
)


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
