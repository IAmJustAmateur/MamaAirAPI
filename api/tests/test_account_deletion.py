import datetime as dt
import os
import tempfile
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.test import override_settings
from django.urls import reverse
from django.utils import timezone
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.token_blacklist.models import OutstandingToken

from api.models import AuditLog, GeneratedSymptomChecklist, SymptomChecklistResponse


User = get_user_model()
PASSWORD = "Birch!Quartz85-frost"


class AccountDeletionTests(APITestCase):
    def setUp(self):
        self.user = User.objects.create_user(
            email="delete-me@example.com",
            password=PASSWORD,
        )
        token_response = self.client.post(
            reverse("email-login"),
            {"email": self.user.email, "password": PASSWORD},
            format="json",
        )
        self.access = token_response.data["access"]
        self.refresh = token_response.data["refresh"]
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {self.access}")
        self.url = reverse("delete-account")

    def test_requires_authentication(self):
        self.client.credentials()
        response = self.client.delete(
            self.url,
            {"confirmation": "DELETE"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_requires_exact_confirmation(self):
        for payload in ({}, {"confirmation": "delete"}, {"confirmation": " DELETE "}):
            with self.subTest(payload=payload):
                response = self.client.delete(self.url, payload, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
                self.assertTrue(User.objects.filter(pk=self.user.pk).exists())

    def test_openapi_exposes_delete_endpoint_and_confirmation_body(self):
        response = self.client.get(
            reverse("schema"),
            HTTP_ACCEPT="application/json",
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        operation = response.json()["paths"]["/api/auth/delete-account/"]["delete"]
        body_schema = operation["requestBody"]["content"]["application/json"]["schema"]
        self.assertEqual(body_schema["required"], ["confirmation"])
        self.assertEqual(
            body_schema["properties"]["confirmation"]["enum"],
            ["DELETE"],
        )

    def test_deletes_account_and_invalidates_tokens(self):
        user_id = self.user.pk
        self.assertTrue(OutstandingToken.objects.filter(user=self.user).exists())
        response = self.client.delete(
            self.url,
            {"confirmation": "DELETE"},
            format="json",
        )
        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(response.content, b"")
        self.assertFalse(User.objects.filter(email=self.user.email).exists())
        self.assertFalse(OutstandingToken.objects.filter(user_id=user_id).exists())
        self.assertEqual(
            self.client.get(reverse("profile")).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )
        self.client.credentials()
        self.assertEqual(
            self.client.post(
                reverse("token_refresh"),
                {"refresh": self.refresh},
                format="json",
            ).status_code,
            status.HTTP_401_UNAUTHORIZED,
        )

    def create_audit_logs(self, user):
        return [
            AuditLog.objects.create(
                user=user,
                method=method,
                path="/api/profile/",
                status_code=status_code,
                duration_ms=1,
            ).pk
            for method, status_code in (("GET", 200), ("POST", 400))
        ]

    def test_deletes_user_audit_logs(self):
        log_ids = self.create_audit_logs(self.user)

        response = self.client.delete(
            self.url, {"confirmation": "DELETE"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertEqual(response.content, b"")
        # Check primary keys so SET_NULL cannot masquerade as deletion.
        self.assertFalse(AuditLog.objects.filter(pk__in=log_ids).exists())

    def test_preserves_other_users_and_anonymous_audit_logs(self):
        other_user = User.objects.create_user(
            email="keep-me@example.com", password=PASSWORD
        )
        self.create_audit_logs(self.user)
        other_log_ids = self.create_audit_logs(other_user)
        anonymous_log_ids = self.create_audit_logs(None)
        preserved_ids = other_log_ids + anonymous_log_ids
        original_logs = list(
            AuditLog.objects.filter(pk__in=preserved_ids).order_by("pk").values()
        )

        response = self.client.delete(
            self.url, {"confirmation": "DELETE"}, format="json"
        )

        self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
        self.assertTrue(User.objects.filter(pk=other_user.pk).exists())
        self.assertEqual(
            list(AuditLog.objects.filter(pk__in=preserved_ids).order_by("pk").values()),
            original_logs,
        )

    def test_restores_audit_logs_when_account_deletion_fails(self):
        log_ids = self.create_audit_logs(self.user)

        def fail_delete(user):
            self.assertFalse(AuditLog.objects.filter(pk__in=log_ids).exists())
            raise RuntimeError("Account deletion failed")

        with patch.object(User, "delete", autospec=True, side_effect=fail_delete):
            with self.assertRaisesMessage(RuntimeError, "Account deletion failed"):
                self.client.delete(
                    self.url, {"confirmation": "DELETE"}, format="json"
                )

        self.assertTrue(User.objects.filter(pk=self.user.pk).exists())
        self.assertEqual(
            AuditLog.objects.filter(pk__in=log_ids, user=self.user).count(),
            len(log_ids),
        )

    def test_deletes_protected_checklist_graph(self):
        checklist = GeneratedSymptomChecklist.objects.create(
            user=self.user,
            checklist_type="mommy",
            local_date=dt.date.today(),
            algorithm_version="account-deletion-test",
        )
        response = SymptomChecklistResponse.objects.create(
            checklist=checklist,
            user=self.user,
            checklist_type="mommy",
            local_date=dt.date.today(),
            recorded_at=timezone.now(),
        )

        result = self.client.delete(
            self.url,
            {"confirmation": "DELETE"},
            format="json",
        )

        self.assertEqual(result.status_code, status.HTTP_204_NO_CONTENT)
        self.assertFalse(GeneratedSymptomChecklist.objects.filter(pk=checklist.pk).exists())
        self.assertFalse(SymptomChecklistResponse.objects.filter(pk=response.pk).exists())

    def test_deletes_uploaded_avatar_file_after_commit(self):
        with tempfile.TemporaryDirectory() as media_root:
            with override_settings(MEDIA_ROOT=media_root):
                self.user.avatar.save("avatar.png", ContentFile(b"avatar"), save=True)
                avatar_path = self.user.avatar.path
                self.assertTrue(os.path.exists(avatar_path))

                with self.captureOnCommitCallbacks(execute=True):
                    response = self.client.delete(
                        self.url,
                        {"confirmation": "DELETE"},
                        format="json",
                    )

                self.assertEqual(response.status_code, status.HTTP_204_NO_CONTENT)
                self.assertFalse(os.path.exists(avatar_path))

    @override_settings(AUTH_PUBLIC_URL="http://testserver")
    def test_deleted_email_can_be_registered_again(self):
        email = self.user.email
        self.client.delete(
            self.url,
            {"confirmation": "DELETE"},
            format="json",
        )
        self.client.credentials()

        with patch("api.tasks.send_account_email.apply_async"):
            with self.captureOnCommitCallbacks(execute=True):
                response = self.client.post(
                    reverse("email-register"),
                    {
                        "email": email,
                        "password": PASSWORD,
                        "password_confirm": PASSWORD,
                    },
                    format="json",
                )

        self.assertEqual(response.status_code, status.HTTP_202_ACCEPTED)
        replacement = User.objects.get(email=email)
        self.assertTrue(replacement.email_verification_pending)
