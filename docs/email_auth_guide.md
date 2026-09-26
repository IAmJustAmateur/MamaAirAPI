# Email authentication and asynchronous delivery

Google sign-in and email/password sign-in use the same user and JWT contract.
Existing legacy accounts keep their access. New public email registrations require
confirmation. Migration `0052_user_email_verification_pending` adds one Boolean
field to `User`, defaulting to false for existing accounts. It does not reactivate
blocked accounts. No Celery database tables or result backend are required.

## Mobile requests

For a complete copy/paste registration, verification, login, reset, replay, and
JWT-revocation sequence, see the [mobile curl walkthrough](email_auth_mobile_curl_guide.md).

| Endpoint (POST) | Request | Success |
| --- | --- | --- |
| `/api/auth/email/register/` | `email`, `password`, `password_confirm` | 202 |
| `/api/auth/email/resend/` | `email` | 202 |
| `/api/auth/email/login/` | `email`, `password` | 200, access/refresh/user |
| `/api/auth/email/verify/` | `uid`, `token`, `new_password`, `password_confirm` | 200 |
| `/api/auth/password-reset/request/` | `email` | 202 |
| `/api/auth/password-reset/confirm/` | `uid`, `token`, `new_password`, `password_confirm` | 200 |
| `/api/auth/password-change/` | `old_password`, `new_password` + Bearer access | 200 |

Registration example:

```json
{"email":"user@example.com","password":"Birch!Quartz85-frost","password_confirm":"Birch!Quartz85-frost"}
```

The user receives a `/verify-email?uid=...&token=...` link. The web page asks the
email holder to choose and confirm the final password. They can reuse the password
entered during registration. Choosing the password again prevents a third party
who registered someone else's email from retaining access after confirmation.
Repeated registration never overwrites an existing account's password.

For valid registration input, existing emails return `409 Conflict` and no email
is queued. Email matching is case-insensitive. The mobile app should route by
`code` and display its own localized text:

| Account state | `code` | `detail` | Mobile action |
| --- | --- | --- | --- |
| Active, unverified | `email_verification_required` | This email is already registered but has not been verified. | Offer verification and an explicit `/api/auth/email/resend/` request |
| Verified, including Google accounts | `account_exists` | An account with this email already exists. | Offer sign-in or password recovery |
| Disabled, or ambiguous legacy email records | `account_exists` | An account with this email already exists. | Do not disclose disabled status or reactivate the account |

Responses contain exactly `code` and `detail`. Invalid registration input returns
`400` before the account lookup; rate limits still return `429`. A concurrent
registration that loses the database uniqueness race returns the same `409`
contract. Registration intentionally reports account existence; resend and reset
requests retain their generic `202` responses.

Account passwords must contain 6 to 128 characters. Numeric, common, and
email-similar passwords are accepted; spaces are preserved. This policy applies
to public email registration, verification, reset, authenticated password change,
and the legacy API-key registration endpoint. Confirmation must match wherever
requested. Login does not impose the new minimum on existing passwords.
Django's administrative password-strength validators are unchanged.

Both email-link web forms hide the new password and confirmation initially.
Use **Show passwords** / **Hide passwords** to toggle both fields without changing
their values. The control also works with a keyboard; without JavaScript the
masked forms can still be submitted. The script uses a per-response CSP nonce.

After confirmation, return to the app and POST email/password to the login URL.
The response has `access`, `refresh`, and `user` (`id`, `email`, `avatar_url`,
`provider: "password"`). Google login keeps its current response format.

For reset, send `{"email":"user@example.com"}` to the request endpoint. The
message is the same for unknown, blocked, pending, and eligible accounts:

```json
{"detail":"If the account is eligible, an email will be sent. Please check your inbox."}
```

202 means the request was queued, not that the email has reached the inbox.
The reset email opens `/reset-password?uid=...&token=...`. Both links expire in
48 hours and cannot be reused after a successful password update. Verification
tokens and reset tokens are distinct. GET only displays the form; the state-changing
POST requires CSRF protection on the web page. A future mobile screen can use the
same confirm API with `uid`, `token`, and the two password fields.

Google-only accounts can set their first password through reset; `google_sub` is
preserved, so both login methods work afterward. Pending registrations must use
verification/resend first. Disabled accounts cannot be verified or reset.

