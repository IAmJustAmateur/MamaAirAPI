# api/views.py

import io
import pandas as pd
from datetime import datetime, timedelta

from rest_framework import status, generics, permissions
from rest_framework.response import Response
from rest_framework.parsers import MultiPartParser
from rest_framework_simplejwt.views import TokenObtainPairView
from rest_framework_simplejwt.serializers import TokenObtainPairSerializer

from django.utils import timezone

from .models import Movement, DailyExposureSummary
from .serializers import (
    RegisterSerializer,
    MovementUploadSerializer,
    DailyExposureSummarySerializer,
)
from django.contrib.auth import get_user_model
from api.aq_utils import fetch_air_quality_data
from api.risks import assess_risks

User = get_user_model()


# 1) Регистрация
class RegisterView(generics.CreateAPIView):
    serializer_class = RegisterSerializer
    permission_classes = []  # без авторизации можно

    def post(self, request, *args, **kwargs):
        return super().post(request, *args, **kwargs)


# 2) Логин (JWT ObtainPair)
class LoginView(TokenObtainPairView):
    permission_classes = []  # без авторизации можно
    # опционально, если нужно поменять сериализатор, но дефолтный подходит
    # serializer_class = YourCustomTokenSerializer


# 3) Загрузка CSV с перемещениями
class MovementUploadView(generics.GenericAPIView):
    serializer_class = MovementUploadSerializer
    permission_classes = [permissions.IsAuthenticated]
    parser_classes = [MultiPartParser]

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        f = serializer.validated_data["file"]
        content = f.read().decode("utf-8")
        df = pd.read_csv(io.StringIO(content))

        # Сохраняем движения в БД
        objs = []
        for _, row in df.iterrows():
            objs.append(
                Movement(
                    user=request.user,
                    latitude=row["latitude"],
                    longitude=row["longitude"],
                    timestamp=row["timestamp"],
                )
            )
        Movement.objects.bulk_create(objs)

        return Response({"message": "Data saved"}, status=status.HTTP_201_CREATED)


# 4) Анализ (аналог /analyze)
class AnalyzeView(generics.GenericAPIView):
    permission_classes = [permissions.IsAuthenticated]

    def get(self, request, *args, **kwargs):
        user = request.user
        # 1) Загружаем движения за последние 2 дня
        now = timezone.now()
        two_days_ago = now - timedelta(days=2)
        movements_qs = Movement.objects.filter(user=user, timestamp__gte=two_days_ago)

        if not movements_qs.exists():
            return Response(
                {"message": "No recent data (last 2 days) available for analysis."},
                status=status.HTTP_404_NOT_FOUND,
            )

        # Преобразуем в DataFrame
        data = list(movements_qs.values("latitude", "longitude", "timestamp"))
        df = pd.DataFrame(data)
        df["timestamp"] = pd.to_datetime(df["timestamp"])

        latest_ts = df["timestamp"].max()
        if latest_ts.date() < (now.date() - timedelta(days=1)):
            return Response(
                {"message": "Last timestamp is too old. Must be today or yesterday."},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # 2) Обогащаем данными о качестве воздуха
        enriched = fetch_air_quality_data(
            df
        )  # ваша функция должна возвращать DataFrame с колонками PM2.5, NO2, O3
        result = assess_risks(enriched)

        # 3) Сохраняем summary
        summary_data = {
            "user": user,
            "analysis_date": latest_ts.date(),
            "pm25_avg": float(result["exposure"]["pm25"]),
            "no2_peak": float(enriched["NO2"].max()),
            "o3_peak": float(enriched["O3"].max()),
            "exposure_hours": result["exposure"]["outdoor_time"],
            "fetal_risk_score": result["summary"]["fetal_risk_score"],
            "pdf": None,
        }
        # upsert: если уже была запись за тот же день, обновляем; иначе создаём новую
        existing = DailyExposureSummary.objects.filter(
            user=user, analysis_date=latest_ts.date()
        ).first()
        if existing:
            for attr, val in summary_data.items():
                setattr(existing, attr, val)
            existing.save()
            summary_obj = existing
        else:
            summary_obj = DailyExposureSummary.objects.create(**summary_data)

        # 4) Отдаём JSON-ответ (опционально сериализуем)
        serializer = DailyExposureSummarySerializer(summary_obj)
        return Response(serializer.data, status=status.HTTP_200_OK)
