from types import SimpleNamespace
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import IntegrityError
from django.test import TestCase
from firebase_admin import auth
from rest_framework.test import APIClient
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

User = get_user_model()
API_URL = "/api/auth/firebase/"
CLAIMS = {
    "uid": "firebase-uid-123", "aud": "test-project", "auth_time": 1700000000,
    "email": "test@example.com", "email_verified": True,
    "name": "Test User", "picture": "https://example.com/avatar.jpg",
}


class FirebaseAuthTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        for name, value in [
            ("firebase_admin.get_app", SimpleNamespace(project_id="test-project")),
            ("auth.verify_id_token", dict(CLAIMS)),
            ("auth.get_user", SimpleNamespace(disabled=False, tokens_valid_after_timestamp=0)),
        ]:
            mocker = patch("api.firebase_auth." + name, return_value=value)
            mock = mocker.start()
            self.addCleanup(mocker.stop)
            setattr(self, name.rsplit(".", 1)[-1], mock)

    def login(self, **claims):
        self.verify_id_token.return_value = {**CLAIMS, **claims}
        return self.client.post(API_URL, {"id_token": "private-test-token"}, format="json")

    def session_requests(self, tokens):
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + tokens["access"])
        access = self.client.get("/api/profile/")
        self.client.credentials()
        refresh = self.client.post("/api/auth/token/refresh/", {"refresh": tokens["refresh"]}, format="json")
        return access, refresh

    def test_new_user_profile_and_session(self):
        response = self.login()
        self.assertEqual(response.status_code, 200, response.data)
        self.verify_id_token.assert_called_once_with("private-test-token", check_revoked=True)
        user = User.objects.get()
        self.assertEqual(user.firebase_uid, CLAIMS["uid"])
        self.assertEqual(user.auth_provider, "firebase")
        self.assertEqual(user.name, CLAIMS["name"])
        self.assertEqual(user.avatar_url, CLAIMS["picture"])
        self.assertFalse(user.has_usable_password())
        for token in (AccessToken(response.data["access"]), RefreshToken(response.data["refresh"])):
            self.assertEqual(token["firebase_auth_time"], CLAIMS["auth_time"])
            self.assertEqual(token["firebase_uid"], user.firebase_uid)
        access, refresh = self.session_requests(response.data)
        self.assertEqual(access.status_code, 200, access.data)
        self.assertEqual(refresh.status_code, 200, refresh.data)
        self.assertEqual(AccessToken(refresh.data["access"])["firebase_auth_time"], CLAIMS["auth_time"])

    def test_repeat_and_changed_email_keep_same_account(self):
        original = self.login().data
        self.assertEqual(self.login().data["user"]["id"], original["user"]["id"])
        other = User.objects.create_user(email="changed@example.com")
        changed = self.login(email=other.email)
        self.assertEqual(changed.status_code, 200)
        self.assertEqual(changed.data["user"], original["user"])
        self.assertEqual(User.objects.count(), 2)
        other.refresh_from_db()
        self.assertIsNone(other.firebase_uid)

    def test_link_verified_existing_account_case_insensitively(self):
        user = User.objects.create_user(email="Test@Example.com", password="ExistingPassword1",
                                       name="Existing name", avatar_url="https://example.com/old.jpg")
        password_hash = user.password
        response = self.login()
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data["user"]["id"], user.pk)
        user.refresh_from_db()
        self.assertEqual(user.password, password_hash)
        self.assertEqual(user.name, "Existing name")
        self.assertEqual(user.avatar_url, "https://example.com/old.jpg")
        self.assertEqual(user.email, "Test@example.com")

    def test_conflicting_uid_rejected(self):
        self.login()
        self.assertEqual(self.login(uid="another-uid").status_code, 401)
        self.assertEqual(User.objects.count(), 1)

    def test_ambiguous_email_rejected(self):
        User.objects.create_user(email="Test@example.com")
        User.objects.create_user(email="test@example.com")
        self.assertEqual(self.login().status_code, 401)
        self.assertFalse(User.objects.exclude(firebase_uid=None).exists())

    def test_local_disabled_and_pending_rejected_before_and_after_link(self):
        user = User.objects.create_user(email=CLAIMS["email"])
        for linked in (False, True):
            for field in ("is_active", "email_verification_pending"):
                user.firebase_uid = CLAIMS["uid"] if linked else None
                user.is_active = field != "is_active"
                user.email_verification_pending = field == "email_verification_pending"
                user.save()
                self.assertEqual(self.login().status_code, 401)

    def test_invalid_input_never_calls_firebase(self):
        for data in ({}, {"id_token": None}, {"id_token": []}, {"id_token": ""}, {"id_token": "a" * 16385}):
            with self.subTest(data_type=type(data.get("id_token"))):
                response = self.client.post(API_URL, data, format="json")
                self.assertEqual(response.status_code, 400)
        self.verify_id_token.assert_not_called()

    def test_invalid_claims_rejected(self):
        for claims in ({"email_verified": False}, {"email": None}, {"email": "invalid"},
                       {"uid": ""}, {"auth_time": None}, {"auth_time": True}, {"aud": "wrong-project"}):
            with self.subTest(claims=claims):
                self.assertEqual(self.login(**claims).status_code, 401)
        self.assertFalse(User.objects.exists())

    def test_invalid_revoked_disabled_and_deleted_token_rejected(self):
        for error in (auth.InvalidIdTokenError, auth.ExpiredIdTokenError,
                      auth.RevokedIdTokenError, auth.UserDisabledError, auth.UserNotFoundError):
            with self.subTest(error=error):
                self.verify_id_token.side_effect = (error("private SDK detail", cause=None)
                                                   if error is auth.ExpiredIdTokenError
                                                   else error("private SDK detail"))
                self.assertEqual(self.login().status_code, 401)

    def test_configuration_and_service_failures_are_503_without_secrets(self):
        self.get_app.side_effect = ValueError("private config")
        self.assertEqual(self.login().status_code, 503)
        self.verify_id_token.assert_not_called()
        self.get_app.side_effect = None
        self.verify_id_token.side_effect = auth.CertificateFetchError("private SDK detail", cause=None)
        with self.assertLogs("api.firebase_auth", level="ERROR") as logs:
            response = self.login()
        self.assertEqual(response.status_code, 503)
        self.assertNotIn("private", str(response.data) + str(logs.output))

    def test_concurrent_creation_conflict_is_controlled(self):
        with patch.object(User.objects, "create_user", side_effect=IntegrityError("duplicate")):
            self.assertEqual(self.login().status_code, 409)

    def test_tokens_and_claims_not_logged(self):
        with patch("api.firebase_auth.logger") as logger:
            self.assertEqual(self.login().status_code, 200)
        logger.info.assert_not_called()
        logger.debug.assert_not_called()

    def test_disabled_revoked_deleted_sessions_rejected_for_access_and_refresh(self):
        tokens = self.login().data
        for record in (SimpleNamespace(disabled=True, tokens_valid_after_timestamp=0),
                       SimpleNamespace(disabled=False, tokens_valid_after_timestamp=(CLAIMS["auth_time"] + 1) * 1000)):
            self.get_user.return_value = record
            for response in self.session_requests(tokens):
                self.assertEqual(response.status_code, 401, response.data)
        self.get_user.side_effect = auth.UserNotFoundError("deleted")
        for response in self.session_requests(tokens):
            self.assertEqual(response.status_code, 401)

    def test_revocation_uses_original_login_time_after_refresh(self):
        tokens = self.login().data
        _, response = self.session_requests(tokens)
        tokens["access"] = response.data["access"]
        self.get_user.return_value.tokens_valid_after_timestamp = (CLAIMS["auth_time"] + 1) * 1000
        for response in self.session_requests(tokens):
            self.assertEqual(response.status_code, 401)

    def test_session_check_fails_closed_on_firebase_outage(self):
        tokens = self.login().data
        self.get_user.side_effect = ConnectionError("private detail")
        for response in self.session_requests(tokens):
            self.assertEqual(response.status_code, 503)
            self.assertNotIn("private", str(response.data))

    def test_fresh_signin_after_revocation_restores_access(self):
        old_tokens = self.login().data
        cutoff = CLAIMS["auth_time"] + 5
        self.get_user.return_value.tokens_valid_after_timestamp = cutoff * 1000
        for response in self.session_requests(old_tokens):
            self.assertEqual(response.status_code, 401)
        new_tokens = self.login(auth_time=cutoff).data
        for response in self.session_requests(new_tokens):
            self.assertEqual(response.status_code, 200)

    def test_local_block_and_password_change_still_revoke_firebase_sessions(self):
        tokens = self.login().data
        user = User.objects.get()
        for field in ("is_active", "email_verification_pending", "password"):
            user.is_active = field != "is_active"
            user.email_verification_pending = field == "email_verification_pending"
            if field == "password":
                user.set_password("ChangedLocalPassword1")
            user.save()
            for response in self.session_requests(tokens):
                self.assertEqual(response.status_code, 401)
        self.get_user.assert_not_called()

    def test_rate_limit(self):
        for _ in range(10):
            self.assertEqual(self.login().status_code, 200)
        self.assertEqual(self.login().status_code, 429)
        self.assertEqual(self.verify_id_token.call_count, 10)

    def test_session_project_or_uid_change_rejected(self):
        tokens = self.login().data
        self.get_app.return_value.project_id = "other-project"
        for response in self.session_requests(tokens):
            self.assertEqual(response.status_code, 401)
        self.get_app.return_value.project_id = "test-project"
        User.objects.update(firebase_uid="different-uid")
        for response in self.session_requests(tokens):
            self.assertEqual(response.status_code, 401)

    def test_other_login_sessions_do_not_call_firebase(self):
        self.login()
        refresh = RefreshToken.for_user(User.objects.get())
        self.get_app.reset_mock()
        for response in self.session_requests({"access": str(refresh.access_token), "refresh": str(refresh)}):
            self.assertEqual(response.status_code, 200)
        self.get_user.assert_not_called()
        self.get_app.assert_not_called()

    def test_profile_cannot_change_uid(self):
        tokens = self.login().data
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + tokens["access"])
        response = self.client.patch("/api/profile/", {"firebase_uid": "attacker"}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(User.objects.get().firebase_uid, CLAIMS["uid"])
        self.assertNotIn("firebase_uid", response.data)
