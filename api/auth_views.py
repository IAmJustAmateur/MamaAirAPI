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
from logging import getLogger

logger = getLogger(__name__)


def verify_id_token(token_str: str) -> dict:
    # Verify the token using Google's signature.
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
    summary="Sign in with Google (Android)",
    description=(
        "Accept Google **ID token** from Android app, verify it on the server,"
        "create or link user, and issue your JWTs (access/refresh)."
    ),
    request=GoogleAuthRequestSerializer,
    responses={
        200: OpenApiResponse(
            response=GoogleAuthResponseSerializer,
            description="Authentication successful",
        ),
        400: OpenApiResponse(
            response=ErrorSerializer, description="Incorrect request (missing id_token)"
        ),
        401: OpenApiResponse(
            response=ErrorSerializer,
            description="Token validation failed (aud/iss/expired/email_verified)",
        ),
    },
    examples=[
        OpenApiExample(
            "Request successful",
            value={"id_token": "eyJhbGciOiJSUzI1NiIsInR5cCI6IkpXVCJ9..."},
            request_only=True,
        ),
        OpenApiExample(
            "Successful response",
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
            "Error: Invalid audience",
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
            logger.info(f"Invalid audience: {aud}")
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
        if not google_sub:
            return Response({"detail": "Google subject missing"}, status=401)
        email = info["email"].lower()
        name = info.get("name") or ""
        picture = info.get("picture")

        user = None
        if google_sub:
            logger.debug(f"Looking for user with google_sub: {google_sub}")
            user = User.objects.filter(google_sub=google_sub).first()
            logger.debug(f"User found by google_sub: {user}")
        if not user:
            logger.debug(f"Looking for user with email: {email}")
            from .email_auth import find_user
            user = find_user(email)
            if not user and User.objects.filter(email__iexact=email).exists():
                return Response({"detail": "Account linking unavailable"}, status=401)
            if user:
                if not user.is_active or (user.google_sub and user.google_sub != google_sub):
                    return Response({"detail": "Account unavailable"}, status=401)
                if user.email_verification_pending:
                    user.set_unusable_password()
                    user.email_verification_pending = False
                user.google_sub = google_sub
                user.auth_provider = "google"
                if picture and not getattr(user, "avatar_url", None):
                    user.avatar_url = picture
                # if name and not user.first_name:
                #     user.first_name = name
                user.save()
                logger.debug(f"User found by email: {user}")
            else:
                logger.debug("Creating new user")
                user = User.objects.create_user(
                    email=email,
                    google_sub=google_sub,
                    auth_provider="google",
                    avatar_url=picture or None,
                    is_active=True,
                )
                logger.debug(f"User created: {user}")

        if not user.is_active:
            return Response({"detail": "Account unavailable"}, status=401)
        refresh = RefreshToken.for_user(user)
        logger.info(f"User {user} authenticated via Google")
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
