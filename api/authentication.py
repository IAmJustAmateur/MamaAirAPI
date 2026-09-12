# authentication.py (внутри api/)

from rest_framework_simplejwt.authentication import JWTAuthentication
from django.contrib.auth.backends import ModelBackend
from django.contrib.auth import get_user_model

UserModel = get_user_model()
import logging

logger = logging.getLogger(__name__)


class EmailBackend(ModelBackend):
    def authenticate(self, request, username=None, password=None, **kwargs):
        logger.info(f"Authenticating user with email: {username}")
        try:
            user = UserModel.objects.get(email=username)
            logger.info(f"User found: {user}")
            # if request is not None:
            #     from django.contrib.auth import login

            #     login(request, user)
        except UserModel.DoesNotExist:
            logger.info(f"User with email {username} does not exist")
            return None

        if user.check_password(password) and self.user_can_authenticate(user) and not user.email_verification_pending:
            logger.info(f"User authenticated: {user}")
            return user

        return None

    def get_user(self, user_id):
        logger.info(f"Retrieving user with ID: {user_id}")
        try:
            user = UserModel.objects.get(pk=user_id)
            logger.info(f"User retrieved: {user}")
            return user
        except UserModel.DoesNotExist:
            return None


class LoggingJWTAuthentication(JWTAuthentication):
    """Authenticate JWTs without writing token claims or password fingerprints to logs."""

    def get_validated_token(self, raw_token):
        token = super().get_validated_token(raw_token)
        logger.debug("JWT access token validated")
        return token

    def get_user(self, validated_token):
        try:
            user = super().get_user(validated_token)
            if user.email_verification_pending:
                from rest_framework.exceptions import AuthenticationFailed
                raise AuthenticationFailed("Email confirmation required")
        except Exception:
            logger.warning("JWT authentication failed")
            raise

        logger.info(
            "Authenticated user id=%s, email=%s",
            getattr(user, "id", None),
            getattr(user, "email", None),
        )
        return user
