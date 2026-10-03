import json
from datetime import timedelta
from unittest.mock import patch

import jwt
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework_simplejwt.backends import TokenBackend
from rest_framework_simplejwt.settings import api_settings
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from api.audit import REDACTED, collect_secrets, sanitize
from api.models import AuditLog, User


class ExpiredTokenAuditTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="expired-audit@example.com", password="test-password")
        self.client = APIClient()
        token = AccessToken.for_user(self.user)
        issued = timezone.now() - timedelta(days=3)
        token.set_iat(at_time=issued)
        token.set_exp(from_time=issued, lifetime=timedelta(days=2))
        self.payload = token.payload
        self.backend = token.get_token_backend()

    def encode(self, payload=None, key=None, algorithm=None):
        return jwt.encode(
            self.payload if payload is None else payload,
            self.backend.prepared_signing_key if key is None else key,
            algorithm=algorithm or self.backend.algorithm,
        )

    def request_log(self, token):
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
        response = self.client.get("/api/profile/")
        self.assertEqual(response.status_code, 401)
        log = AuditLog.objects.get(request_id=response["X-Request-ID"])
        self.assertNotIn(token, json.dumps({
            "body": log.response_body, "metadata": log.metadata, "headers": log.request_headers,
        }))
        return log

    def test_expired_access_identifies_owner_without_authenticating(self):
        log = self.request_log(self.encode())
        self.assertEqual(log.user_id, self.user.pk)
        self.assertEqual(log.metadata["user_source"], "expired_access_token")
        self.assertIs(log.metadata["authentication_succeeded"], False)
        self.assertGreater(log.metadata["token_expired_seconds_ago"], 0)
        self.assertIn("token_expired_at", log.metadata)
        self.assertEqual(log.response_body["code"], "token_not_valid")
        self.assertEqual(log.response_body["messages"][0]["token_type"], "access")
        self.assertEqual(log.response_body["messages"][0]["token_class"], "AccessToken")

    def test_forged_or_unsigned_tokens_cannot_attribute_a_user(self):
        for token in (self.encode(key="attacker-controlled-key"),
                      jwt.encode(self.payload, "", algorithm="none"), "invalid.token.value"):
            with self.subTest(token_kind=token.split(".")[0]):
                log = self.request_log(token)
                self.assertIsNone(log.user_id)
                self.assertNotIn("user_source", log.metadata)

    def test_future_nbf_or_iat_and_missing_claims_rejected(self):
        variants = [dict(self.payload, nbf=int((timezone.now() + timedelta(hours=1)).timestamp())),
                    dict(self.payload, iat=int((timezone.now() + timedelta(hours=1)).timestamp())),
                    dict(self.payload, exp="not-a-date"), dict(self.payload, exp=True)]
        for key in ("exp", "iat", api_settings.USER_ID_CLAIM, api_settings.JTI_CLAIM):
            variants.append({k: v for k, v in self.payload.items() if k != key})
        for payload in variants:
            with self.subTest(claims=list(payload)):
                log = self.request_log(self.encode(payload))
                self.assertIsNone(log.user_id)

    def test_refresh_token_is_not_treated_as_expired_access(self):
        token = RefreshToken.for_user(self.user)
        token.set_exp(from_time=timezone.now() - timedelta(days=31), lifetime=timedelta(days=30))
        self.assertIsNone(self.request_log(str(token)).user_id)

    def test_valid_but_revoked_access_is_not_labelled_expired(self):
        token = str(AccessToken.for_user(self.user))
        self.user.set_password("changed-password")
        self.user.save(update_fields=["password"])
        self.assertIsNone(self.request_log(token).user_id)

    def test_deleted_owner_does_not_prevent_logging(self):
        token = self.encode()
        self.user.delete()
        self.assertIsNone(self.request_log(token).user_id)

    def test_issuer_and_audience_checks_are_not_disabled(self):
        backend = TokenBackend(algorithm=self.backend.algorithm,
                               signing_key=self.backend.signing_key,
                               issuer="expected-issuer", audience="expected-audience")
        for claims in ({"iss": "wrong", "aud": "expected-audience"},
                       {"iss": "expected-issuer", "aud": "wrong"}):
            with self.subTest(claims=claims), patch(
                "api.audit_auth.AccessToken.get_token_backend", return_value=backend
            ):
                self.assertIsNone(self.request_log(self.encode(dict(self.payload, **claims))).user_id)

    def test_owner_lookup_failure_keeps_error_log(self):
        # The authenticated-user lookup is skipped for this anonymous 401.
        with patch("api.audit_auth.get_user_model", side_effect=RuntimeError("lookup failed")):
            self.assertIsNone(self.request_log(self.encode()).user_id)

    def test_diagnostic_exception_applies_only_to_known_response_values(self):
        diagnostic = {"code": "token_not_valid", "token_type": "access", "token_class": "AccessToken"}
        self.assertEqual(sanitize(diagnostic, diagnostics=True), diagnostic)
        self.assertEqual(collect_secrets(diagnostic, diagnostics=True), [])
        self.assertTrue(all(value == REDACTED for value in sanitize(diagnostic).values()))
        for value in ("actual-secret-token", {"secret": "hidden"}, ["hidden"]):
            for key in diagnostic:
                self.assertEqual(sanitize({key: value}, diagnostics=True)[key], REDACTED)

    def test_codes_and_actual_tokens_stay_redacted(self):
        body = {"code": "123456", "access": self.encode(), "refresh_token": "refresh-secret"}
        self.assertTrue(all(value == REDACTED for value in sanitize(body, diagnostics=True).values()))
