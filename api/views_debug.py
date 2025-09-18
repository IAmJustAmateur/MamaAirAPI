# views_debug.py
from django.conf import settings
from rest_framework import permissions, serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView
from django.utils import timezone

from api.models import Exposure  # или AirExposureLog — подставь свою модель

# from api.services.air_exposure_daily import recompute_daily_exposure  # если нужен второй эндпойнт


class IsDebugAndAdmin(permissions.BasePermission):
    def has_permission(self, request, view):
        if not (
            getattr(settings, "DEBUG", False)
            or getattr(settings, "ENV", "") in {"dev", "staging"}
        ):
            return False
        return request.user and request.user.is_authenticated and request.user.is_staff


class DebugExposureUpsertSerializer(serializers.Serializer):
    timestamp = serializers.DateTimeField(required=False)
    pollutants = serializers.DictField(
        child=serializers.FloatField(allow_null=False), required=True
    )


class DebugExposureUpsertView(APIView):
    """
    Отладочный upsert Exposure: создаёт свежую запись с заданными агрегатами.
    Доступен только в DEBUG/dev/staging и только для staff.
    """

    permission_classes = [IsDebugAndAdmin]

    def post(self, request):
        ser = DebugExposureUpsertSerializer(data=request.data)
        ser.is_valid(raise_exception=True)
        ts = ser.validated_data.get("timestamp") or timezone.now()
        pollutants = ser.validated_data["pollutants"]

        exp = Exposure.objects.create(
            user=request.user,
            timestamp=ts,
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
