# Run email authentication tests on the new EC2 server

This guide tests the running API at `https://api-new.mamaair.work`.
Run the commands on the new server, inside the repository's `deployment`
directory. Do not run them on the old production server.

The test sends HTTPS requests through Caddy. Celery writes emails to files
instead of sending them through SMTP. The test reads those files and follows
the confirmation and password-reset links.

This checks PostgreSQL, Redis, Celery, email generation, API endpoints, and web
forms over HTTPS. It does not check real inbox delivery or Google/Firebase login.
It uses HTTP requests for the forms, not a browser.

## 1. Connect and check the services

From your computer:

```sh
ssh mamaair-api-dev
```

Change to the `deployment` directory in your cloned repository. Then run:

```sh
docker compose --env-file ../.env ps -a
free -h
swapon --show
curl --fail --show-error --connect-timeout 10 --max-time 20 https://api-new.mamaair.work/api/meta/choices/
```

Caddy and account_cleanup must be running. Web, PostgreSQL, Redis, and Celery
must be healthy. Resolve errors or restart loops before testing.
The curl command must return HTTP 200 with valid JSON and no TLS error.

## 2. Temporarily save emails to files

Record the previous `EMAIL_BACKEND` and `EMAIL_FILE_PATH` settings so you can
restore them later. Edit `../.env` on the new server. Replace existing entries;
do not add duplicate names:

```dotenv
DJANGO_ENV=production
EMAIL_BACKEND=django.core.mail.backends.filebased.EmailBackend
EMAIL_FILE_PATH=/tmp/mamaair-e2e-mail
AUTH_PUBLIC_URL=https://api-new.mamaair.work
```

Keep the other settings, including database credentials, unchanged.
If this deployment intentionally uses `DJANGO_ENV=staging`, keep that value.
Both `production` and `staging` use PostgreSQL. Other values select SQLite.

While this backend is active, all account emails on this deployment are saved
to files. They are not sent to real inboxes. Use this procedure on the test
deployment before importing real users.

Apply the settings to all three application services:

```sh
docker compose --env-file ../.env config --quiet
docker compose --env-file ../.env up -d --force-recreate web celery_worker account_cleanup
docker compose --env-file ../.env up -d caddy
docker compose --env-file ../.env ps -a
```

A restart alone does not reload `.env`. No image build is needed if the current
image already contains the test script. Wait until the services are ready.

Check the actual settings in each application container. This prints no secrets:

```sh
for service in web celery_worker account_cleanup; do
  echo "Checking $service"
  docker compose --env-file ../.env exec -T "$service" python manage.py shell -c \
    'from django.conf import settings as s; print({"environment": s.DJANGO_ENV, "database_engine": s.DATABASES["default"]["ENGINE"], "email_backend": s.EMAIL_BACKEND, "email_path": s.EMAIL_FILE_PATH, "public_url": s.AUTH_PUBLIC_URL})'
done
```

All three must show PostgreSQL, the file email backend, the same email path,
and the new public URL. A healthy Celery worker alone does not prove that its
database settings are correct.

## 3. Run one test

Run the test inside `celery_worker`, where the email files are written:

```sh
date -Is
docker compose --env-file ../.env exec -T celery_worker \
  python -u scripts/test_email_auth_e2e.py \
  --base-url https://api-new.mamaair.work \
  --mail-dir /tmp/mamaair-e2e-mail
echo "Test exit code: $?"
```

`--mail-dir` is a path inside the worker container, not on your computer or the
EC2 host. Django creates the directory when it writes the first email. No shared
volume is needed because the worker and test use the same container filesystem.
The files are temporary and disappear when that container is removed.

Do not add `--browser` or `--insecure-test-tls` for this run. The standard app
image does not include the browser dependencies, and public TLS must be checked.
Do not run several copies at once or recreate the worker during the test.

Success means exit code `0` and a message starting with `Email auth E2E passed`.
The test covers:

- Registration, duplicate registration, and email confirmation.
- Login, password reset, password change, and rejection of reused links.
- Rejection of old access and refresh tokens after password changes.
- Account deletion and registration with the same email again.

The test creates a unique `email-e2e-...@example.com` account. It deletes that
account during the test, then registers it again. A successful run leaves one
unverified test account. A failed run can also leave test data. This is not a
read-only test, and it does not perform full cleanup.

## 4. If the test fails

Keep the failure output and the test start time. Before recreating containers,
collect recent logs:

```sh
docker compose --env-file ../.env ps -a
docker compose --env-file ../.env logs --since 15m --tail=150 --timestamps web celery_worker account_cleanup caddy
free -h
docker stats --no-stream
```

Review logs before sharing them. Do not share email files: they contain account
confirmation and password-reset links.

| Error | What to check |
| --- | --- |
| No verification/reset email within 30 seconds | Worker health and logs; file backend and path; worker and web database settings. |
| SQLite or `no such table` | `DJANGO_ENV` in the server `.env` and actual container settings. Do not create a separate SQLite database to fix this. |
| Email points outside the test server | `AUTH_PUBLIC_URL`, especially in the worker. |
| TLS error or connection refused | Caddy status and logs, DNS, and ports 80/443. Do not disable certificate checks. |
| HTTP 429 | Rate limits. Wait for the relevant limit window before retrying. Do not clear Redis. |
| SSH/API becomes slow | Check memory, swap activity, and the sysstat history. Stop the test before starting another run. |

If Caddy is stopped, inspect its startup error before recreating it:

```sh
docker inspect agent_api_caddy --format '{{json .State}}'
docker logs --tail=100 agent_api_caddy
```

## 5. Restore real email delivery

Do this after either success or failure. Restore the previous `EMAIL_BACKEND`
and `EMAIL_FILE_PATH` values in `../.env`. For SMTP, the backend is:

```dotenv
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
```

Keep `AUTH_PUBLIC_URL=https://api-new.mamaair.work` and the correct `DJANGO_ENV`.
Do not copy the old production public URL back into this deployment.

```sh
docker compose --env-file ../.env up -d --force-recreate web celery_worker account_cleanup
docker compose --env-file ../.env ps -a
```

Repeat the settings check from step 2 to confirm the intended backend is active.
Recreating the worker also removes the temporary captured email files. Do not
delete database or Redis volumes, and do not use `down -v` for this procedure.

Real SMTP delivery is a separate check. With an existing verified test account
whose inbox you control, replace the example address and run:

```sh
docker compose --env-file ../.env exec -T web \
  python scripts/request_email_delivery.py \
  --base-url https://api-new.mamaair.work \
  --email YOUR_VERIFIED_TEST_EMAIL
```

This requests a password-reset email. Check the inbox/spam folder and confirm
that the link uses the new domain. HTTP 202 alone does not prove delivery.
