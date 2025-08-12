# demo_interface/serializers.py
from django.contrib.auth import get_user_model
from rest_framework import serializers
from api.models import UserLifeStyle  # поправь импорт под своё расположение моделей

User = get_user_model()


class DemoUserCreateSerializer(serializers.ModelSerializer):
    # по желанию можно требовать пароль через API
    password = serializers.CharField(write_only=True, required=False, allow_blank=True)

    class Meta:
        model = User
        fields = [
            "id",
            "email",
            "name",
            "date_of_birth",
            "height",
            "weight_pre_pregnancy",
            "race",
            "password",
        ]

    def create(self, validated_data):
        password = validated_data.pop("password", None)
        user = User(**validated_data)
        if password:
            user.set_password(password)
        else:
            # безопасный дефолт для dev
            user.set_password("TestUser123!")
        user.save()
        return user


class DemoUserLifeStyleSerializer(serializers.ModelSerializer):
    # По API ожидаем PK пользователя
    user = serializers.PrimaryKeyRelatedField(queryset=User.objects.all())

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
        ]

    def create(self, validated_data):
        # OneToOne: если уже есть — обновим вместо падения
        user = validated_data["user"]
        instance, _created = UserLifeStyle.objects.get_or_create(user=user)
        for k, v in validated_data.items():
            setattr(instance, k, v)
        instance.save()
        return instance
