# auth_views.py
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, throttling
from django.contrib.auth import get_user_model
from django.conf import settings

from google.oauth2 import id_token
from google.auth.transport import requests as google_requests
from rest_framework_simplejwt.tokens import RefreshToken

from drf_spectacular.utils import extend_schema, OpenApiResponse, OpenApiExample
from .serializers import (
    GoogleAuthRequestSerializer,
    GoogleAuthResponseSerializer,
    ErrorSerializer,
)

User = get_user_model()


def verify_id_token(token_str: str) -> dict:
    # Реальная проверка токена подписью Google
    return id_token.verify_oauth2_token(
        token_str, google_requests.Request(), audience=None
    )


def get_allowed_auds():
    raw = getattr(settings, "GOOGLE_ALLOWED_AUDS", "")
    return {x.strip() for x in raw.split(",") if x.strip()}


class SigninThrottle(throttling.AnonRateThrottle):
    scope = "signin"


@extend_schema(
    tags=["Auth"],
    operation_id="auth_google_sign_in",
    summary="Sign in with Google (Android)",
    description=(
        "Принимает Google **ID token** с клиента (Android), проверяет его на сервере, "
        "создаёт/связывает пользователя и выдаёт ваши JWT (access/refresh)."
    ),
    request=GoogleAuthRequestSerializer,
    responses={
        200: OpenApiResponse(
            response=GoogleAuthResponseSerializer, description="Успешная аутентификация"
        ),
        400: OpenApiResponse(
            response=ErrorSerializer, description="Некорректный запрос (нет id_token)"
        ),
        401: OpenApiResponse(
            response=ErrorSerializer,
            description="Проблемы валидации токена Google (aud/iss/expired/email_verified)",
        ),
    },
    examples=[
        OpenApiExample(
            "Успешный запрос",
            value={"id_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."},
            request_only=True,
        ),
        OpenApiExample(
            "Успешный ответ",
            value={
                "access": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                "refresh": "eyJ0eXAiOiJKV1QiLCJhbGciOiJIUzI1NiJ9...",
                "user": {
                    "id": 123,
                    "email": "user@example.com",
                    "name": "Jane Doe",
                    "avatar_url": "https://lh3.googleusercontent.com/...",
                    "provider": "google",
                },
            },
            response_only=True,
        ),
        OpenApiExample(
            "Ошибка: некорректная аудитория",
            value={"detail": "Invalid audience"},
            response_only=True,
            status_codes=["401"],
        ),
    ],
)
class GoogleAuthView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = [SigninThrottle]

    def post(self, request):
        token_str = request.data.get("id_token")
        if not token_str:
            return Response({"detail": "id_token is required"}, status=400)

        try:
            info = verify_id_token(token_str)
        except Exception:
            return Response({"detail": "Invalid Google token"}, status=401)

        aud = info.get("aud")
        if aud not in get_allowed_auds():
            return Response({"detail": "Invalid audience"}, status=401)

        if info.get("iss") not in [
            "https://accounts.google.com",
            "accounts.google.com",
        ]:
            return Response({"detail": "Invalid issuer"}, status=401)

        if not info.get("email"):
            return Response({"detail": "Email missing"}, status=401)

        if not info.get("email_verified", False):
            return Response({"detail": "Email not verified"}, status=401)

        google_sub = info.get("sub")
        email = info["email"].lower()
        name = info.get("name") or ""
        picture = info.get("picture")

        user = None
        if google_sub:
            user = User.objects.filter(google_sub=google_sub).first()
        if not user:
            user = User.objects.filter(email=email).first()
            if user:
                user.google_sub = google_sub
                user.auth_provider = "google"
                if picture and not getattr(user, "avatar_url", None):
                    user.avatar_url = picture
                if name and not user.first_name:
                    user.first_name = name
                user.save()
            else:
                user = User.objects.create(
                    email=email,
                    google_sub=google_sub,
                    auth_provider="google",
                    avatar_url=picture or None,
                    is_active=True,
                )

        refresh = RefreshToken.for_user(user)
        return Response(
            {
                "access": str(refresh.access_token),
                "refresh": str(refresh),
                "user": {
                    "id": user.id,
                    "email": user.email,
                    "avatar_url": getattr(user, "avatar_url", None),
                    "provider": getattr(user, "auth_provider", "google"),
                },
            },
            status=200,
        )
