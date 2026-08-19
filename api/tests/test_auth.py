# api/tests/test_auth.py

import os
import shutil
import tempfile

from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import override_settings
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework import status
from django.contrib.auth import get_user_model

User = get_user_model()
from django.conf import settings


PNG_1X1 = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01"
    b"\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89"
    b"\x00\x00\x00\rIDATx\x9cc\xf8\xcf\xc0\xf0\x1f\x00"
    b"\x05\x00\x01\xff\x89\x99=\x1d\x00\x00\x00\x00IEND\xaeB`\x82"
)


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

    def test_profile_onboarding_fields_round_trip(self):
        token_response = self.client.post(
            self.token_url, {"email": "test@example.com", "password": "testpass123"}
        )
        access = token_response.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        payload = {
            "timezone": "Europe/Minsk",
            "pregnancy_number": 2,
            "notification_window_from": "09:00",
            "notification_window_to": "21:00",
        }
        response = self.client.patch(self.profile_url, payload, format="json")

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(response.data["timezone"], "Europe/Minsk")
        self.assertEqual(response.data["pregnancy_number"], 2)
        self.assertEqual(response.data["notification_window_from"], "09:00:00")
        self.assertEqual(response.data["notification_window_to"], "21:00:00")
        self.assertIs(response.data["is_first_pregnancy"], False)

        self.user.refresh_from_db()
        self.assertEqual(self.user.pregnancy_number, 2)
        self.assertIs(self.user.is_first_pregnancy, False)

    def test_profile_rejects_invalid_timezone(self):
        token_response = self.client.post(
            self.token_url, {"email": "test@example.com", "password": "testpass123"}
        )
        access = token_response.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = self.client.patch(
            self.profile_url, {"timezone": "Minsk"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("timezone", response.data)

    def test_profile_requires_complete_notification_window(self):
        token_response = self.client.post(
            self.token_url, {"email": "test@example.com", "password": "testpass123"}
        )
        access = token_response.data["access"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")

        response = self.client.patch(
            self.profile_url, {"notification_window_from": "09:00"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("notification_window", response.data)

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

    @override_settings(REGISTRATION_API_KEY="test-registration-key")
    def test_register_user_success_with_api_key(self):
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

    @override_settings(REGISTRATION_API_KEY="test-registration-key")
    def test_register_user_without_api_key(self):
        response = self.client.post(
            reverse("register"),
            {
                "email": "unauthorized@example.com",
                "password": "password123",
            },
        )
        self.assertEqual(response.status_code, 401)

    @override_settings(REGISTRATION_API_KEY="test-registration-key")
    def test_register_user_with_invalid_api_key(self):
        response = self.client.post(
            reverse("register"),
            {
                "email": "invalid-key@example.com",
                "password": "password123",
            },
            HTTP_X_API_KEY="wrong-registration-key",
        )
        self.assertEqual(response.status_code, 401)
        self.assertFalse(User.objects.filter(email="invalid-key@example.com").exists())

    @override_settings(REGISTRATION_API_KEY=None)
    def test_register_user_when_api_key_is_not_configured(self):
        response = self.client.post(
            reverse("register"),
            {
                "email": "unconfigured-key@example.com",
                "password": "password123",
            },
        )
        self.assertEqual(response.status_code, 401)
        self.assertFalse(
            User.objects.filter(email="unconfigured-key@example.com").exists()
        )

    @override_settings(REGISTRATION_API_KEY="")
    def test_register_user_when_api_key_is_blank(self):
        response = self.client.post(
            reverse("register"),
            {
                "email": "blank-key@example.com",
                "password": "password123",
            },
            HTTP_X_API_KEY="",
        )
        self.assertEqual(response.status_code, 401)
        self.assertFalse(User.objects.filter(email="blank-key@example.com").exists())


class ProfileAvatarTests(APITestCase):
    def setUp(self):
        self.media_root = tempfile.mkdtemp()
        self.override = override_settings(MEDIA_ROOT=self.media_root)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.addCleanup(lambda: shutil.rmtree(self.media_root, ignore_errors=True))

        self.user = User.objects.create_user(
            email="avatar@example.com",
            password="testpass123",
            avatar_url="https://example.com/social-avatar.png",
        )
        self.client.force_authenticate(self.user)
        self.avatar_url = reverse("profile-avatar")
        self.profile_url = reverse("profile")

    def _avatar_file(self, name="avatar.png"):
        return SimpleUploadedFile(name, PNG_1X1, content_type="image/png")

    def test_upload_avatar_returns_profile_with_uploaded_avatar_url(self):
        response = self.client.post(
            self.avatar_url,
            {"avatar": self._avatar_file()},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn("/media/avatars/user_", response.data["avatar_url"])
        self.assertNotEqual(
            response.data["avatar_url"], "https://example.com/social-avatar.png"
        )

        self.user.refresh_from_db()
        self.assertTrue(self.user.avatar.name.startswith("avatars/user_"))

        profile_response = self.client.get(self.profile_url)
        self.assertEqual(profile_response.data["avatar_url"], response.data["avatar_url"])

    def test_delete_avatar_removes_upload_and_falls_back_to_legacy_avatar_url(self):
        upload_response = self.client.post(
            self.avatar_url,
            {"avatar": self._avatar_file()},
            format="multipart",
        )
        self.assertEqual(upload_response.status_code, status.HTTP_200_OK)

        self.user.refresh_from_db()
        uploaded_path = self.user.avatar.path

        delete_response = self.client.delete(self.avatar_url)

        self.assertEqual(delete_response.status_code, status.HTTP_200_OK)
        self.assertEqual(
            delete_response.data["avatar_url"],
            "https://example.com/social-avatar.png",
        )
        self.assertFalse(os.path.exists(uploaded_path))

        self.user.refresh_from_db()
        self.assertFalse(self.user.avatar)

    def test_upload_avatar_rejects_non_image(self):
        file_obj = SimpleUploadedFile(
            "avatar.txt",
            b"not an image",
            content_type="text/plain",
        )

        response = self.client.post(
            self.avatar_url,
            {"avatar": file_obj},
            format="multipart",
        )

        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("avatar", response.data)
