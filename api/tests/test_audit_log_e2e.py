"""Real HTTP requests through Django's live server, database and admin UI."""
import os
import requests

from django.contrib.auth.models import Permission
from django.contrib.staticfiles.testing import StaticLiveServerTestCase
from django.core.servers.basehttp import ThreadedWSGIServer
from django.test import override_settings
from django.test.testcases import LiveServerThread
from rest_framework_simplejwt.tokens import RefreshToken

from api.models import AuditLog, MommySymptom, User


class JoinedHTTPServer(ThreadedWSGIServer):
    # Chromium may leave idle connections; join handlers before Python shutdown.
    daemon_threads = False

    def get_request(self):
        sock, address = super().get_request()
        sock.settimeout(5)
        return sock, address


class JoinedServerThread(LiveServerThread):
    server_class = JoinedHTTPServer


@override_settings(
    ALLOWED_HOSTS=["localhost", "127.0.0.1", "testserver"],
    # LiveServer uses HTTP, including when CI loads HTTPS staging settings.
    # Keep CSRF validation enabled, but allow cookies on this test transport.
    CSRF_COOKIE_SECURE=False,
    SESSION_COOKIE_SECURE=False,
)
class AuditLogHTTPTests(StaticLiveServerTestCase):
    server_thread_class = JoinedServerThread

    def test_api_to_database_to_admin_and_permissions(self):
        user = User.objects.create_user(email="audit-http@example.com", password="audit-test-password")
        operator = User.objects.create_superuser(email="audit-admin@example.com", password="admin-test-password")
        symptom = MommySymptom.objects.create(name="Audit E2E symptom")
        token = str(RefreshToken.for_user(user).access_token)
        response = requests.post(
            self.live_server_url + "/api/symptoms/mommy/selection/",
            json={"symptom_ids": [symptom.pk], "latitude": 52.12345, "password": "do-not-store"},
            headers={"Authorization": f"Bearer {token}"}, timeout=10,
        )
        self.assertEqual(response.status_code, 200, response.text)
        log = AuditLog.objects.get(request_id=response.headers["X-Request-ID"])
        self.assertEqual(log.user_id, user.pk)
        self.assertEqual(log.request_body["symptom_ids"], [symptom.pk])
        self.assertEqual(log.request_body["latitude"], "[redacted]")
        self.assertEqual(log.request_body["password"], "[redacted]")

        failure = requests.post(self.live_server_url + "/api/movements/upload/json/",
                                json={"movements": [{"latitude": 51.11, "longitude": 12.22}]}, timeout=10)
        self.assertEqual(failure.status_code, 401)
        self.assertTrue(AuditLog.objects.filter(request_id=failure.headers["X-Request-ID"], status_code=401).exists())

        # Login via the real admin form, including CSRF, and inspect list/detail pages.
        session = requests.Session()
        session.headers["Connection"] = "close"
        self.addCleanup(session.close)
        login_url = self.live_server_url + "/admin/login/"
        session.get(login_url, timeout=10).raise_for_status()
        missing_csrf = session.post(login_url, data={
            "username": operator.email, "password": "admin-test-password",
        }, headers={"Referer": login_url}, timeout=10)
        self.assertEqual(missing_csrf.status_code, 403)
        logged_in = session.post(login_url, data={
            "username": operator.email, "password": "admin-test-password",
            "csrfmiddlewaretoken": session.cookies["csrftoken"], "next": "/admin/api/auditlog/",
        }, headers={"Referer": login_url}, timeout=10)
        self.assertEqual(logged_in.status_code, 200)
        self.assertIn("symptoms-mommy-selection", logged_in.text)
        detail_url = self.live_server_url + f"/admin/api/auditlog/{log.pk}/change/"
        detail = session.get(detail_url, timeout=10)
        self.assertEqual(detail.status_code, 200)
        self.assertIn("symptom_ids", detail.text)
        self.assertNotIn('name="_save"', detail.text)
        self.assertNotIn("52.12345", detail.text)
        self.assertNotIn("do-not-store", detail.text)
        self.assertNotIn(token, detail.text)
        for suffix in ("add/", f"{log.pk}/delete/"):
            self.assertEqual(session.get(self.live_server_url + "/admin/api/auditlog/" + suffix, timeout=10).status_code, 403)
        attempted = session.post(detail_url, data={
            "status_code": 201, "csrfmiddlewaretoken": session.cookies["csrftoken"],
        }, headers={"Referer": detail_url}, timeout=10)
        self.assertEqual(attempted.status_code, 403)
        log.refresh_from_db()
        self.assertEqual(log.status_code, 200)

        operator.is_superuser = False
        operator.save(update_fields=["is_superuser"])
        self.assertEqual(session.get(detail_url, timeout=10).status_code, 403)
        operator.user_permissions.add(Permission.objects.get(codename="view_auditlog", content_type__app_label="api"))
        self.assertEqual(session.get(detail_url, timeout=10).status_code, 200)

        if os.environ.get("AUDIT_BROWSER_E2E") == "1":
            from playwright.sync_api import sync_playwright, expect

            with sync_playwright() as playwright:
                browser = playwright.chromium.launch()
                try:
                    page = browser.new_page()
                    page.goto(login_url + "?next=/admin/api/auditlog/")
                    page.locator("#id_username").fill(operator.email)
                    page.locator("#id_password").fill("admin-test-password")
                    page.locator('input[type="submit"]').click()
                    expect(page).to_have_url(self.live_server_url + "/admin/api/auditlog/")
                    page.locator("#searchbar").fill(str(log.request_id))
                    page.locator("#searchbar").press("Enter")
                    expect(page.locator("#result_list tbody tr")).to_have_count(1)
                    page.goto(detail_url)
                    expect(page.locator(".field-request_body")).to_contain_text("symptom_ids")
                    expect(page.locator('input[name="_save"]')).to_have_count(0)
                    expect(page.locator("body")).not_to_contain_text("52.12345")
                    expect(page.locator("body")).not_to_contain_text("do-not-store")
                finally:
                    browser.close()
