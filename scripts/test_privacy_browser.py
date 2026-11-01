"""Exercise the public policy in Chromium against an isolated Django process."""
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
    artifacts = root / ".e2e-artifacts" / "privacy"
    artifacts.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="mamaair-privacy-") as temp:
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base = f"http://127.0.0.1:{port}"
        env = {**os.environ, "DJANGO_SETTINGS_MODULE": "agent_api.email_e2e_settings",
               "EMAIL_E2E_ROOT": temp, "DJANGO_ENV": "development",
               "FIREBASE_CREDENTIALS": "", "AUTH_REDIS_CACHE_URL": "",
               "AUTH_PUBLIC_URL": base, "DELETION_GOOGLE_CLIENT_ID": "",
               "DELETION_FIREBASE_API_KEY": ""}
        with (artifacts / "server.log").open("w") as output:
            subprocess.run([sys.executable, "manage.py", "migrate", "--noinput"],
                           cwd=root, env=env, stdout=output, stderr=subprocess.STDOUT, check=True)
            server_code = (
                "import faulthandler; faulthandler.dump_traceback_later(45); "
                "from django.core.wsgi import get_wsgi_application; "
                "from wsgiref.simple_server import make_server; "
                f"make_server('127.0.0.1', {port}, get_wsgi_application()).serve_forever()"
            )
            process = subprocess.Popen([sys.executable, "-u", "-c", server_code], cwd=root, env=env,
                stdout=output, stderr=subprocess.STDOUT)
            try:
                session = requests.Session()
                session.trust_env = False  # Local readiness must bypass workstation proxies.
                deadline = time.monotonic() + 60
                while time.monotonic() < deadline:
                    if process.poll() is not None:
                        raise RuntimeError("Isolated server exited")
                    try:
                        if session.get(base + "/privacy-policy", timeout=1).status_code == 200:
                            break
                    except requests.RequestException:
                        pass
                    time.sleep(.2)
                else:
                    raise RuntimeError("Isolated server did not start")
                with sync_playwright() as playwright:
                    browser = playwright.chromium.launch()
                    try:
                        for label, width in (("mobile", 390), ("desktop", 1440)):
                            context = browser.new_context(viewport={"width": width, "height": 900})
                            page = context.new_page()
                            errors = []
                            page.on("pageerror", lambda error: errors.append(str(error)))
                            response = page.goto(base + "/privacy-policy")
                            assert response.status == 200
                            expect(page).to_have_title("MamaAir Privacy Policy")
                            expect(page.get_by_role("heading", name="Privacy Policy", exact=True)).to_be_visible()
                            expect(page.get_by_role("heading", name="17. Contact us", exact=True)).to_be_visible()
                            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
                            page.screenshot(path=str(artifacts / f"{label}.png"), full_page=True)
                            page.reload()
                            expect(page.get_by_role("heading", name="17. Contact us", exact=True)).to_be_visible()
                            page.get_by_role("link", name="Delete your account", exact=True).click()
                            expect(page).to_have_url(base + "/delete-account")
                            expect(page.get_by_role("heading", name="Delete your account", exact=True)).to_be_visible()
                            assert not errors, errors
                            context.close()
                    finally:
                        browser.close()
                print("Privacy Chromium E2E passed: mobile, desktop, reload and deletion link.")
            finally:
                process.terminate()
                process.wait(timeout=15)


if __name__ == "__main__":
    main()
