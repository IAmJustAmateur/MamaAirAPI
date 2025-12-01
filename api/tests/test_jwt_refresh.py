# api/tests/test_jwt_refresh.py

from django.contrib.auth import get_user_model
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status

from rest_framework_simplejwt.tokens import RefreshToken
from rest_framework_simplejwt.exceptions import InvalidToken

from api.jwt_refresh import LoggingTokenRefreshSerializer

User = get_user_model()


class LoggingTokenRefreshSerializerTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com",
            password="testpassword123",
        )

    def test_validate_success_when_user_exists(self):
        """
        Сериализатор должен успешно валидировать refresh-токен,
        если пользователь существует.
        """
        refresh = RefreshToken.for_user(self.user)
        data = {"refresh": str(refresh)}

        serializer = LoggingTokenRefreshSerializer(data=data)
        self.assertTrue(serializer.is_valid(), serializer.errors)

        # Должен выдать хотя бы новый access-токен
        self.assertIn("access", serializer.validated_data)

    def test_validate_raises_invalid_token_when_user_deleted(self):
        """
        Если пользователь, указанный в payload токена, удалён,
        сериализатор должен поднять InvalidToken (а не давать 500).
        """
        refresh = RefreshToken.for_user(self.user)
        data = {"refresh": str(refresh)}

        # Удаляем пользователя после выпуска токена
        self.user.delete()

        serializer = LoggingTokenRefreshSerializer(data=data)

        with self.assertRaises(InvalidToken) as ctx:
            serializer.is_valid(raise_exception=True)

        # Можно проверить текст ошибки, если хочется
        self.assertIn("User for this refresh token does not exist", str(ctx.exception))

    def test_validate_raises_invalid_token_on_completely_invalid_token(self):
        """
        При откровенно битом refresh-токене сериализатор должен поднять InvalidToken.
        """
        data = {"refresh": "this-is-not-a-valid-jwt"}

        serializer = LoggingTokenRefreshSerializer(data=data)

        with self.assertRaises(InvalidToken):
            serializer.is_valid(raise_exception=True)


class LoggingTokenRefreshViewTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test2@example.com",
            password="testpassword123",
        )
        self.refresh = str(RefreshToken.for_user(self.user))
        self.url = reverse("token_refresh")

    def test_refresh_view_returns_new_access_token(self):
        """
        Вьюха должна вернуть 200 и новый access-токен при валидном refresh.
        """
        response = self.client.post(
            self.url,
            {"refresh": self.refresh},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        # refresh может вернуться или нет, в зависимости от настроек.
        # Если ROTATE_REFRESH_TOKENS=False, обычно refresh не возвращают.
        # Поэтому проверяем только access.

    def test_refresh_view_returns_401_when_user_deleted(self):
        """
        Если пользователь удалён, вьюха должна вернуть 401 Unauthorized,
        а не 500, благодаря нашему кастомному сериализатору.
        """
        refresh = str(RefreshToken.for_user(self.user))
        self.user.delete()

        response = self.client.post(
            self.url,
            {"refresh": refresh},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("detail", response.data)
        # Наше сообщение "User for this refresh token does not exist"
        # попадёт в detail, но код будет 'token_not_valid' —
        # это поведение simplejwt.
        self.assertIn(
            "User for this refresh token does not exist", str(response.data["detail"])
        )

    def test_refresh_view_returns_401_on_invalid_token(self):
        """
        При полностью невалидном токене вьюха должна вернуть 401.
        """
        response = self.client.post(
            self.url,
            {"refresh": "not-a-valid-jwt"},
            format="json",
        )

        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertIn("detail", response.data)
