# api/tests/test_auth.py

from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model

User = get_user_model()
from django.conf import settings


class AuthTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="test@example.com", password="testpass123"
        )
        self.token_url = reverse("token_obtain_pair")
        self.refresh_url = reverse("token_refresh")
        self.profile_url = reverse("profile")  # Защищённый эндпоинт

    def test_obtain_token_success(self):
        response = self.client.post(
            self.token_url, {"email": "test@example.com", "password": "testpass123"}
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)
        self.assertIn("refresh", response.data)

    def test_obtain_token_failure(self):
        response = self.client.post(
            self.token_url, {"email": "test@example.com", "password": "wrongpass"}
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_refresh_token_success(self):
        # Получаем refresh токен
        token_response = self.client.post(
            self.token_url, {"email": "test@example.com", "password": "testpass123"}
        )
        refresh = token_response.data["refresh"]

        # Пробуем обновить access токен
        response = self.client.post(self.refresh_url, {"refresh": refresh})
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("access", response.data)

    def test_protected_view_requires_auth(self):
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    def test_protected_view_with_token(self):
        token_response = self.client.post(
            self.token_url, {"email": "test@example.com", "password": "testpass123"}
        )
        access = token_response.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        response = self.client.get(self.profile_url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertEqual(response.data["email"], "test@example.com")

    def test_password_change_success(self):
        token = self.client.post(
            self.token_url, {"email": self.user.email, "password": "testpass123"}
        ).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.post(
            reverse("password-change"),
            {"old_password": "testpass123", "new_password": "newpass456"},
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Проверим что новый пароль работает
        login = self.client.post(
            self.token_url, {"email": self.user.email, "password": "newpass456"}
        )
        self.assertEqual(login.status_code, status.HTTP_200_OK)

    def test_logout(self):
        tokens = self.client.post(
            self.token_url, {"email": self.user.email, "password": "testpass123"}
        ).data
        access = tokens["access"]
        refresh = tokens["refresh"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        response = self.client.post(reverse("logout"), {"refresh": refresh})
        self.assertEqual(response.status_code, status.HTTP_302_FOUND)

    def test_delete_account(self):
        tokens = self.client.post(
            self.token_url, {"email": self.user.email, "password": "testpass123"}
        ).data
        access = tokens["access"]

        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
        response = self.client.delete(reverse("delete-account"))
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)

        # Убедимся, что пользователь действительно удалён
        self.assertFalse(User.objects.filter(email="test@example.com").exists())

    def test_set_language_success(self):
        # Получаем токен
        token = self.client.post(
            self.token_url, {"email": self.user.email, "password": "testpass123"}
        ).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        # Устанавливаем язык
        response = self.client.post(reverse("set-language"), {"language": "fr"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["language"], "fr")

        # Проверяем, что язык действительно обновлён
        self.user.refresh_from_db()
        self.assertEqual(self.user.language, "fr")

    def test_set_language_invalid_code(self):
        token = self.client.post(
            self.token_url, {"email": self.user.email, "password": "testpass123"}
        ).data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")

        response = self.client.post(reverse("set-language"), {"language": "xx"})
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.data)

    def test_set_language_requires_auth(self):
        response = self.client.post(reverse("set-language"), {"language": "fr"})
        self.assertEqual(response.status_code, 401)

    def test_register_user_success_with_api_key(self):
        headers = {"X-API-Key": settings.REGISTRATION_API_KEY}
        response = self.client.post(
            reverse("register"),
            {
                "email": "newuser@example.com",
                "password": "securepass123",
            },
            **{"HTTP_X_API_KEY": settings.REGISTRATION_API_KEY},
        )
        self.assertEqual(response.status_code, 201)
        self.assertTrue(User.objects.filter(email="newuser@example.com").exists())

    def test_register_user_without_api_key(self):
        response = self.client.post(
            reverse("register"),
            {
                "email": "unauthorized@example.com",
                "password": "password123",
            },
        )
        self.assertEqual(response.status_code, 401)
