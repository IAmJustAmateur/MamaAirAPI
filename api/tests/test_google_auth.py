# tests/test_google_auth.py
from django.test import TestCase, override_settings
from rest_framework.test import APIClient
from unittest.mock import patch

API_URL = "/api/auth/google/"

FAKE_CLAIMS_OK = {
    "aud": "test-client-id.apps.googleusercontent.com",
    "iss": "https://accounts.google.com",
    "email": "test@example.com",
    "email_verified": True,
    "sub": "google-sub-123",
    "name": "Test User",
    "picture": "https://example.com/a.jpg",
}


def _patch_verify(return_value=FAKE_CLAIMS_OK, side_effect=None):
    """
    Удобный helper: патчим вашу обёртку verify_id_token.
    ВАЖНО: путь должен совпадать с тем, как вы импортируете вьюху.
    Если во view: `from auth.google_verifier import verify_id_token`,
    то патчить нужно 'auth.views.verify_id_token'.
    Если во view: `from .google_verifier import verify_id_token`,
    модуль всё равно будет 'auth.views.verify_id_token'.
    """
    return patch(
        "api.auth_views.verify_id_token",
        return_value=return_value,
        side_effect=side_effect,
    )


@override_settings(GOOGLE_ALLOWED_AUDS="test-client-id.apps.googleusercontent.com")
class GoogleAuthViewTests(TestCase):
    def setUp(self):
        self.client = APIClient()

    def test_success(self):
        with _patch_verify():
            resp = self.client.post(API_URL, {"id_token": "ANY"}, format="json")
        self.assertEqual(resp.status_code, 200, resp.content)
        data = resp.json()
        # Проверяем, что отдали наши JWT и профиль
        self.assertIn("access", data)
        self.assertIn("refresh", data)
        self.assertEqual(data["user"]["email"], "test@example.com")
        self.assertEqual(data["user"]["provider"], "google")

    def test_missing_token(self):
        resp = self.client.post(API_URL, {}, format="json")
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json().get("detail"), "id_token is required")

    # def test_invalid_audience(self):
    #     wrong_claims = {
    #         **FAKE_CLAIMS_OK,
    #         "aud": "another-client-id.apps.googleusercontent.com",
    #     }
    #     with _patch_verify(return_value=wrong_claims):
    #         resp = self.client.post(API_URL, {"id_token": "ANY"}, format="json")
    #     self.assertEqual(resp.status_code, 401)
    #     self.assertEqual(resp.json().get("detail"), "Invalid audience")

    def test_email_not_verified(self):
        claims = {**FAKE_CLAIMS_OK, "email_verified": False}
        with _patch_verify(return_value=claims):
            resp = self.client.post(API_URL, {"id_token": "ANY"}, format="json")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json().get("detail"), "Email not verified")

    def test_invalid_google_token_signature(self):
        # эмулируем исключение из verify_id_token
        with _patch_verify(side_effect=ValueError("bad token")):
            resp = self.client.post(API_URL, {"id_token": "ANY"}, format="json")
        self.assertEqual(resp.status_code, 401)
        self.assertEqual(resp.json().get("detail"), "Invalid Google token")
