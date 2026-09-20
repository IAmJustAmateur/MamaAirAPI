# api/jwt_refresh.py
import logging

from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.contrib.auth import get_user_model

from rest_framework_simplejwt.settings import (
    api_settings,
)  # Read the Simple JWT settings from the public API.
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.utils import get_md5_hash_password

logger = logging.getLogger(__name__)
User = get_user_model()


class LoggingTokenRefreshSerializer(TokenRefreshSerializer):
    """Reject missing users and password-revoked refresh tokens without logging secrets."""

    def validate(self, attrs):
        raw_refresh = attrs.get("refresh")

        # Decode the refresh token explicitly.
        try:
            token = self.token_class(raw_refresh)
        except TokenError as e:
            logger.warning("Invalid refresh token: %s", e)
            # Simple JWT already maps this validation error to HTTP 401.
            raise InvalidToken(e.args[0])

        # Read the decoded payload.
        try:
            payload = token.payload
        except AttributeError:
            payload = dict(token)

        # Use Simple JWT's configured model field and token claim.
        user_id_field = api_settings.USER_ID_FIELD
        user_id_claim = api_settings.USER_ID_CLAIM
        user_id = payload.get(user_id_claim)

        logger.info(
            "User lookup for refresh token: user_id_field=%s, claim=%s, value=%s",
            user_id_field,
            user_id_claim,
            user_id,
        )

        if user_id is not None:
            try:
                user = User._default_manager.get(**{user_id_field: user_id})
                if api_settings.CHECK_REVOKE_TOKEN and token.get(api_settings.REVOKE_TOKEN_CLAIM) != get_md5_hash_password(user.password):
                    raise InvalidToken("Password has changed. Please sign in again.")
                logger.info(
                    "User found for refresh token: id=%s, email=%s",
                    getattr(user, "id", None),
                    getattr(user, "email", None),
                )
            except User.DoesNotExist:
                logger.error(
                    "User from refresh token does not exist. user_id_field=%s, value=%s",
                    user_id_field,
                    user_id,
                )
                # Return a controlled 401 response instead of a server error.
                raise InvalidToken("User for this refresh token does not exist")

        # Delegate expiry validation and access-token creation to Simple JWT.
        return super().validate(attrs)


class LoggingTokenRefreshView(TokenRefreshView):
    serializer_class = LoggingTokenRefreshSerializer
