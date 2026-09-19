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


def run(base_url, mail_dir, browser=None, insecure_test_tls=False):
    base_url = base_url.rstrip("/")
    email = f"email-e2e-{uuid4().hex}@example.com"
    password = "Birch!Quartz85-frost"
    new_password = "Ocean!Quartz62-spring"
    session = requests.Session()
    session.verify = not insecure_test_tls

    def post(path, body, expected):
        response = session.post(base_url + "/api/auth/" + path + "/", json=body, timeout=15)
        assert response.status_code == expected, f"{path}: expected {expected}, got {response.status_code}: {response.text[:300]}"
        return response.json()

    def form_confirm(url, selected_password):
        assert urlparse(url).netloc == urlparse(base_url).netloc, "Email points outside the test server"
        if browser is not None:
            browser_confirm(browser, url, selected_password, insecure_test_tls)
            return
        client = requests.Session()
        client.verify = not insecure_test_tls
        page = client.get(url, timeout=15)
        assert page.status_code == 200
        assert "token=" not in page.url
        parser = FormParser()
        parser.feed(page.text)
        assert parser.csrf, "CSRF field missing"
        # Model a same-origin form submission; Chromium mode checks real headers.
        result = client.post(page.url, data={"csrfmiddlewaretoken": parser.csrf,
                             "new_password": selected_password, "password_confirm": selected_password},
                             headers={"Origin": base_url, "Referer": page.url}, timeout=15)
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


def browser_confirm(browser, url, password, insecure_test_tls):
    """Use native navigation and HTML form POST; never inject Origin or CSRF headers."""
    from playwright.sync_api import expect

    context = browser.new_context(ignore_https_errors=insecure_test_tls)
    try:
        page = context.new_page()
        response = page.goto(url)
        assert response.status == 200, "Account form did not load"
        clean_url = page.url
        assert not urlparse(clean_url).query, "Token was not removed before rendering"
        assert urlparse(clean_url).netloc == urlparse(url).netloc
        page.locator('input[name="new_password"]').fill(password)
        page.locator('input[name="password_confirm"]').fill(password)
        with page.expect_response(lambda r: r.request.method == "POST" and r.url == clean_url) as submitted:
            page.get_by_role("button", name="Save password").click()
        result = submitted.value
        headers = result.request.all_headers()
        origin = f"{urlparse(clean_url).scheme}://{urlparse(clean_url).netloc}"
        assert headers.get("origin") == origin, "Browser form must send its actual Origin, not null"
        assert headers.get("referer") == clean_url, "Referer must contain only the cleaned form URL"
        assert result.status == 200, f"Browser form rejected: HTTP {result.status}"
        expect(page.get_by_role("heading", name="Password saved")).to_be_visible()
        assert response.headers.get("referrer-policy") == "same-origin"
        print(f"Browser form passed: {urlparse(clean_url).path}, same-origin POST, no token in Referer.")
    finally:
        context.close()


def run_with_browser(base_url, mail_dir, insecure_test_tls=False):
    from playwright.sync_api import sync_playwright

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        try:
            run(base_url, mail_dir, browser=browser, insecure_test_tls=insecure_test_tls)
        finally:
            browser.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--mail-dir", type=Path, required=True)
    parser.add_argument("--browser", action="store_true", help="Submit both forms in real Chromium")
    parser.add_argument("--insecure-test-tls", action="store_true", help="Only for isolated E2E with a private test CA")
    args = parser.parse_args()
    runner = run_with_browser if args.browser else run
    runner(args.base_url, args.mail_dir, insecure_test_tls=args.insecure_test_tls)
