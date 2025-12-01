# api/jwt_refresh.py
import logging

from rest_framework_simplejwt.serializers import TokenRefreshSerializer
from rest_framework_simplejwt.exceptions import InvalidToken, TokenError
from django.contrib.auth import get_user_model

from rest_framework_simplejwt.settings import (
    api_settings,
)  # ВАЖНО: берём отсюда настройки
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

        # 1. Декодируем refresh-токен сами
        try:
            token = self.token_class(raw_refresh)
        except TokenError as e:
            logger.warning("Invalid refresh token: %s", e)
            # это уже "нормальная" ошибка simplejwt → 401
            raise InvalidToken(e.args[0])

        # 2. Достаём payload
        try:
            payload = token.payload
        except AttributeError:
            payload = dict(token)

        logger.info("Refresh token payload: %s", payload)

        # 3. Узнаём, как simplejwt ищет пользователя:
        #    USER_ID_FIELD – поле в модели (id или email)
        #    USER_ID_CLAIM – ключ в payload токена
        user_id_field = api_settings.USER_ID_FIELD  # <-- вот так, а не через token
        user_id_claim = api_settings.USER_ID_CLAIM  # например, "email" или "user_id"
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
                # отдаём аккуратный 401 вместо 500
                raise InvalidToken("User for this refresh token does not exist")

        # 4. Теперь даём simplejwt сделать обычную логику (проверка срока, выдача нового access и т.д.)
        return super().validate(attrs)


class LoggingTokenRefreshView(TokenRefreshView):
    serializer_class = LoggingTokenRefreshSerializer