Handle 400 for invalid input/link, 401 for rejected login/session, 409 for registration conflicts, 429 for request
limits, and 503 when queue publication fails. For 503 during registration the
account may already exist. A registration retry then returns
`409 email_verification_required`; use resend confirmation to queue a new email.

Auth-related profile fields (`email`, `is_active`, `auth_provider`, `google_sub`,
`email_verification_pending`) are read-only. Email changes need a separate verified
flow. Existing API-key registration/token endpoints remain for compatibility;
new mobile builds should use the public email endpoints above.

## Celery and delivery behavior

Production uses Redis as broker, a shared Redis cache for API throttling, and one
Celery worker consuming the `email` queue. Tasks are published after database
commit. Mail templates include plain text and HTML, use the user's name when
available, and set Reply-To to `service@mamaair.work`.

Tasks contain email, purpose, and an account-state fingerprint, not raw passwords
or reset tokens. The worker skips stale account state, blocked/unknown accounts,
and the wrong confirmation state. Queued requests expire after ten minutes;
the link's 48-hour lifetime starts when the worker generates it. SMTP temporary
failures are retried at most three times with backoff; authentication and other
permanent SMTP failures are logged without retrying. If delivery remains broken,
the user requests a fresh email after service recovery.

SMTP does not provide exactly-once delivery: connection failures after SMTP
acceptance may result in duplicate mail. Celery alone also does not give a durable
database outbox guarantee. Redis persistence reduces loss but does not remove every
failure window. There is no delivery-history UI in this MVP.

## Local verification without Docker

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\venv\Scripts\python.exe scripts\run_email_process_e2e.py
```

The helper creates a temporary database, file-based mail inbox and filesystem
broker, runs migrations, and starts separate Django and Celery processes. It tests
the public HTTP API and both web forms, then stops its own processes and removes
its temporary files. It never uses Gmail. On Windows it uses the solo pool and
pywin32 for this smoke test; Windows is not a supported production Celery platform.
This proves process handoff but does not validate Redis or PostgreSQL behavior.

To submit the verification and reset forms in real headless Chromium (no Docker):

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\venv\Scripts\python.exe -m playwright install chromium
.\venv\Scripts\python.exe scripts\run_email_process_e2e.py --browser
```

This also checks the browser-generated Origin and Referer headers. It reproduces
the old `Origin: null` failure with `no-referrer`, without manually injecting
headers. Local process tests use HTTP; the CI stack below covers real HTTPS.
The scenario registers, verifies and resets using six-character numeric passwords,
then changes to a common password and checks JWT revocation. Chromium additionally
checks the minimum length and shows/hides both fields on both forms, including
keyboard activation and submission while the passwords are visible.

Unit/API tests:

```powershell
$env:MOVEMENT_COORDINATE_KEYS='{"1":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="}'
.\venv\Scripts\python.exe manage.py test -v 1
```

## Redis/PostgreSQL E2E with Docker

After Docker is available, from the repository root:

```powershell
docker compose -f deployment/compose.email-e2e.yml up --build --abort-on-container-exit --exit-code-from tests
docker compose -f deployment/compose.email-e2e.yml down --volumes --remove-orphans
```

The Compose project is named `mamaair-email-e2e`, has its own PostgreSQL, Redis,
web, worker, HTTPS Caddy proxy, Chromium runner and captured email volume, and does not load the repository `.env` or
production secrets. The cleanup command deletes only this test stack's data.
It checks registration, real queue handoff, email contents, native Chromium form
confirmation over HTTPS, login, reset, link replay, and access/refresh revocation. Every run
uses a unique address. CI has a separate `email-auth-e2e` job for this stack.
Only the test runner accepts the private test CA (`--insecure-test-tls`). Do not
use that flag for production. Chromium dependencies are isolated from the production image.

To test an already-running isolated stack with a shared captured-mail directory:

```powershell
.\venv\Scripts\python.exe scripts\test_email_auth_e2e.py --base-url http://127.0.0.1:8000 --mail-dir .e2e-emails
```

## Deployment and Gmail setup

