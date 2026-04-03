from django.test import TestCase
from django.contrib.auth import get_user_model
from rest_framework.test import APIClient
from unittest.mock import patch

User = get_user_model()
API_URL = "/api/auth/firebase/"

FAKE_CLAIMS_OK = {
    "uid": "firebase-uid-123",
    "email": "test@example.com",
    "email_verified": True,
    "name": "Test User",
    "picture": "https://example.com/avatar.jpg",
}


def patch_verify(return_value=FAKE_CLAIMS_OK, side_effect=None):
    """
    Патчим именно то место, откуда verify_id_token импортирован во вьюхе.
    Если во view: `from firebase_admin import auth as fb_auth`,
    и далее `fb_auth.verify_id_token(...)`,
    то нужно патчить 'auth.views_firebase.fb_auth.verify_id_token'
    (замени путь под своё приложение).
    """
    return patch(
        "api.auth.views_firebase.fb_auth.verify_id_token",
        return_value=return_value,
        side_effect=side_effect,
    )


class FirebaseAuthViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_success_creates_user_and_returns_jwt(self):
        with patch_verify():
            resp = self.client.post(
                API_URL,
                {"id_token": "ANY_TOKEN"},
                format="json",
            )

        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()

        # Проверяем JWT
        self.assertIn("access", data)
        self.assertIn("refresh", data)

        # Пользователь создан
        user = User.objects.get(email="test@example.com")
        self.assertEqual(data["user"]["email"], "test@example.com")
        # self.assertEqual(data["user"]["name"], "Test User")

    def test_missing_token(self):
        resp = self.client.post(API_URL, {}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json().get("detail"), "id_token is required")

    # def test_invalid_token_exception(self):
    #     # Эмулируем сломанный/просроченный токен
    #     with patch_verify(side_effect=Exception("bad token")):
    #         resp = self.client.post(API_URL, {"id_token": "ANY"}, format="json")

    #     self.assertEqual(resp.status_code, 401)
    #     self.assertEqual(resp.json().get("detail"), "Invalid Firebase token")

    # def test_email_not_verified(self):
    #     claims = {**FAKE_CLAIMS_OK, "email_verified": False}
    #     with patch_verify(return_value=claims):
    #         resp = self.client.post(API_URL, {"id_token": "ANY"}, format="json")

    #     self.assertEqual(resp.status_code, 401)
    #     self.assertEqual(resp.json().get("detail"), "Email missing or not verified")
