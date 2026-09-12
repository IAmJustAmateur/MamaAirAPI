# MamaAir API

Django REST Framework backend for the MamaAir mobile app. The API stores user profile and lifestyle inputs, ingests movement data, computes air quality exposure, and returns dashboard recommendations for pregnancy health risk awareness.

## Features

- JWT authentication for protected mobile endpoints
- Google mobile sign-in
- Verified email/password sign-in and password reset via Celery
- User profile, pregnancy, consent, language, and lifestyle data
- Wellbeing logs, daily check-ins, and daily task completion
- Mommy and baby symptom checklists, selections, and statistics
- Movement upload via JSON or CSV
- Air quality, weather, UV, exposure history, and dashboard summary
- Swagger/OpenAPI documentation through `drf-spectacular`

## API Documentation

- Swagger UI: `/api/docs/`
- OpenAPI schema: `/api/schema/`
- Committed OpenAPI snapshot: `docs/openapi/schema.json`
- Mobile developer guide: `docs/mobile_api_guide.md`
- Email auth, Gmail setup, deployment and rollback: [email auth guide](docs/email_auth_guide.md)

Production Swagger URL:

```text
https://api.mamaair.work/api/docs/
```

The E2E scripts also support explicit deployment targets with `--base-url`.

Regenerate the committed OpenAPI snapshot after an intentional mobile API
contract change:

```bash
python scripts/update_openapi_schema_snapshot.py
```

## Requirements

- Python 3.12, matching CI
- Django 5.2 + Django REST Framework
- SQLite for local development when `DJANGO_ENV=development`
- PostgreSQL for CI, staging, and production
- OpenWeather API key in `OWM_API_KEY` for live air quality/weather lookup

Install Python dependencies:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## Environment

### Email E2E without Docker

Run from the repository root (PowerShell):

```powershell
.\venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\venv\Scripts\python.exe scripts\run_email_process_e2e.py
```

This starts separate API and Celery processes with a temporary SQLite database,
filesystem queue and captured emails. It tests registration, email confirmation,
login, password reset and old-token revocation without Gmail or Docker. It does
not replace the Redis/PostgreSQL E2E check; see the [email auth guide](docs/email_auth_guide.md)
for that command and deployment requirements.

### Application settings

Create `.env` next to `manage.py`. Start from `env.dist` when possible.

Common settings:

```env
SECRET_KEY=your_django_secret_key_here
DEBUG=True
DJANGO_ENV=development
ALLOWED_HOSTS=127.0.0.1,localhost

OWM_API_KEY=your_openweather_api_key_here
REGISTRATION_API_KEY=your-registration-api-key

DB_NAME=agent_api_db
DB_USER=agent_api_user
DB_PASSWORD=your-db-password
DB_HOST=localhost
DB_PORT=5432

# Optional, only when Firebase auth is enabled in the environment.
# FIREBASE_CREDENTIALS=/path/to/firebase_service_account.json

MOVEMENT_H3_RESOLUTION=8
MOVEMENT_COORDINATE_ACTIVE_KEY_VERSION=1
# Local development/E2E example key only. Use a real secret outside local dev.
MOVEMENT_COORDINATE_KEYS={"1":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="}

HEALTH_INSIGHT_SNAPSHOT_FRESH_HOURS=6
```

`ALLOWED_HOSTS` is comma-separated. `MOVEMENT_COORDINATE_KEYS` is a JSON object mapping key versions to base64-encoded 32-byte AES keys; keep real deployment keys in the secret store, never in Git. Leave `FIREBASE_CREDENTIALS` unset locally unless you have a service account file.

## Local Setup

PowerShell:

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

The API will be available at:

```text
http://127.0.0.1:8000/
```

## Authentication Overview

Protected endpoints require:

```http
Authorization: Bearer <access_token>
```

Mobile auth:

- `POST /api/auth/google/`
- `POST /api/auth/token/refresh/`
- `POST /api/auth/logout/`

JWT API calls do not require `X-CSRFTOKEN`; that header may appear in Swagger-generated browser examples, but mobile clients should use Bearer auth.

## Core Mobile Endpoints

All routes are prefixed with `/api/`.

Auth:

- `POST /api/auth/google/`
- `POST /api/auth/token/refresh/`
- `POST /api/auth/logout/`
- `DELETE /api/auth/delete-account/`

