"""Email account operations shared by HTTP endpoints and Celery tasks."""
import hashlib
import logging
from collections.abc import Mapping

from django.contrib.auth import get_user_model
from django.contrib.auth.tokens import PasswordResetTokenGenerator
from django.db import IntegrityError, transaction
from django.utils.encoding import force_bytes
from django.utils.http import urlsafe_base64_decode, urlsafe_base64_encode
from rest_framework import serializers, throttling
from rest_framework.exceptions import APIException
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework_simplejwt.tokens import RefreshToken
from drf_spectacular.utils import extend_schema

from api.serializers import GoogleAuthResponseSerializer

logger = logging.getLogger(__name__)
User = get_user_model()
ACCEPTED = {"detail": "If the account is eligible, an email will be sent. Please check your inbox."}


def user_can_authenticate(user):
    return bool(user and user.is_active and not user.email_verification_pending)


def account_state(user):
    raw = f"{user.pk}:{user.email}:{user.password}:{user.is_active}:{user.email_verification_pending}"
    return hashlib.sha256(raw.encode()).hexdigest()


class VerificationTokenGenerator(PasswordResetTokenGenerator):
    key_salt = "mamaair.email.verify"

    def _make_hash_value(self, user, timestamp):
        return super()._make_hash_value(user, timestamp) + str(user.email_verification_pending)


verification_tokens = VerificationTokenGenerator()
reset_tokens = PasswordResetTokenGenerator()


def find_user(email):
    # Fail closed for legacy case-insensitive duplicates; never link arbitrarily.
    users = list(User.objects.filter(email__iexact=email)[:2])
    return users[0] if len(users) == 1 else None


class EmailInput(serializers.Serializer):
    email = serializers.EmailField(max_length=254)

    def validate_email(self, value):
        return value.strip().lower()


class RegisterInput(EmailInput):
    password = serializers.CharField(write_only=True, trim_whitespace=False, min_length=6, max_length=128)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False, min_length=6, max_length=128)

    def validate(self, attrs):
        check_password(attrs["password"], attrs["password_confirm"])
        return attrs


class LoginInput(EmailInput):
    password = serializers.CharField(write_only=True, trim_whitespace=False, max_length=128)


class ConfirmInput(serializers.Serializer):
    uid = serializers.CharField(max_length=128)
    token = serializers.CharField(max_length=256, write_only=True)
    new_password = serializers.CharField(write_only=True, trim_whitespace=False, min_length=6, max_length=128)
    password_confirm = serializers.CharField(write_only=True, trim_whitespace=False, min_length=6, max_length=128)


class DetailOutput(serializers.Serializer):
    detail = serializers.CharField()


def check_password(password, confirmation):
    # Account passwords require length and confirmation only; Django's global
    # strength validators remain available to administrative forms.
    if password != confirmation:
        raise serializers.ValidationError({"password_confirm": ["Passwords do not match."]})


class EmailIPThrottle(throttling.AnonRateThrottle):
    scope = "email_auth"


class EmailAddressThrottle(throttling.SimpleRateThrottle):
    scope = "email_address"

    def get_cache_key(self, request, view):
        if not isinstance(request.data, Mapping):
            return None  # Let the serializer return a controlled invalid-input response.
        value = str(request.data.get("email", "")).strip().lower()
        return self.cache_format % {"scope": self.scope, "ident": hashlib.sha256(value.encode()).hexdigest()}


class EmailUnavailable(APIException):
    status_code = 503
    default_detail = "Email service is temporarily unavailable. Please try again later."


def queue_email(email, purpose):
    from api.tasks import send_account_email
    user = find_user(email)
    state = account_state(user) if user else None

    def publish():
        try:
            # Bound delay: queued mail must not silently become valid days later.
            send_account_email.apply_async(
                args=(email, purpose, state), expires=600,
                argsrepr="(<redacted email>, <purpose>, <redacted state>)",
            )
        except Exception as exc:
            logger.error("Account email could not be queued (%s)", type(exc).__name__)
            raise EmailUnavailable() from exc

    transaction.on_commit(publish)


