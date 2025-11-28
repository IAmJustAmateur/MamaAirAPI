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

        if user.check_password(password):
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
    """
    Класс аутентификации, который логирует payload токена
    и информацию о пользователе.
    """

    def get_validated_token(self, raw_token):
        token = super().get_validated_token(raw_token)
        # В token.payload лежит декодированный JWT
        try:
            payload = token.payload
        except AttributeError:
            # На всякий случай, если версия simplejwt другая
            payload = dict(token)

        logger.info("JWT access token payload: %s", payload)
        return token

    def get_user(self, validated_token):
        try:
            user = super().get_user(validated_token)
        except Exception:
            # Логируем payload, если не удалось найти пользователя
            try:
                payload = validated_token.payload
            except AttributeError:
                payload = dict(validated_token)
            logger.exception("Failed to get user from JWT token. Payload: %s", payload)
            raise

        logger.info(
            "Authenticated user id=%s, email=%s",
            getattr(user, "id", None),
            getattr(user, "email", None),
        )
        return user
