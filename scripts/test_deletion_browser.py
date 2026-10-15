"""Isolated Chromium smoke test for public account deletion; no deployed server."""
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

import requests
from playwright.sync_api import sync_playwright, expect


def main():
    root = Path(__file__).resolve().parents[1]
    artifacts = root / ".e2e-artifacts" / "deletion"
    artifacts.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mamaair-deletion-browser-") as temp:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        url = f"http://127.0.0.1:{port}/delete-account"
        env = {**os.environ, "DJANGO_SETTINGS_MODULE": "agent_api.email_e2e_settings",
               "EMAIL_E2E_ROOT": temp, "DJANGO_ENV": "development", "FIREBASE_CREDENTIALS": "",
               "AUTH_PUBLIC_URL": f"http://127.0.0.1:{port}", "AUTH_REDIS_CACHE_URL": "",
               "DELETION_GOOGLE_CLIENT_ID": "", "DELETION_FIREBASE_API_KEY": ""}
        with (artifacts / "server.log").open("w") as output:
            subprocess.run([sys.executable, "manage.py", "migrate", "--noinput"], cwd=root, env=env,
                           stdout=output, stderr=subprocess.STDOUT, check=True)
            subprocess.run([sys.executable, "manage.py", "shell", "-c",
                "from django.contrib.auth import get_user_model; get_user_model().objects.create_user(email='browser@example.com', password='browser-test-password')"],
                cwd=root, env=env, stdout=output, stderr=subprocess.STDOUT, check=True)
            process = subprocess.Popen([sys.executable, "manage.py", "runserver", f"127.0.0.1:{port}", "--noreload"],
                                       cwd=root, env=env, stdout=output, stderr=subprocess.STDOUT)
            try:
                deadline = time.monotonic() + 30
                while time.monotonic() < deadline:
                    try:
                        if requests.get(url, timeout=1).status_code == 200:
                            break
                    except requests.RequestException:
                        pass
                    time.sleep(.2)
                else:
                    raise RuntimeError("Isolated server did not start")
                with sync_playwright() as p:
                    browser = p.chromium.launch()
                    try:
                        page = browser.new_page(viewport={"width": 390, "height": 844})
                        page.goto(url)
                        expect(page.get_by_role("heading", name="Delete your account")).to_be_visible()
                        page.screenshot(path=str(artifacts / "01-sign-in.png"), full_page=True)
                        page.get_by_label("Email", exact=True).fill("browser@example.com")
                        page.get_by_label("Password", exact=True).fill("browser-test-password")
                        page.get_by_role("button", name="Continue with password").click()
                        expect(page.get_by_text("Verified account:")).to_be_visible()
                        page.reload()  # GET/prefetch cannot consume proof or delete.
                        expect(page.get_by_text("Verified account:")).to_be_visible()
                        page.screenshot(path=str(artifacts / "02-confirm.png"), full_page=True)
                        page.get_by_label("Type DELETE to confirm").fill("delete")
                        page.get_by_role("button", name="Permanently delete my account").click()
                        expect(page.get_by_text("Verified account:")).to_be_visible()
                        page.get_by_label("Type DELETE to confirm").fill("DELETE")
                        with page.expect_response(lambda r: r.url == url and r.request.method == "POST") as result:
                            page.get_by_role("button", name="Permanently delete my account").click()
                        assert result.value.status == 200
                        expect(page.get_by_role("heading", name="Account deleted")).to_be_visible()
                        page.screenshot(path=str(artifacts / "03-success.png"), full_page=True)
                        assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                    finally:
                        browser.close()
                subprocess.run([sys.executable, "manage.py", "shell", "-c",
                    "from django.contrib.auth import get_user_model; assert not get_user_model().objects.filter(email='browser@example.com').exists()"],
                    cwd=root, env=env, stdout=output, stderr=subprocess.STDOUT, check=True)
                print("Public deletion Chromium smoke test passed; screenshots in .e2e-artifacts/deletion.")
            finally:
                process.terminate()
                process.wait(timeout=15)


if __name__ == "__main__":
    main()