Profile and configuration:

- `GET /api/profile/`
- `PATCH /api/profile/`
- `POST /api/profile/avatar/`
- `DELETE /api/profile/avatar/`
- `GET /api/meta/choices/`
- `POST /api/set-language/`
- `GET /api/lifestyle/`
- `PATCH /api/lifestyle/`

Wellbeing:

- `GET /api/wellbeing/`
- `GET /api/wellbeing/log/?date=YYYY-MM-DD`
- `POST /api/wellbeing/log/`
- `GET /api/daily-checkin/?date=YYYY-MM-DD`
- `POST /api/daily-checkin/`
- `GET /api/daily-tasks/`
- `GET /api/task-completion/?date=YYYY-MM-DD`
- `POST /api/task-completion/`
- `GET /api/daily-plan/?date=YYYY-MM-DD`
- `PATCH /api/daily-plan/actions/{action_id}/completion/`

Symptoms:

- `GET /api/symptoms/mommy/checklist/`
- `GET /api/symptoms/mommy/selection/?date=YYYY-MM-DD`
- `POST /api/symptoms/mommy/selection/`
- `GET /api/symptoms/mommy/statistics/`
- `GET /api/symptoms/mommy/statistics/classes/`
- `GET /api/symptoms/baby/checklist/`
- `GET /api/symptoms/baby/selection/?date=YYYY-MM-DD`
- `POST /api/symptoms/baby/selection/`
- `GET /api/symptoms/baby/statistics/classes/`

Exposure and dashboard:

- `POST /api/movements/upload/json/`
- `POST /api/movements/upload/`
- `GET /api/air-exposure/`
- `GET /api/exposure/history/?days=7`
- `GET /api/summary/`
- `GET /api/advice/`
- `GET /api/info/current/`
- `GET /api/exposure-per-weeks/`
- `GET /api/recommendation-completion/`
- `POST /api/recommendation-completion/`

## Quick cURL Examples

Use placeholders for secrets and tokens. Do not commit real JWTs or API keys.

```bash
BASE_URL="<deployment-base-url>"
ACCESS="<access_token>"
REFRESH="<refresh_token>"
GOOGLE_ID_TOKEN="<google_id_token>"

curl -X POST "$BASE_URL/api/auth/google/" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d "{\"id_token\":\"$GOOGLE_ID_TOKEN\"}"

curl -X PATCH "$BASE_URL/api/profile/" \
  -H "Accept: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "Test User",
    "language": "en",
    "date_of_birth": "1990-01-01",
    "height": 178,
    "weight_pre_pregnancy": 70,
    "race": "caucasian",
    "country": "NG",
    "is_first_pregnancy": false,
    "pregnancy_number": 2,
    "week_of_pregnancy": 12,
    "tracking_enabled": true,
    "notifications_enabled": true,
    "notification_window_from": "09:00",
    "notification_window_to": "21:00",
    "timezone": "Africa/Lagos",
    "consent": true
  }'

curl -X POST "$BASE_URL/api/profile/avatar/" \
  -H "Accept: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -F "avatar=@avatar.png"

curl "$BASE_URL/api/profile/" \
  -H "Accept: application/json" \
  -H "Authorization: Bearer $ACCESS"

curl "$BASE_URL/api/lifestyle/" \
  -H "Accept: application/json" \
  -H "Authorization: Bearer $ACCESS"

curl -X POST "$BASE_URL/api/movements/upload/json/" \
  -H "Accept: application/json" \
  -H "Authorization: Bearer $ACCESS" \
  -H "Content-Type: application/json" \
  -d '{"movements":[{"latitude":52.2297,"longitude":21.0122,"timestamp":"2026-04-21T08:00:00+02:00"}]}'

curl "$BASE_URL/api/summary/" \
  -H "Accept: application/json" \
  -H "Authorization: Bearer $ACCESS"
```

## Local Django Tests

Movement ingestion tests need the coordinate encryption key that CI creates automatically. For a local full-suite run in PowerShell, set a temporary test key first:

```powershell
$env:MOVEMENT_COORDINATE_KEYS='{"1":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="}'
.\venv\Scripts\python.exe manage.py test -v 1
```

