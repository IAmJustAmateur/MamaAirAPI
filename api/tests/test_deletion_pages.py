import time
from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.db import close_old_connections
from django.test import Client, TestCase, TransactionTestCase, override_settings, skipUnlessDBFeature
from django.urls import reverse
from django.utils import timezone

from api.deletion_pages import SESSION_KEY, digest
from api.firebase_auth import FirebaseRejected, FirebaseUnavailable
from api.models import AccountDeletionGrant, AuditLog

User = get_user_model()
PASSWORD = "Test-password-12!"


@override_settings(DELETION_GOOGLE_CLIENT_ID="web-client", DELETION_FIREBASE_CONFIG={
    "apiKey": "public-key", "authDomain": "test.firebaseapp.com", "projectId": "test", "appId": "test-app"})
class DeletionPageTests(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email="owner@example.com", password=PASSWORD)
        self.url = reverse("delete-account-page")

    def verify(self, client=None):
        return (client or self.client).post(self.url, {
            "action": "password", "email": self.user.email, "password": PASSWORD})

    def confirm(self, client=None, **extra):
        return (client or self.client).post(self.url, {
            "action": "confirm", "confirmation": "DELETE", **extra})

    def test_public_page_and_get_never_delete(self):
        for query in ("", "?action=confirm&confirmation=DELETE&token=anything"):
            response = self.client.get(self.url + query)
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, "Delete your account")
        self.verify()
        response = self.client.get(self.url)
        self.assertContains(response, self.user.email)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("frame-ancestors 'none'", response["Content-Security-Policy"])
        self.assertEqual(response["Referrer-Policy"], "same-origin")

    def test_password_success_shared_cleanup_and_replay(self):
        other = User.objects.create_user(email="other@example.com")
        AuditLog.objects.create(user=self.user, method="POST", path="/api/profile", status_code=200, duration_ms=1)
        other_log = AuditLog.objects.create(user=other, method="GET", path="/api/profile", status_code=200, duration_ms=1)
        self.assertEqual(self.verify().status_code, 302)
        self.assertEqual(AccountDeletionGrant.objects.count(), 1)
        stolen_session = Client()
        stolen_session.cookies = self.client.cookies.copy()
        response = self.confirm(user_id=other.pk, email=other.email)
        self.assertContains(response, "Account deleted")
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())
        self.assertTrue(User.objects.filter(pk=other.pk).exists())
        self.assertEqual(list(AuditLog.objects.values_list("pk", flat=True)), [other_log.pk])
        self.assertFalse(AccountDeletionGrant.objects.exists())
        self.assertEqual(self.confirm(stolen_session).status_code, 400)

    def test_wrong_confirmation_and_no_proof(self):
        self.assertEqual(self.confirm().status_code, 400)
        self.verify()
        for value in ("", "delete", " DELETE "):
            self.assertEqual(self.confirm(confirmation=value).status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_unknown_wrong_password_disabled_and_pending_are_indistinguishable(self):
        responses = []
        for email, password in (("absent@example.com", PASSWORD), (self.user.email, "wrong")):
            responses.append(self.client.post(self.url, {"action": "password", "email": email, "password": password}))
        for field in ("is_active", "email_verification_pending"):
            setattr(self.user, field, field == "email_verification_pending")
            self.user.save()
            responses.append(self.verify())
        for response in responses:
            self.assertEqual(response.status_code, 400)
            self.assertEqual(response.context["error"], responses[0].context["error"])
        self.assertFalse(AccountDeletionGrant.objects.exists())

    def test_expired_proof_cannot_be_used(self):
        self.verify()
        AccountDeletionGrant.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
        self.assertContains(self.client.get(self.url), "invalid, expired, or already used")
        self.assertEqual(self.confirm().status_code, 400)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_changed_password_invalidates_proof(self):
        self.verify()
        self.user.set_password("New-password-12!")
        self.user.save()
        self.assertEqual(self.confirm().status_code, 400)

    def test_cancel_and_failed_reverification_revoke_previous_proof(self):
        self.verify()
        self.client.post(self.url, {"action": "cancel"})
        self.assertFalse(AccountDeletionGrant.objects.exists())
        self.verify()
        self.client.post(self.url, {"action": "password", "email": self.user.email, "password": "wrong"})
        self.assertFalse(AccountDeletionGrant.objects.exists())
        self.assertEqual(self.confirm().status_code, 400)

    def test_session_bound_and_not_exposed_in_html(self):
        self.verify()
        token = self.client.session[SESSION_KEY]
        self.assertTrue(AccountDeletionGrant.objects.filter(token_hash=digest(token)).exists())
        self.assertNotContains(self.client.get(self.url), token)
        self.assertEqual(self.confirm(Client()).status_code, 400)

    def test_csrf_required_at_both_stages(self):
        client = Client(enforce_csrf_checks=True)
        self.assertEqual(self.verify(client).status_code, 403)
        client.get(self.url)
        response = client.post(self.url, {"action": "password", "email": self.user.email,
            "password": PASSWORD, "csrfmiddlewaretoken": client.cookies["csrftoken"].value})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.confirm(client).status_code, 403)
        response = self.confirm(client, csrfmiddlewaretoken=client.cookies["csrftoken"].value)
        self.assertEqual(response.status_code, 200)

    def test_account_rate_limit_and_ip_limit(self):
        for i in range(6):
            response = self.client.post(self.url, {"action": "password", "email": "absent@example.com", "password": "wrong"}, REMOTE_ADDR=f"192.0.2.{i}")
        self.assertEqual(response.status_code, 429)
        cache.clear()
        for i in range(21):
            response = self.client.post(self.url, {"action": "invalid"})
        self.assertEqual(response.status_code, 429)
        self.assertEqual(response["Retry-After"], "600")

    def google_claims(self):
        self.client.get(self.url)
        return {"sub": "google-owner", "email_verified": True, "aud": "web-client",
                "iss": "https://accounts.google.com", "nonce": self.client.session["deletion_google_nonce"]}

    def test_google_success_only_with_existing_subject_and_nonce(self):
        self.user.google_sub = "google-owner"
        self.user.save()
        claims = self.google_claims()
        with patch("api.deletion_pages.verify_id_token", return_value=claims):
            response = self.client.post(self.url, {"action": "google", "id_token": "google-secret"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(self.confirm().status_code, 200)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

    def test_google_rejects_wrong_subject_audience_nonce_and_unverified_email(self):
        self.user.google_sub = "google-owner"
        self.user.save()
        claims = self.google_claims()
        for overrides in ({"sub": "other", "email": self.user.email}, {"aud": "android-client"}, {"nonce": "other"}, {"email_verified": False}):
            with patch("api.deletion_pages.verify_id_token", return_value={**claims, **overrides}):
                response = self.client.post(self.url, {"action": "google", "id_token": "secret"})
            self.assertEqual(response.status_code, 400)
        self.assertFalse(AccountDeletionGrant.objects.exists())

    def test_firebase_success_and_rejections(self):
        self.user.firebase_uid = "firebase-owner"
        self.user.save()
        for uid, auth_time in (("other", int(time.time())), ("firebase-owner", int(time.time()) - 301)):
            with patch("api.deletion_pages.verify_firebase_token", return_value=({"uid": uid, "auth_time": auth_time}, self.user.email)):
                self.assertEqual(self.client.post(self.url, {"action": "firebase", "id_token": "secret"}).status_code, 400)
        with patch("api.deletion_pages.verify_firebase_token", return_value=({"uid": "firebase-owner", "auth_time": int(time.time())}, "changed@example.com")):
            self.assertEqual(self.client.post(self.url, {"action": "firebase", "id_token": "secret"}).status_code, 302)
        self.assertEqual(self.confirm().status_code, 200)
        self.assertFalse(User.objects.filter(pk=self.user.pk).exists())

    def test_provider_failures_are_generic_and_no_secrets_are_audited(self):
        for exception, expected in ((FirebaseRejected(), 400), (FirebaseUnavailable(), 503), (RuntimeError("secret-token"), 503)):
            with patch("api.deletion_pages.verify_firebase_token", side_effect=exception):
                response = self.client.post(self.url, {"action": "firebase", "id_token": "secret-token"})
            self.assertEqual(response.status_code, expected)
            self.assertNotContains(response, "secret-token", status_code=expected)
        self.assertFalse(AuditLog.objects.exists())

    @override_settings(DELETION_GOOGLE_CLIENT_ID="", DELETION_FIREBASE_CONFIG={})
    def test_missing_provider_configuration_is_explicit_and_fails_closed(self):
        response = self.client.get(self.url)
        self.assertContains(response, "Google web sign-in is currently unavailable")
        for provider in ("google", "firebase"):
            self.assertEqual(self.client.post(self.url, {"action": provider, "id_token": "secret"}).status_code, 400)

    def test_old_proof_does_not_delete_reregistered_email(self):
        self.verify()
        self.user.delete()
        replacement = User.objects.create_user(email=self.user.email, password=PASSWORD)
        self.assertEqual(self.confirm().status_code, 400)
        self.assertTrue(User.objects.filter(pk=replacement.pk).exists())


class ConcurrentDeletionTests(TransactionTestCase):
    @skipUnlessDBFeature("has_select_for_update")
    def test_two_confirmations_only_one_succeeds(self):
        cache.clear()
        user = User.objects.create_user(email="concurrent@example.com", password=PASSWORD)
        url = reverse("delete-account-page")
        self.client.post(url, {"action": "password", "email": user.email, "password": PASSWORD})
        clients = [Client(), Client()]
        for client in clients:
            client.cookies = self.client.cookies.copy()

        def confirm(client):
            close_old_connections()
            try:
                return client.post(url, {"action": "confirm", "confirmation": "DELETE"}).status_code
            finally:
                close_old_connections()

        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(sorted(pool.map(confirm, clients)), [200, 400])
        self.assertFalse(User.objects.filter(pk=user.pk).exists())
