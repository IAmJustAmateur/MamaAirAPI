# api/jwt_refresh.py
import logging

from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.contrib.auth import get_user_model

from rest_framework_simplejwt.views import TokenRefreshView

logger = logging.getLogger(__name__)
User = get_user_model()


class LoggingTokenRefreshSerializer(TokenRefreshSerializer):
    """
    Сериализатор, который логирует payload refresh-токена
    и аккуратно обрабатывает ситуацию, когда пользователь не найден.
    """

    def validate(self, attrs):
        raw_refresh = attrs.get("refresh")

        # Сначала пробуем просто декодировать токен
        try:
            token = self.token_class(raw_refresh)
        except TokenError as e:
            logger.warning("Invalid refresh token: %s", e)
            raise InvalidToken(e.args[0])

        # Здесь у нас уже есть payload refresh-токена
        try:
            payload = token.payload
        except AttributeError:
            payload = dict(token)

        logger.info("Refresh token payload: %s", payload)

        # Можно дополнительно попробовать явно найти пользователя
        user_id_field = (
            self.token_class().user_id_field
        )  # как simplejwt ищет пользователя
        user_id = payload.get(self.token_class().user_id_claim)

        logger.info(
            "User lookup for refresh token: user_id_field=%s, claim=%s, value=%s",
            user_id_field,
            self.token_class().user_id_claim,
            user_id,
        )

        if user_id is not None:
            try:
                user = User._default_manager.get(**{user_id_field: user_id})
                logger.info(
                    "User found for refresh token: id=%s, email=%s",
                    getattr(user, "id", None),
                    getattr(user, "email", None),
                )
            except User.DoesNotExist:
                logger.error(
                    "User from refresh token does not exist. user_id_field=%s, value=%s, payload=%s",
                    user_id_field,
                    user_id,
                    payload,
                )
                # здесь можно либо бросить InvalidToken, либо позволить simplejwt самому упасть
                # безопаснее — сразу дать 401, а не 500:
                raise InvalidToken("User for this refresh token does not exist")

        # а теперь даём simplejwt сделать свою стандартную логику (выдача нового access'а)
        return super().validate(attrs)


class LoggingTokenRefreshView(TokenRefreshView):
    serializer_class = LoggingTokenRefreshSerializer
