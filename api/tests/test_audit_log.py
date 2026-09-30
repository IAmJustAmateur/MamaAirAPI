import json
from datetime import timedelta
from io import StringIO
from unittest.mock import patch

from django.contrib import admin
from django.core.management import call_command
from django.db import DatabaseError
from django.http import JsonResponse, StreamingHttpResponse
from django.test import TestCase, override_settings
from django.urls import path
from django.utils import timezone
from rest_framework.test import APIClient
from rest_framework.response import Response
from rest_framework.decorators import api_view
from rest_framework_simplejwt.tokens import RefreshToken

from api.audit import REDACTED, sanitize
from api.models import AuditLog, User


def failing(request):
    raise ValueError("password=never-store-this latitude=52.123")


def echo_error(request):
    return JsonResponse(json.loads(request.body), status=400)


def stream_error(request):
    return StreamingHttpResponse(iter([b"secret-stream"]), status=503)


def ok(request):
    return JsonResponse({"ok": True})


@api_view(["POST"])
def partial_movement(request):
    return Response({"imported": 1, "errors": [{"row": 2, "error": "Missing timestamp"}]}, status=201)


urlpatterns = [
    path("api/failure/", failing),
    path("api/echo/", echo_error),
    path("api/stream/", stream_error),
    path("api/movements/upload/json/", ok, name="movements-upload-json"),
    path("api/partial/", partial_movement, name="movements-upload"),
]


class AuditLogTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(email="audit@example.com", password="test-password")
        self.client = APIClient()
        self.client.credentials(HTTP_AUTHORIZATION=f"Bearer {RefreshToken.for_user(self.user).access_token}")

    def test_symptom_success_records_jwt_user_and_payload(self):
        for kind in ("mommy", "baby"):
            response = self.client.post(f"/api/symptoms/{kind}/selection/", {"symptom_ids": []}, format="json")
            self.assertEqual(response.status_code, 200, response.content)
            log = AuditLog.objects.get(request_id=response["X-Request-ID"])
            self.assertEqual(log.user_id, self.user.pk)
            self.assertEqual(log.request_body, {"symptom_ids": []})
            self.assertEqual(log.response_body["symptom_ids"], [])
            self.assertGreaterEqual(log.duration_ms, 0)
            self.assertNotIn("Authorization", log.request_headers)

    def test_validation_error_and_unauthorized_movement(self):
        response = self.client.post("/api/symptoms/mommy/selection/", {"symptom_ids": "invalid"}, format="json")
        self.assertEqual(response.status_code, 400)
        self.assertIn("symptom_ids", AuditLog.objects.get().response_body)
        self.client.credentials()
        response = self.client.post("/api/movements/upload/json/?latitude=52.123", {
            "movements": [{"latitude": 52.123, "longitude": 13.456}], "password": "secret-pass",
        }, format="json")
        self.assertEqual(response.status_code, 401)
        log = AuditLog.objects.get(request_id=response["X-Request-ID"])
        self.assertIsNone(log.user_id)
        self.assertEqual(log.request_body["movements"][0]["latitude"], REDACTED)
        self.assertEqual(log.query_params["latitude"], REDACTED)
        self.assertNotIn("52.123", json.dumps(log.request_body))

    @override_settings(ROOT_URLCONF=__name__)
    def test_successful_movement_skipped(self):
        self.assertEqual(self.client.post("/api/movements/upload/json/", {}, format="json").status_code, 200)
        self.assertFalse(AuditLog.objects.exists())

    def test_successful_get_skipped(self):
        self.assertEqual(self.client.get("/api/symptoms/mommy/selection/").status_code, 200)
        self.assertFalse(AuditLog.objects.exists())

    @override_settings(ROOT_URLCONF=__name__)
    def test_500_frames_without_exception_message(self):
        self.client.raise_request_exception = False
        response = self.client.get("/api/failure/")
        self.assertEqual(response.status_code, 500)
        log = AuditLog.objects.get()
        self.assertEqual(log.error_type, "ValueError")
        self.assertIn("in failing", log.traceback)
        self.assertNotIn("never-store-this", log.traceback)
        self.assertIsNone(log.response_body)

    @override_settings(ROOT_URLCONF=__name__)
    def test_nested_redaction_and_echoed_values(self):
        payload = {"items": [{"lat": 52.123, "refresh_token": "long-secret-token"}],
                   "symptoms": [1, 2], "message": "long-secret-token at 52.123"}
        response = self.client.post("/api/echo/", payload, format="json")
        self.assertEqual(response.status_code, 400)
        log = AuditLog.objects.get()
        for body in (log.request_body, log.response_body):
            self.assertEqual(body["symptoms"], [1, 2])
            self.assertNotIn("long-secret-token", json.dumps(body))
            self.assertNotIn("52.123", json.dumps(body))

    @override_settings(AUDIT_LOG_MAX_BODY_BYTES=64)
    def test_large_and_invalid_request_bodies_omitted(self):
        for payload in ('{"password": "' + 'x' * 100 + '"}', '{"password":'):
            response = self.client.post("/api/symptoms/mommy/selection/", data=payload, content_type="application/json")
            self.assertEqual(response.status_code, 400)
            log = AuditLog.objects.get(request_id=response["X-Request-ID"])
            self.assertIsNone(log.request_body)
            self.assertIn("request_body_omitted", log.metadata)

    @override_settings(ROOT_URLCONF=__name__)
    def test_streaming_error_does_not_consume_stream(self):
        response = self.client.get("/api/stream/")
        self.assertEqual(b"".join(response.streaming_content), b"secret-stream")
        self.assertEqual(AuditLog.objects.get().metadata["response_body_omitted"], "streaming")

    def test_database_failure_does_not_break_response_or_transaction(self):
        with patch("api.audit.AuditLog.objects.create", side_effect=DatabaseError("secret")):
            response = self.client.post("/api/symptoms/mommy/selection/", {"symptom_ids": []}, format="json")
        self.assertEqual(response.status_code, 200)
        self.assertFalse(AuditLog.objects.exists())

    @override_settings(AUDIT_LOG_ENABLED=False)
    def test_disabled(self):
        self.client.post("/api/symptoms/mommy/selection/", {}, format="json")
        self.assertFalse(AuditLog.objects.exists())

    def test_admin_readonly_and_retention(self):
        self.client.post("/api/symptoms/mommy/selection/", {}, format="json")
        log = AuditLog.objects.get()
        model_admin = admin.site._registry[AuditLog]
        for check in (model_admin.has_add_permission, model_admin.has_change_permission, model_admin.has_delete_permission):
            self.assertFalse(check(None))
        call_command("purge_audit_logs", stdout=StringIO())
        self.assertTrue(AuditLog.objects.exists())
        AuditLog.objects.filter(pk=log.pk).update(timestamp=timezone.now() - timedelta(days=15))
        call_command("purge_audit_logs", stdout=StringIO())
        self.assertFalse(AuditLog.objects.exists())

    def test_deleted_user_keeps_log(self):
        self.client.post("/api/symptoms/mommy/selection/", {}, format="json")
        self.user.delete()
        self.assertIsNone(AuditLog.objects.get().user_id)

    def test_sanitize_aliases(self):
        for name in ("coordinates", "gps", "location", "api_key", "Authorization", "newPassword", "geo", "h3_cell"):
            self.assertEqual(sanitize({name: "hidden"})[name], REDACTED)

    @override_settings(ROOT_URLCONF=__name__)
    def test_partial_movement_error_logged_even_with_201(self):
        response = self.client.post("/api/partial/", {}, format="json")
        self.assertEqual(response.status_code, 201)
        self.assertEqual(AuditLog.objects.get().response_body["errors"][0]["row"], 2)

    def test_404_and_query_repeated_values(self):
        response = self.client.get("/api/unknown/secret-in-path/?tag=a&tag=b&access_token=secret-query")
        self.assertEqual(response.status_code, 404)
        log = AuditLog.objects.get()
        self.assertEqual(log.path, "/api/[unresolved]")
        self.assertEqual(log.query_params, {"tag": ["a", "b"], "access_token": REDACTED})

    def test_csv_error_does_not_capture_uploaded_coordinates(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        response = self.client.post("/api/movements/upload/", {
            "file": SimpleUploadedFile("coordinates.csv", b"latitude,longitude\n52.12345,13.12345", content_type="text/csv"),
        }, format="multipart")
        self.assertGreaterEqual(response.status_code, 400)
        log = AuditLog.objects.get()
        self.assertIsNone(log.request_body)
        self.assertNotIn("52.12345", json.dumps(log.response_body))
        self.assertEqual(log.metadata["response_text_omitted"], "request_body_unavailable")