For Git Bash or Linux/macOS shells:

```bash
MOVEMENT_COORDINATE_KEYS='{"1":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="}' python manage.py test -v 1
```

Other useful local checks:

```bash
python manage.py check
python manage.py makemigrations --check --dry-run
python scripts/update_openapi_schema_snapshot.py
```

## E2E API Checks

Movement upload is part of the full E2E flow, so the Django server process must
have a coordinate encryption key. For local testing, start the server in the first
PowerShell terminal with the temporary test key used by CI:

```powershell
$env:MOVEMENT_COORDINATE_KEYS='{"1":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="}'
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py runserver
```

If the server was already running, stop and restart it after setting the variable.
Setting the key only in the E2E client's terminal does not configure the server.
The all-zero key above is for local tests only; never use it in staging or
production.

In a second PowerShell terminal, run the current-contract E2E script:

```powershell
.\venv\Scripts\python.exe scripts\test_server_api.py --env local
```

Run only the wellbeing-to-mental-Daily-Plan scenario with a fresh test account:

```powershell
.\venv\Scripts\python.exe scripts\test_server_api.py --env local --only mental-wellbeing
```

For this scenario, the script automatically adds a unique suffix to the email on
every run. This is required because a Daily Plan is immutable after it is created;
reusing the same account on the same date could otherwise test yesterday's setup
instead of the new wellbeing answer. To choose the test email prefix explicitly,
add `--email mental-e2e@example.com`.

For local E2E, the server's `REGISTRATION_API_KEY` must match the script's `--reg-api-key` value. The script defaults to `super-secret-mobile-key`, so either use that locally or pass an explicit key:

```powershell
.\venv\Scripts\python.exe scripts\test_server_api.py --env local --reg-api-key your-registration-api-key
```

Alternatively, put the local-only coordinate key in the repository `.env` as
`MOVEMENT_COORDINATE_KEYS`, then restart Django. Environment variables already set
in PowerShell take precedence over `.env`.

Run the legacy-contract E2E script to verify older mobile builds still work:

```bash
python scripts/test_server_api_legacy.py --env local
```

Useful overrides:

```bash
python scripts/test_server_api.py --env production
python scripts/test_server_api_legacy.py --env production
python scripts/test_server_api.py --base-url https://api.mamaair.work/
python scripts/test_server_api.py --base-url https://api.mamaair.work/
```

The E2E scripts exercise the mobile integration flow: auth, profile, lifestyle, Daily Plan completion transitions, symptoms, movement upload, exposure, summary, and recommendation completion. The legacy script keeps older response assertions for backwards compatibility, while the main script validates the latest API contract.

The current-contract E2E also submits the `distressed` wellbeing mood and verifies
that Daily Plan contains a completable `mental` action. If the selected E2E user
already has a Daily Plan for today from an older build, use a fresh `E2E_EMAIL`
because daily plans are intentionally immutable for their date.

## Notes for Mobile Developers

- Use Google sign-in or verified email/password sign-in as the mobile auth flow.
- Read dropdown values from `GET /api/meta/choices/`.
- `POST /api/wellbeing/log/` adds `water_amount` to the stored daily total.
- Mood and feeling answers for the user's current local date can produce a
  wellbeing-based Daily Plan action with `domain: mental`. Missing wellbeing is
  valid and does not prevent Daily Plan from being created.
- Prefer posting the current wellbeing answers before the first Daily Plan GET of
  the day. An already-created plan keeps its existing IDs and content.
- `GET /api/daily-tasks/` returns task `category` (`diet`, `activity`, `behavior`, `mental`) for UI grouping.
- `POST /api/task-completion/` replaces the completed task set for the date and returns per-category `counts`.
- `PATCH /api/daily-plan/actions/{action_id}/completion/` accepts `completed`, `skipped`, or `not_done`; clients only need the action UUID returned by Daily Plan.
- See [Daily Plan: Mobile Integration](docs/daily_plan_mobile_guide.md) for the focused client contract.
- `POST /api/symptoms/*/selection/` replaces the selected symptom set for the resolved date.
- `GET /api/summary/` returns `snapshot_id`; use it for `POST /api/recommendation-completion/`.
- `GET /api/air-exposure/` and `GET /api/summary/` may return `204` until movement/exposure data exists.
