"""Run API + separate Celery worker with a temporary filesystem broker, without Docker.

This checks process boundaries but does not replace the Redis/PostgreSQL Compose E2E.
"""
import argparse
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time

import requests

from test_email_auth_e2e import run, run_with_browser


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--browser", action="store_true", help="Use Chromium for both account forms")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    with tempfile.TemporaryDirectory(prefix="mamaair-email-e2e-") as temp:
        temp_path = Path(temp)
        for folder in ("mail", "queue", "control"):
            (temp_path / folder).mkdir()
        with socket.socket() as sock:
            sock.bind(("127.0.0.1", 0))
            port = sock.getsockname()[1]
        base_url = f"http://127.0.0.1:{port}"
        env = {**os.environ, "DJANGO_SETTINGS_MODULE": "agent_api.email_e2e_settings",
               "EMAIL_E2E_ROOT": temp, "DJANGO_ENV": "development", "FIREBASE_CREDENTIALS": "",
               "AUTH_PUBLIC_URL": base_url, "EMAIL_HOST_PASSWORD": "", "AUTH_REDIS_CACHE_URL": ""}
        processes = []
        logs = []
        try:
            with (temp_path / "migration.log").open("w") as output:
                subprocess.run([sys.executable, "manage.py", "migrate", "--noinput"], cwd=root, env=env, stdout=output, stderr=subprocess.STDOUT, check=True)
            for name, command in (
                ("worker", [sys.executable, "-m", "celery", "-A", "agent_api", "worker", "--pool=solo", "--loglevel=WARNING", "--without-gossip", "--without-mingle", "--without-heartbeat"]),
                ("server", [sys.executable, "manage.py", "runserver", f"127.0.0.1:{port}", "--noreload"]),
            ):
                output = (temp_path / f"{name}.log").open("w")
                logs.append(output)
                processes.append(subprocess.Popen(command, cwd=root, env=env, stdout=output, stderr=subprocess.STDOUT))
            deadline = time.monotonic() + 45
            while time.monotonic() < deadline:
                if any(p.poll() is not None for p in processes):
                    raise RuntimeError("An E2E process exited early")
                try:
                    if requests.get(base_url + "/api/meta/choices/", timeout=1).status_code == 200:
                        break
                except requests.RequestException:
                    pass
                time.sleep(0.25)
            else:
                raise RuntimeError("E2E server did not start")
            runner = run_with_browser if args.browser else run
            runner(base_url, temp_path / "mail")
        except Exception:
            for output in logs:
                output.flush()
            for name in ("migration", "server", "worker"):
                path = temp_path / f"{name}.log"
                if path.exists():
                    print(f"{name} diagnostics:\n{path.read_text(errors='replace')[-5000:]}")
            raise
        finally:
            for process in processes:
                process.terminate()
            for process in processes:
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
            for output in logs:
                output.close()


if __name__ == "__main__":
    main()
