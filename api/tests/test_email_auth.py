from datetime import timedelta
import re
import smtplib
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.db import IntegrityError
from django.test import Client, override_settings
from django.urls import reverse
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import RefreshToken

from api.email_auth import account_state, encoded_uid, registration_conflict, reset_tokens, verification_tokens
from api.tasks import send_account_email

User = get_user_model()
PASSWORD = "Frost!Birch81-cloud"
NEW_PASSWORD = "River!Quartz72-stone"
SIMPLE_PASSWORDS = ("123456", "password", "member@example.com", "a" * 128, " 1234 ")


@override_settings(EMAIL_BACKEND="django.core.mail.backends.locmem.EmailBackend",
                   AUTH_PUBLIC_URL="http://testserver")
class EmailAuthTests(APITestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(email="member@example.com", password=PASSWORD)

    def payload(self, user=None, purpose="reset", password=NEW_PASSWORD):
        user = user or self.user
        generator = reset_tokens if purpose == "reset" else verification_tokens
        return {"uid": encoded_uid(user), "token": generator.make_token(user),
                "new_password": password, "password_confirm": password}

    def post_queued(self, url, data):
        with patch("api.tasks.send_account_email.apply_async") as publish:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(url, data, format="json")
        return response, publish

    def test_registration_normalizes_and_queues_after_commit(self):
        with patch("api.tasks.send_account_email.apply_async") as publish:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(reverse("email-register"), {
                    "email": "New@EXAMPLE.COM", "password": PASSWORD, "password_confirm": PASSWORD})
                publish.assert_not_called()
            publish.assert_called_once()
        self.assertEqual(response.status_code, 202)
        pending = User.objects.get(email="new@example.com")
        self.assertTrue(pending.email_verification_pending)
        self.assertTrue(pending.is_active)

    def test_pending_user_cannot_use_either_login_or_refresh(self):
        self.user.email_verification_pending = True
        self.user.save()
        for url in (reverse("email-login"), reverse("token_obtain_pair")):
            response = self.client.post(url, {"email": self.user.email, "password": PASSWORD})
            self.assertEqual(response.status_code, 401)
        refresh = RefreshToken.for_user(self.user)
        self.assertEqual(self.client.post(reverse("token_refresh"), {"refresh": str(refresh)}).status_code, 401)

    def test_verify_sets_owner_password_and_invalidates_link(self):
        self.user.email_verification_pending = True
        self.user.save()
        payload = self.payload(purpose="verify")
        self.assertEqual(self.client.post(reverse("email-verify"), payload).status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.email_verification_pending)
        self.assertTrue(self.user.check_password(NEW_PASSWORD))
        self.assertFalse(self.user.check_password(PASSWORD))
        self.assertEqual(self.client.post(reverse("email-verify"), payload).status_code, 400)

    def test_registration_never_overwrites_existing_password(self):
        for active, pending, code in ((True, False, "account_exists"),
                                      (True, True, "email_verification_required"),
                                      (False, False, "account_exists"),
                                      (False, True, "account_exists")):
            with self.subTest(active=active, pending=pending):
                cache.clear()
                self.user.is_active = active
                self.user.email_verification_pending = pending
                self.user.save()
                state = account_state(self.user)
                response, publish = self.post_queued(reverse("email-register"), {
                    "email": " " + self.user.email.upper() + " ",
                    "password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD})
                self.assertEqual(response.status_code, 409)
                self.assertEqual(response.data, {
                    "code": code,
                    "detail": ("This email is already registered but has not been verified."
                               if code == "email_verification_required"
                               else "An account with this email already exists.")})
                publish.assert_not_called()
                self.user.refresh_from_db()
                self.assertEqual(account_state(self.user), state)
                self.assertEqual(User.objects.count(), 1)

    def test_registration_conflict_for_google_account_preserves_login_method(self):
        self.user.google_sub = "google-sub"
        self.user.set_unusable_password()
        self.user.save()
        response, publish = self.post_queued(reverse("email-register"), {
            "email": self.user.email, "password": PASSWORD, "password_confirm": PASSWORD})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "account_exists")
        publish.assert_not_called()
        self.user.refresh_from_db()
        self.assertFalse(self.user.has_usable_password())
        self.assertEqual(self.user.google_sub, "google-sub")

    def test_registration_conflict_for_ambiguous_legacy_emails_is_generic(self):
        User.objects.create_user(email=self.user.email.upper(), password=PASSWORD,
                                 email_verification_pending=True)
        response, publish = self.post_queued(reverse("email-register"), {
            "email": self.user.email, "password": PASSWORD, "password_confirm": PASSWORD})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "account_exists")
        self.assertEqual(User.objects.count(), 2)
        publish.assert_not_called()

    def test_concurrent_registration_conflict_after_unique_constraint_failure(self):
        for pending in (False, True):
            cache.clear()
            self.user.email_verification_pending = pending
            self.user.save()
            # Model a stale initial lookup; create_user then hits the real DB
            # uniqueness constraint, and the second lookup sees the winner.
            with patch("api.email_auth.registration_conflict",
                       side_effect=[None, registration_conflict(self.user.email)]):
                response, publish = self.post_queued(reverse("email-register"), {
                    "email": self.user.email, "password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD})
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.data["code"], "email_verification_required" if pending else "account_exists")
            publish.assert_not_called()
            self.user.refresh_from_db()
            self.assertTrue(self.user.check_password(PASSWORD))
            self.assertEqual(User.objects.count(), 1)

    def test_unrelated_registration_integrity_error_is_not_hidden(self):
        with patch.object(User.objects, "create_user", side_effect=IntegrityError("unrelated")), \
                patch("api.email_auth.queue_email") as queue:
            with self.assertRaises(IntegrityError):
                self.client.post(reverse("email-register"), {
                    "email": "new@example.com", "password": PASSWORD, "password_confirm": PASSWORD})
        queue.assert_not_called()

    def test_registration_queue_failure_recovers_via_explicit_resend(self):
        from api.email_auth import EmailUnavailable

        data = {"email": "new@example.com", "password": PASSWORD, "password_confirm": PASSWORD}
        with patch("api.email_auth.queue_email", side_effect=EmailUnavailable):
            self.assertEqual(self.client.post(reverse("email-register"), data).status_code, 503)
        response, publish = self.post_queued(reverse("email-register"), data)
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.data["code"], "email_verification_required")
        publish.assert_not_called()
        response, publish = self.post_queued(reverse("email-resend"), {"email": data["email"]})
        self.assertEqual(response.status_code, 202)
        publish.assert_called_once()

    def test_existing_email_still_requires_valid_registration_input(self):
        response, publish = self.post_queued(reverse("email-register"), {
            "email": self.user.email, "password": PASSWORD, "password_confirm": "different"})
        self.assertEqual(response.status_code, 400)
        publish.assert_not_called()

    def test_simple_passwords_work_for_registration_verification_and_login(self):
        for index, password in enumerate(SIMPLE_PASSWORDS):
            with self.subTest(password=password):
                cache.clear()
                email = f"simple-{index}@example.com"
                response, publish = self.post_queued(reverse("email-register"), {
                    "email": email, "password": password, "password_confirm": password})
                self.assertEqual(response.status_code, 202)
                publish.assert_called_once()
                user = User.objects.get(email=email)
                self.assertTrue(user.check_password(password))
                self.assertNotEqual(user.password, password)
                self.assertTrue(user.email_verification_pending)
                payload = self.payload(user=user, purpose="verify", password=password)
                self.assertEqual(self.client.post(reverse("email-verify"), payload).status_code, 200)
                self.assertEqual(self.client.post(reverse("email-login"), {
                    "email": email, "password": password}).status_code, 200)

    def test_simple_passwords_work_for_reset_and_login(self):
        for password in SIMPLE_PASSWORDS:
            with self.subTest(password=password):
                cache.clear()
                self.assertEqual(self.client.post(reverse("password-reset-confirm"),
                                                  self.payload(password=password)).status_code, 200)
                self.user.refresh_from_db()
                self.assertTrue(self.user.check_password(password))
                self.assertEqual(self.client.post(reverse("email-login"), {
                    "email": self.user.email, "password": password}).status_code, 200)

    def test_simple_passwords_work_for_authenticated_change(self):
        old_password = PASSWORD
        for password in SIMPLE_PASSWORDS:
            with self.subTest(password=password):
                cache.clear()
                self.client.force_authenticate(self.user)
                response = self.client.post(reverse("password-change"), {
                    "old_password": old_password, "new_password": password})
                self.assertEqual(response.status_code, 200)
                self.user.refresh_from_db()
                self.assertTrue(self.user.check_password(password))
                self.client.force_authenticate(user=None)
                self.assertEqual(self.client.post(reverse("email-login"), {
                    "email": self.user.email, "password": password}).status_code, 200)
                old_password = password

    def test_existing_short_password_still_allows_login_and_change(self):
        self.user.set_password("12345")
        self.user.save()
        tokens = self.client.post(reverse("email-login"), {
            "email": self.user.email, "password": "12345"})
        self.assertEqual(tokens.status_code, 200)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + tokens.data["access"])
        response = self.client.post(reverse("password-change"), {
            "old_password": "12345", "new_password": "123456"})
        self.assertEqual(response.status_code, 200)

    def test_password_length_and_confirmation_rejections_preserve_account(self):
        invalid_pairs = (("", ""), ("12345", "12345"), ("a" * 129, "a" * 129),
                         (None, None), ("123456", "654321"), ("123456", ""))
        for password, confirmation in invalid_pairs:
            with self.subTest(password=password, confirmation=confirmation):
                cache.clear()
                response, publish = self.post_queued(reverse("email-register"), {
                    "email": "new@example.com", "password": password, "password_confirm": confirmation})
                self.assertEqual(response.status_code, 400)
                publish.assert_not_called()
                self.assertFalse(User.objects.filter(email="new@example.com").exists())
                for purpose, endpoint in (("verify", "email-verify"), ("reset", "password-reset-confirm")):
                    self.user.email_verification_pending = purpose == "verify"
                    self.user.save()
                    payload = {**self.payload(purpose=purpose, password=password),
                               "password_confirm": confirmation}
                    response = self.client.post(reverse(endpoint), payload, format="json")
                    self.assertEqual(response.status_code, 400)
                    self.user.refresh_from_db()
                    self.assertTrue(self.user.check_password(PASSWORD))
                    self.assertEqual(self.user.email_verification_pending, purpose == "verify")

    def test_password_change_rejects_invalid_length_and_wrong_old_password(self):
        self.client.force_authenticate(self.user)
        for password in ("", "12345", "a" * 129, None):
            with self.subTest(password=password):
                response = self.client.post(reverse("password-change"), {
                    "old_password": PASSWORD, "new_password": password}, format="json")
                self.assertEqual(response.status_code, 400)
        response = self.client.post(reverse("password-change"), {
            "old_password": "wrong", "new_password": "123456"})
        self.assertEqual(response.status_code, 400)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(PASSWORD))

    def test_reset_request_generic_and_always_queues(self):
        responses = []
        for email in (self.user.email, "unknown@example.com"):
            response, publish = self.post_queued(reverse("password-reset-request"), {"email": email})
            self.assertEqual(response.status_code, 202)
            publish.assert_called_once()
            responses.append(response.data)
        self.assertEqual(*responses)

    def test_broker_failure_returns_503_for_known_and_unknown_email(self):
        for email in (self.user.email, "unknown@example.com"):
            with patch("api.tasks.send_account_email.apply_async", side_effect=OSError("offline")):
                from api.email_auth import queue_email, EmailUnavailable
                with self.assertRaises(EmailUnavailable):
                    with self.captureOnCommitCallbacks(execute=True):
                        queue_email(email, "reset")
        with patch("api.email_auth.queue_email", side_effect=EmailUnavailable):
            response = self.client.post(reverse("password-reset-request"), {"email": self.user.email})
        self.assertEqual(response.status_code, 503)

    def test_reset_revokes_access_refresh_and_old_password(self):
        tokens = self.client.post(reverse("email-login"), {"email": self.user.email.upper(), "password": PASSWORD}).data
        payload = self.payload()
        self.assertEqual(self.client.post(reverse("password-reset-confirm"), payload).status_code, 200)
        self.assertEqual(self.client.post(reverse("password-reset-confirm"), payload).status_code, 400)
        self.assertEqual(self.client.post(reverse("token_refresh"), {"refresh": tokens["refresh"]}).status_code, 401)
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + tokens["access"])
        self.assertEqual(self.client.get(reverse("profile")).status_code, 401)
        self.client.credentials()
        self.assertEqual(self.client.post(reverse("email-login"), {"email": self.user.email, "password": PASSWORD}).status_code, 401)
        self.assertEqual(self.client.post(reverse("email-login"), {"email": self.user.email, "password": NEW_PASSWORD}).status_code, 200)

    def test_expired_malformed_and_wrong_purpose_tokens(self):
        payload = self.payload()
        with patch.object(reset_tokens, "_now", return_value=reset_tokens._now() + timedelta(hours=48, seconds=1)):
            self.assertEqual(self.client.post(reverse("password-reset-confirm"), payload).status_code, 400)
        for changes in ({"uid": "bad"}, {"token": "bad"}, {"token": verification_tokens.make_token(self.user)}):
            self.assertEqual(self.client.post(reverse("password-reset-confirm"), {**payload, **changes}).status_code, 400)

    def test_disabled_user_cannot_reset_or_verify(self):
        for purpose, url in (("reset", "password-reset-confirm"), ("verify", "email-verify")):
            self.user.email_verification_pending = purpose == "verify"
            self.user.is_active = False
            self.user.save()
            self.assertEqual(self.client.post(reverse(url), self.payload(purpose=purpose)).status_code, 400)

    def test_google_user_can_set_first_password(self):
        self.user.google_sub = "google-sub"
        self.user.set_unusable_password()
        self.user.save()
        self.assertEqual(self.client.post(reverse("password-reset-confirm"), self.payload()).status_code, 200)
        self.user.refresh_from_db()
        self.assertTrue(self.user.has_usable_password())
        self.assertEqual(self.user.google_sub, "google-sub")

    def test_profile_cannot_mutate_auth_fields(self):
        self.client.force_authenticate(self.user)
        self.client.patch(reverse("profile"), {"email": "attacker@example.com", "is_active": False,
                         "google_sub": "fake", "email_verification_pending": True}, format="json")
        self.user.refresh_from_db()
        self.assertEqual(self.user.email, "member@example.com")
        self.assertTrue(self.user.is_active)
        self.assertIsNone(self.user.google_sub)
        self.assertFalse(self.user.email_verification_pending)

    def test_worker_renders_real_multipart_mail(self):
        send_account_email.run(self.user.email, "reset", account_state(self.user))
        message = mail.outbox[0]
        self.assertEqual(message.to, [self.user.email])
        self.assertEqual(message.reply_to, ["service@mamaair.work"])
        self.assertIn("48 hours", message.body)
        self.assertTrue(message.alternatives)
        url = next(line for line in message.body.splitlines() if line.startswith("http"))
        payload = {key: value[0] for key, value in parse_qs(urlparse(url).query).items()}
        self.assertTrue(reset_tokens.check_token(self.user, payload["token"]))

    def test_worker_skips_unknown_disabled_pending_or_changed_state(self):
        before = len(getattr(mail, "outbox", []))
        send_account_email.run("unknown@example.com", "reset", None)
        send_account_email.run(self.user.email, "reset", "stale-state")
        self.user.is_active = False
        self.user.save()
        send_account_email.run(self.user.email, "reset", account_state(self.user))
        self.assertEqual(len(getattr(mail, "outbox", [])), before)

    def test_retry_only_for_temporary_smtp_failure(self):
        for error in (OSError("offline"), smtplib.SMTPResponseException(451, b"temporary")):
            with patch("api.tasks.EmailMultiAlternatives.send", side_effect=error), patch.object(send_account_email, "retry", side_effect=RuntimeError("retry")) as retry:
                with self.assertRaises(RuntimeError):
                    send_account_email.run(self.user.email, "reset", account_state(self.user))
                retry.assert_called_once()
        with patch("api.tasks.EmailMultiAlternatives.send", side_effect=smtplib.SMTPAuthenticationError(535, b"credentials")), patch.object(send_account_email, "retry") as retry:
            with self.assertRaises(RuntimeError):
                send_account_email.run(self.user.email, "reset", account_state(self.user))
            retry.assert_not_called()

    def test_web_page_strips_token_and_requires_csrf(self):
        client = Client(enforce_csrf_checks=True)
        payload = self.payload()
        response = client.get("/reset-password", {"uid": payload["uid"], "token": payload["token"]})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response["Location"], "/reset-password")
        response = client.get(response["Location"])
        self.assertNotContains(response, payload["token"])
        self.assertEqual(response["Referrer-Policy"], "same-origin")
        self.assertEqual(client.post("/reset-password", payload).status_code, 403)
        payload["csrfmiddlewaretoken"] = client.cookies["csrftoken"].value
        self.assertContains(client.post("/reset-password", payload), "Password saved")

    def test_web_forms_use_scoped_scripts_and_accept_simple_passwords(self):
        for purpose, path in (("verify", "/verify-email"), ("reset", "/reset-password")):
            with self.subTest(purpose=purpose):
                self.user.email_verification_pending = purpose == "verify"
                self.user.save()
                client = Client(enforce_csrf_checks=True)
                payload = self.payload(purpose=purpose, password="123456")
                response = client.get(path, {"uid": payload["uid"], "token": payload["token"]}, follow=True)
                nonce = re.search(r'<script nonce="([^"]+)"', response.content.decode())[1]
                directives = response["Content-Security-Policy"].split("; ")
                script_policy = next(value for value in directives if value.startswith("script-src "))
                self.assertEqual(script_policy, f"script-src 'nonce-{nonce}'")
                self.assertContains(response, 'type="password"', count=2)
                self.assertContains(response, 'minlength="6"', count=2)
                self.assertContains(response, 'maxlength="128"', count=2)
                self.assertContains(response, 'type="button" id="password-visibility"')
                self.assertIn("no-store", response["Cache-Control"])
                self.assertNotEqual(client.get(path)["Content-Security-Policy"], response["Content-Security-Policy"])
                form = {"new_password": "123456", "password_confirm": "654321",
                        "csrfmiddlewaretoken": client.cookies["csrftoken"].value}
                rejected = client.post(path, form)
                self.assertContains(rejected, "Passwords do not match")
                self.assertNotContains(rejected, 'value="123456"')
                form["password_confirm"] = "123456"
                self.assertContains(client.post(path, form), "Password saved")
                self.user.refresh_from_db()
                self.assertTrue(self.user.check_password("123456"))

    def test_https_forms_accept_same_origin_and_referer_fallback(self):
        for purpose, path in (("verify", "/verify-email"), ("reset", "/reset-password")):
            for headers in ({"HTTP_ORIGIN": "https://testserver"},
                            {"HTTP_REFERER": "https://testserver" + path}):
                with self.subTest(purpose=purpose, headers=headers):
                    self.user.email_verification_pending = purpose == "verify"
                    self.user.save()
                    client = Client(enforce_csrf_checks=True)
                    payload = self.payload(purpose=purpose)
                    response = client.get(path, {"uid": payload["uid"], "token": payload["token"]}, secure=True)
                    self.assertEqual(response["Location"], path)
                    response = client.get(path, secure=True)
                    self.assertEqual(response["Referrer-Policy"], "same-origin")
                    self.assertNotContains(response, payload["token"])
                    form = {"new_password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD,
                            "csrfmiddlewaretoken": client.cookies["csrftoken"].value}
                    self.assertContains(client.post(path, form, secure=True, **headers), "Password saved")

    def test_https_forms_still_reject_null_foreign_and_missing_origins(self):
        for purpose, path in (("verify", "/verify-email"), ("reset", "/reset-password")):
            self.user.email_verification_pending = purpose == "verify"
            self.user.save()
            client = Client(enforce_csrf_checks=True)
            payload = self.payload(purpose=purpose)
            client.get(path, {"uid": payload["uid"], "token": payload["token"]}, secure=True)
            client.get(path, secure=True)
            form = {"new_password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD,
                    "csrfmiddlewaretoken": client.cookies["csrftoken"].value}
            for headers in ({"HTTP_ORIGIN": "null"}, {"HTTP_ORIGIN": "https://untrusted.example"}, {}):
                self.assertEqual(client.post(path, form, secure=True, **headers).status_code, 403)
            self.assertEqual(client.post(path, {"new_password": NEW_PASSWORD, "password_confirm": NEW_PASSWORD},
                                         secure=True, HTTP_ORIGIN="https://testserver").status_code, 403)
            self.user.refresh_from_db()
            self.assertEqual(self.user.email_verification_pending, purpose == "verify")
            self.assertTrue(self.user.check_password(PASSWORD))

    def test_email_request_throttled(self):
        for _ in range(5):
            response, _ = self.post_queued(reverse("password-reset-request"), {"email": self.user.email})
            self.assertEqual(response.status_code, 202)
        response, publish = self.post_queued(reverse("password-reset-request"), {"email": self.user.email})
        self.assertEqual(response.status_code, 429)
        publish.assert_not_called()

    def test_non_object_request_returns_validation_error(self):
        response = self.client.post(reverse("password-reset-request"), ["invalid"], format="json")
        self.assertEqual(response.status_code, 400)

    def test_reset_link_is_still_valid_at_48_hours(self):
        now = reset_tokens._now().replace(microsecond=0)
        with patch.object(reset_tokens, "_now", return_value=now):
            payload = self.payload()
        with patch.object(reset_tokens, "_now", return_value=now + timedelta(hours=48)):
            self.assertEqual(self.client.post(reverse("password-reset-confirm"), payload).status_code, 200)

    def test_password_change_preserves_whitespace_and_revokes_tokens(self):
        tokens = self.client.post(reverse("email-login"), {"email": self.user.email, "password": PASSWORD}).data
        self.client.credentials(HTTP_AUTHORIZATION="Bearer " + tokens["access"])
        response = self.client.post(reverse("password-change"), {"old_password": PASSWORD, "new_password": " " + NEW_PASSWORD + " "})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.client.get(reverse("profile")).status_code, 401)
        self.client.credentials()
        self.assertEqual(self.client.post(reverse("token_refresh"), {"refresh": tokens["refresh"]}).status_code, 401)
        self.user.refresh_from_db()
        self.assertTrue(self.user.check_password(" " + NEW_PASSWORD + " "))

    @override_settings(GOOGLE_ALLOWED_AUDS="expected-client")
    def test_google_audience_and_pending_account_link(self):
        claims = {"aud": "wrong", "iss": "https://accounts.google.com", "sub": "sub1", "email": self.user.email, "email_verified": True}
        with patch("api.auth_views.verify_id_token", return_value=claims):
            self.assertEqual(self.client.post(reverse("auth-google"), {"id_token": "test"}).status_code, 401)
        claims["aud"] = "expected-client"
        self.user.email_verification_pending = True
        self.user.save()
        with patch("api.auth_views.verify_id_token", return_value=claims):
            self.assertEqual(self.client.post(reverse("auth-google"), {"id_token": "test"}).status_code, 200)
        self.user.refresh_from_db()
        self.assertFalse(self.user.has_usable_password())
        self.assertFalse(self.user.email_verification_pending)