1. Sign in to `noreply.mamaair@gmail.com` and enable Google 2-Step Verification.
2. Open https://myaccount.google.com/apppasswords and create an app password named
   `MamaAir SMTP`. Copy it to the deployment secret store; do not commit or share it.
3. Set the values below in the server `.env` used by both web and worker.

```dotenv
EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend
EMAIL_HOST=smtp.gmail.com
EMAIL_PORT=587
EMAIL_USE_TLS=true
EMAIL_HOST_USER=noreply.mamaair@gmail.com
EMAIL_HOST_PASSWORD=your-app-password-without-spaces
DEFAULT_FROM_EMAIL="MamaAir <noreply.mamaair@gmail.com>"
SUPPORT_EMAIL=service@mamaair.work
AUTH_PUBLIC_URL=https://api.mamaair.work
CELERY_BROKER_URL=redis://redis:6379/0
AUTH_REDIS_CACHE_URL=redis://redis:6379/1
```

App Passwords require 2-Step Verification and may be unavailable for accounts with
Advanced Protection or organization restrictions. Changing the Google account
password revokes existing app passwords. Official instructions:
https://support.google.com/accounts/answer/185833?hl=en

Ensure `GOOGLE_ALLOWED_AUDS` contains the mobile app's valid Google client IDs:
Google tokens with a different audience are now rejected. Preserve the existing
DB, Firebase, public domain, and coordinate-encryption secrets in `.env`.

From the repository root on the deployment host:

```sh
docker compose --env-file .env -f deployment/docker-compose.yml up -d --build
docker compose --env-file .env -f deployment/docker-compose.yml ps
docker compose --env-file .env -f deployment/docker-compose.yml logs --tail=100 celery_worker
```

Web startup applies migrations and collects static files. The worker starts after
web/Redis are healthy. Redis is private and persistent, with no public host port.
The image now uses Python 3.12, matching CI. Caddy forwards HTTPS information and
sets `Referrer-Policy: same-origin`, matching Django's account forms; Django
configures secure form cookies for an HTTPS public URL. A `no-referrer` policy
can cause browsers to send `Origin: null` on native form POSTs, which Django
correctly rejects. Keep CSRF protection enabled and never trust a null origin.
The initial link is redirected to a token-free URL before the form is rendered;
the cleaned URL is only sent as Referer to the same origin, never to other sites.
Caddy applies this header after the upstream response (`>Referrer-Policy`) so
the browser receives one policy rather than duplicate proxy/application values.

### Deploying the form CSRF fix

Pull the updated `codex/email-auth-celery` branch on the server. No new migration
is needed for this fix. Rebuild web/worker and recreate Caddy to load the changed
bind-mounted Caddyfile (rebuilding web alone does not update Caddy's policy):

```sh
docker compose --env-file .env -f deployment/docker-compose.yml up -d --build web celery_worker
docker compose --env-file .env -f deployment/docker-compose.yml up -d --no-deps --force-recreate caddy
```

Open the confirmation link again in a fresh browser tab, not the old form tab.
If the link expired, request a new verification email via `/api/auth/email/resend/`.
Complete verification before requesting password reset. Do not manually clear
`email_verification_pending` to bypass this check.

JWT revocation is enabled: tokens issued before this release lack the required
password fingerprint and require one new login. After a password change/reset,
old access and refresh tokens are rejected. Token lifetime remains 48 hours;
the mobile client must handle 401 by returning to login.

Once SMTP is configured, use an existing active test account whose inbox you own:

```powershell
.\venv\Scripts\python.exe scripts\request_email_delivery.py --base-url https://api.mamaair.work --email your-test-account@example.com
```

This sends one reset request; inspect inbox/spam manually. API acceptance and
SMTP acceptance alone do not prove inbox delivery.

## Rollback

Stop new email traffic and the worker before restoring the previous application
image. Before any code rollback, disable accounts with `email_verification_pending=True`:
old code does not enforce this flag, even if the column is left in the database.
Record those account IDs securely for later recovery. Discard only pending messages
in the dedicated email queue; never flush a shared Redis instance. The additive
column can then remain temporarily, or migration 0052 can be reversed after those
pending accounts are disabled. Already changed passwords and sent messages cannot
be undone. A mobile
release using the new endpoints also needs a compatible rollback plan.
