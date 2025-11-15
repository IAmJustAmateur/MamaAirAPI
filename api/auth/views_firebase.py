# auth/views_firebase.py
from django.contrib.auth import get_user_model
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status, throttling
from firebase_admin import auth as fb_auth
from rest_framework_simplejwt.tokens import RefreshToken

from logging import getLogger

logger = getLogger(__name__)

User = get_user_model()


class SigninThrottle(throttling.AnonRateThrottle):
    scope = "signin"


class FirebaseAuthView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = [SigninThrottle]

    def post(self, request):
        token = request.data.get("id_token")
        if not token:
            return Response({"detail": "id_token is required"}, status=400)

        try:
            # Проверка подписи и клеймов Firebase ID Token
            decoded = fb_auth.verify_id_token(
                token
            )  # при необходимости: check_revoked=True
            logger.info(f"Decoded Firebase token: {decoded}")
        except Exception:
            logger.exception("Failed to verify Firebase token")
            return Response({"detail": "Invalid Firebase token"}, status=401)

        uid = decoded["uid"]
        email = (decoded.get("email") or "").lower()
        email_verified = decoded.get("email_verified", False)
        name = decoded.get("name") or ""
        picture = decoded.get("picture")

        # if not email or not email_verified:
        #     return Response({"detail": "Email missing or not verified"}, status=401)
        if not email:
            return Response({"detail": "Email missing or not verified"}, status=401)

        # Линкуем/создаём юзера у себя
        user = User.objects.filter(email=email).first()
        if user:
            # можно хранить связь с Firebase UID
            if not getattr(user, "firebase_uid", None):
                setattr(user, "firebase_uid", uid)
            if not getattr(user, "auth_provider", None):
                setattr(user, "auth_provider", "firebase")
            if picture and not getattr(user, "avatar_url", None):
                setattr(user, "avatar_url", picture)
            if name and not user.first_name:
                user.first_name = name
            user.save()
        else:
            user = User.objects.create(
                # username=email,
                email=email,
                # first_name=name,
                is_active=True,
                # добавь поля в свою модель, если есть:
                # firebase_uid=uid,
                # auth_provider="firebase",
                # avatar_url=picture or None,
            )

        refresh = RefreshToken.for_user(user)
        data = {
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": user.id,
                "email": user.email,
                # "name": user.first_name,
                "avatar_url": getattr(user, "avatar_url", None),
                "provider": getattr(user, "auth_provider", "firebase"),
            },
        }
        return Response(data, status=200)
