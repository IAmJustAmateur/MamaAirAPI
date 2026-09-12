"""Account-email E2E. Uses captured mail, never Gmail credentials or private API hooks."""
import argparse
from email import policy
from email.parser import BytesParser
from html.parser import HTMLParser
from pathlib import Path
import re
import time
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

import requests


class FormParser(HTMLParser):
    csrf = None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "input" and attrs.get("name") == "csrfmiddlewaretoken":
            self.csrf = attrs["value"]


def wait_for_mail(directory, recipient, purpose, timeout=30):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        for path in directory.glob("*.log"):
            try:
                message = BytesParser(policy=policy.default).parsebytes(path.read_bytes())
                if recipient not in str(message.get("To", "")):
                    continue
                part = message.get_body(preferencelist=("plain",))
                body = part.get_content() if part else ""
                match = re.search(r"https?://[^\s]+/" + purpose + r"\?[^\s]+", body)
                if match:
                    return match.group(0)
            except (OSError, ValueError, UnicodeError):
                continue  # A worker may still be writing the message.
        time.sleep(0.25)
    raise AssertionError(f"No {purpose} email within {timeout}s; inspect worker/broker logs.")


def run(base_url, mail_dir):
    base_url = base_url.rstrip("/")
    email = f"email-e2e-{uuid4().hex}@example.com"
    password = "Birch!Quartz85-frost"
    new_password = "Ocean!Quartz62-spring"
    session = requests.Session()

    def post(path, body, expected):
        response = session.post(base_url + "/api/auth/" + path + "/", json=body, timeout=15)
        assert response.status_code == expected, f"{path}: expected {expected}, got {response.status_code}: {response.text[:300]}"
        return response.json()

    def form_confirm(url, selected_password):
        assert urlparse(url).netloc == urlparse(base_url).netloc, "Email points outside the test server"
        browser = requests.Session()
        page = browser.get(url, timeout=15)
        assert page.status_code == 200
        assert "token=" not in page.url
        parser = FormParser()
        parser.feed(page.text)
        assert parser.csrf, "CSRF field missing"
        result = browser.post(page.url, data={"csrfmiddlewaretoken": parser.csrf,
                              "new_password": selected_password, "password_confirm": selected_password}, timeout=15)
        assert result.status_code == 200 and "Password saved" in result.text, "Web form confirmation failed"

    register = {"email": email, "password": password, "password_confirm": password}
    post("email/register", register, 202)
    post("email/login", {"email": email, "password": password}, 401)
    verification = wait_for_mail(mail_dir, email, "verify-email")
    form_confirm(verification, password)
    old_tokens = post("email/login", {"email": email, "password": password}, 200)
    known_response = post("password-reset/request", {"email": email}, 202)
    unknown = f"unknown-{uuid4().hex}@example.com"
    assert post("password-reset/request", {"email": unknown}, 202) == known_response
    reset_url = wait_for_mail(mail_dir, email, "reset-password")
    reset_fields = {key: value[0] for key, value in parse_qs(urlparse(reset_url).query).items()}
    form_confirm(reset_url, new_password)
    post("password-reset/confirm", {**reset_fields, "new_password": new_password, "password_confirm": new_password}, 400)
    post("email/login", {"email": email, "password": password}, 401)
    new_tokens = post("email/login", {"email": email, "password": new_password}, 200)
    post("token/refresh", {"refresh": old_tokens["refresh"]}, 401)
    post("token/refresh", {"refresh": new_tokens["refresh"]}, 200)
    profile_url = base_url + "/api/profile/"
    assert session.get(profile_url, headers={"Authorization": "Bearer " + old_tokens["access"]}, timeout=15).status_code == 401
    assert session.get(profile_url, headers={"Authorization": "Bearer " + new_tokens["access"]}, timeout=15).status_code == 200
    print("Email auth E2E passed: register, captured mail, web verification, login, reset, replay, JWT revocation.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--mail-dir", type=Path, required=True)
    args = parser.parse_args()
    run(args.base_url, args.mail_dir)