class PublicEmailView(APIView):
    authentication_classes = []
    permission_classes = []
    throttle_classes = [EmailIPThrottle]


class EmailRegisterView(PublicEmailView):
    throttle_classes = [EmailIPThrottle, EmailAddressThrottle]

    @extend_schema(tags=["Auth"], request=RegisterInput, responses={202: DetailOutput, 400: DetailOutput, 503: DetailOutput})
    def post(self, request):
        data = RegisterInput(data=request.data)
        data.is_valid(raise_exception=True)
        email = data.validated_data["email"]
        # A repeated registration cannot replace the password of an existing user.
        if not User.objects.filter(email__iexact=email).exists():
            try:
                with transaction.atomic():
                    User.objects.create_user(email=email, password=data.validated_data["password"], email_verification_pending=True)
            except IntegrityError:
                pass  # A concurrent registration won; resend without changing it.
        queue_email(email, "verify")
        return Response(ACCEPTED, status=202)


class EmailLoginView(PublicEmailView):
    @extend_schema(tags=["Auth"], request=LoginInput, responses={200: GoogleAuthResponseSerializer, 401: DetailOutput})
    def post(self, request):
        data = LoginInput(data=request.data)
        data.is_valid(raise_exception=True)
        user = find_user(data.validated_data["email"])
        valid_password = user.check_password(data.validated_data["password"]) if user else False
        if not user:
            User().set_password(data.validated_data["password"])
        if not valid_password or not user_can_authenticate(user):
            return Response({"detail": "Invalid email or password, or email is not confirmed."}, status=401)
        refresh = RefreshToken.for_user(user)
        return Response({"access": str(refresh.access_token), "refresh": str(refresh), "user": {
            "id": user.pk, "email": user.email, "avatar_url": user.avatar_url, "provider": "password",
        }})


class EmailResendView(PublicEmailView):
    purpose = "verify"
    throttle_classes = [EmailIPThrottle, EmailAddressThrottle]

    @extend_schema(tags=["Auth"], request=EmailInput, responses={202: DetailOutput, 503: DetailOutput})
    def post(self, request):
        data = EmailInput(data=request.data)
        data.is_valid(raise_exception=True)
        queue_email(data.validated_data["email"], self.purpose)
        return Response(ACCEPTED, status=202)


class PasswordResetRequestView(EmailResendView):
    purpose = "reset"


def confirm_account(attrs, purpose):
    try:
        pk = urlsafe_base64_decode(attrs["uid"]).decode()
        with transaction.atomic():
            user = User.objects.select_for_update().get(pk=pk)
            generator = verification_tokens if purpose == "verify" else reset_tokens
            eligible = user.is_active and user.email_verification_pending == (purpose == "verify")
            if not eligible or not generator.check_token(user, attrs["token"]):
                raise ValueError("invalid token")
            check_password(attrs["new_password"], attrs["password_confirm"])
            # The email holder chooses the final password. A pre-registration by
            # somebody else can never leave that person's password on the account.
            user.set_password(attrs["new_password"])
            user.email_verification_pending = False
            user.save(update_fields=["password", "email_verification_pending"])
    except (User.DoesNotExist, ValueError, TypeError, OverflowError, UnicodeDecodeError):
        raise serializers.ValidationError({"detail": "This link is invalid, expired, or already used."})


class EmailVerifyView(PublicEmailView):
    purpose = "verify"

    @extend_schema(tags=["Auth"], request=ConfirmInput, responses={200: DetailOutput, 400: DetailOutput})
    def post(self, request):
        data = ConfirmInput(data=request.data)
        data.is_valid(raise_exception=True)
        confirm_account(data.validated_data, self.purpose)
        return Response({"detail": "Password saved. You can now sign in."})


class PasswordResetConfirmView(EmailVerifyView):
    purpose = "reset"


def encoded_uid(user):
    return urlsafe_base64_encode(force_bytes(user.pk))
