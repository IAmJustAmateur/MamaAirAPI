"""Check final settings after every assignment, not just temporary test overrides."""
import json
import os
from pathlib import Path
import subprocess
import sys

from django.test import SimpleTestCase


class EmailCookieSettingsTests(SimpleTestCase):
    def test_caddy_policies_match_the_account_forms(self):
        deployment = Path(__file__).resolve().parents[2] / "deployment"
        for filename in ("Caddyfile", "Caddyfile.email-e2e"):
            config = (deployment / filename).read_text(encoding="utf-8")
            self.assertIn('>Referrer-Policy "same-origin"', config)
            self.assertNotIn('Referrer-Policy "no-referrer"', config)

    def read_cookies(self, environment, public_url):
        result = subprocess.run(
            [sys.executable, "-c", (
                "import json; from agent_api import settings as s; "
                "print(json.dumps([s.SESSION_COOKIE_SECURE, s.CSRF_COOKIE_SECURE, s.CSRF_TRUSTED_ORIGINS]))"
            )],
            cwd=Path(__file__).resolve().parents[2],
            env={**os.environ, "DJANGO_ENV": environment, "AUTH_PUBLIC_URL": public_url},
            capture_output=True, text=True, check=True, timeout=30,
        )
        return json.loads(result.stdout.splitlines()[-1])

    def test_private_http_staging_accepts_cookies(self):
        self.assertEqual(self.read_cookies("staging", "http://web:8000"),
                         [False, False, ["http://web:8000"]])

    def test_https_production_uses_secure_cookies_and_actual_origin(self):
        self.assertEqual(self.read_cookies("production", "https://api.mamaair.work"),
                         [True, True, ["https://api.mamaair.work"]])

    def test_production_never_downgrades_cookie_security(self):
        self.assertEqual(self.read_cookies("production", "http://invalid.example")[:2],
                         [True, True])
