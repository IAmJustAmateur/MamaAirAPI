# views_debug.py
from django.conf import settings
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone

import logging

logger = logging.getLogger(__name__)

from api.models import Exposure  # или AirExposureLog — подставь свою модель

# from api.services.air_exposure_daily import recompute_daily_exposure  # если нужен второй эндпойнт


class IsDebugAndAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        logger.info("Try to authenticate")
        if not (
            getattr(settings, "DEBUG", False)
            or getattr(settings, "DJANGO_ENV", "") in {"dev", "staging"}
        ):
            return False
        return request.user and request.user.is_authenticated and request.user.is_staff


class DebugExposureUpsertSerializer(serializers.Serializer):
    timestamp = serializers.DateTimeField(required=False)
    pollutants = serializers.DictField(
        child=serializers.FloatField(allow_null=False), required=True
    )
    user_email = serializers.EmailField(required=False)  # field for specifying user


class DebugExposureUpsertView(APIView):
    """
    Отладочный upsert Exposure: создаёт свежую запись с заданными агрегатами.
    Доступен только в DEBUG/dev/staging и только для staff.
    """

    permission_classes = [IsDebugAndAdmin]

    def post(self, request):
        from api.models import (
            User,
        )  # импортируем здесь, чтобы избежать циклических импортов

        ser = DebugExposureUpsertSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        user = (
            User.objects.get(email=ser.validated_data.get("user_email"))
            if ser.validated_data.get("user_email")
            else None
        )
        if not user:
            raise serializers.ValidationError("User with specified email not found")
        ts = ser.validated_data.get("timestamp") or timezone.now()
        pollutants = ser.validated_data["pollutants"]
        default_exposure_level = 1
        try:
            exp = Exposure.objects.get(
                user=user,
                timestamp=ts,
            )
            if exp:
                exp.pollutants = pollutants
                exp.save()
            else:
                exp = Exposure.objects.create(
                    user=user,
                    timestamp=ts,
                    exposure_level=default_exposure_level,
                    pollutants=pollutants,  # JSONField со словарём: {"pm25_24h_mean": 15.0, ...}
                )
        except Exposure.DoesNotExist:
            exp = Exposure.objects.create(
                user=user,
                timestamp=ts,
                exposure_level=default_exposure_level,
                pollutants=pollutants,  # JSONField со словарём: {"pm25_24h_mean": 15.0, ...}
            )

        return Response(
            {
                "id": exp.id,
                "timestamp": exp.timestamp.isoformat(),
                "pollutants": exp.pollutants,
            },
            status=status.HTTP_201_CREATED,
        )


class DebugExposureRecomputeView(APIView):
    """
    (Опционально) Запуск серверного пересчёта из движений для текущего юзера.
    """

    permission_classes = [IsDebugAndAdmin]

    def post(self, request):
        # ok = recompute_daily_exposure(request.user)  # если используете реальный сервис
        ok = True
        return Response({"recomputed": bool(ok)}, status=status.HTTP_200_OK)
