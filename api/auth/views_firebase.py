from django.contrib.auth import get_user_model
from django.db import IntegrityError, transaction
from rest_framework import serializers, throttling
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema

from api.firebase_auth import FirebaseRejected, verify_firebase_token
from api.serializers import GoogleAuthResponseSerializer, ErrorSerializer

User = get_user_model()


class SigninThrottle(throttling.AnonRateThrottle):
    scope = "signin"


class FirebaseInput(serializers.Serializer):
    id_token = serializers.CharField(max_length=16384, trim_whitespace=False)


class FirebaseAuthView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = [SigninThrottle]

    @extend_schema(
        tags=["Auth"], summary="Sign in with Firebase",
        request=FirebaseInput,
        responses={200: GoogleAuthResponseSerializer, 400: ErrorSerializer,
                   401: ErrorSerializer, 409: ErrorSerializer, 503: ErrorSerializer},
    )
    def post(self, request):
        data = FirebaseInput(data=request.data)
        data.is_valid(raise_exception=True)
        claims, email = verify_firebase_token(data.validated_data["id_token"])
        uid = claims["uid"]
        name = str(claims.get("name") or "")[:255]
        try:
            picture = serializers.URLField(max_length=200).run_validation(claims.get("picture"))
        except serializers.ValidationError:
            picture = None
        try:
            with transaction.atomic():
                user = User.objects.select_for_update().filter(firebase_uid=uid).first()
                if user is None:
                    matches = list(User.objects.select_for_update().filter(email__iexact=email)[:2])
                    if len(matches) > 1:
                        raise FirebaseRejected("Account unavailable")
                    user = matches[0] if matches else None
                    if user and user.firebase_uid not in (None, uid):
                        raise FirebaseRejected("Account unavailable")
                if user:
                    if not user.is_active or user.email_verification_pending:
                        raise FirebaseRejected("Account unavailable")
                    # Local email identifies existing JWTs and password accounts.
                    # Keep it stable; Firebase identity is the UID.
                    user.firebase_uid = uid
                    user.auth_provider = "firebase"
                    if not user.name:
                        user.name = name
                    if not user.avatar_url:
                        user.avatar_url = picture
                    user.save(update_fields=["firebase_uid", "auth_provider", "name", "avatar_url"])
                else:
                    user = User.objects.create_user(
                        email=email, firebase_uid=uid, auth_provider="firebase",
                        name=name, avatar_url=picture,
                    )
                refresh = RefreshToken.for_user(user)
                refresh["firebase_uid"] = uid
                refresh["firebase_auth_time"] = claims["auth_time"]
                refresh["firebase_project_id"] = claims["aud"]
        except IntegrityError:
            return Response({"detail": "Account conflict. Please retry sign-in."}, status=409)

        return Response({
            "access": str(refresh.access_token),
            "refresh": str(refresh),
            "user": {
                "id": user.id, "email": user.email,
                "avatar_url": user.avatar_url, "provider": user.auth_provider,
            },
        })
