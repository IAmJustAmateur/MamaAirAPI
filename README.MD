# MamaAir API

Django REST Framework backend for the MamaAir mobile app. The API stores user profile and lifestyle inputs, ingests movement data, computes air quality exposure, and returns dashboard recommendations for pregnancy health risk awareness.

## Features

- JWT authentication for protected mobile endpoints
- Google mobile sign-in
- User profile, pregnancy, consent, language, and lifestyle data
- Wellbeing logs, daily check-ins, and daily task completion
- Mommy and baby symptom checklists, selections, and statistics
- Movement upload via JSON or CSV
- Air quality, weather, UV, exposure history, and dashboard summary
- Swagger/OpenAPI documentation through `drf-spectacular`

## API Documentation

- Swagger UI: `/api/docs/`
- OpenAPI schema: `/api/schema/`
- Mobile developer guide: `docs/mobile_api_guide.md`

Production Swagger URL:

```text
https://api.mamaair.app/api/docs/
```

## Requirements

- Python 3.9+
- Django + Django REST Framework
- SQLite for local development or PostgreSQL for deployed environments
- OpenWeather API key for air quality and weather data

Install Python dependencies:

```bash
pip install --upgrade pip
pip install -r requirements.txt
```

## Environment

Create `.env` next to `manage.py`. Start from `env.dist` when possible.

Common settings:

```env
SECRET_KEY=your_django_secret_key_here
DEBUG=True
DJANGO_ENV=development

OPENWEATHER_API_KEY=your_openweather_api_key_here

POSTGRES_DB=air_quality_db
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
```

## Local Setup

```bash
python -m venv venv
venv\Scripts\activate
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
BASE_URL="https://api.mamaair.app"
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

## E2E API Checks

Run the Django server locally:

```bash
python manage.py runserver
```

Run the current-contract E2E script:

```bash
python scripts/test_server_api.py --env local
```

Run the legacy-contract E2E script to verify older mobile builds still work:

```bash
python scripts/test_server_api_legacy.py --env local
```

Useful overrides:

```bash
python scripts/test_server_api.py --env production
python scripts/test_server_api_legacy.py --env production
python scripts/test_server_api.py --base-url https://api.mamaair.app/
```

The E2E scripts exercise the mobile integration flow: auth, profile, lifestyle, wellbeing, symptoms, movement upload, exposure, summary, and recommendation completion. The legacy script keeps older response assertions for backwards compatibility, while the main script validates the latest API contract.

## Notes for Mobile Developers

- Use Google sign-in as the mobile auth flow.
- Read dropdown values from `GET /api/meta/choices/`.
- `POST /api/wellbeing/log/` adds `water_amount` to the stored daily total.
- `GET /api/daily-tasks/` returns task `category` (`diet`, `activity`, `behavior`, `mental`) for UI grouping.
- `POST /api/task-completion/` replaces the completed task set for the date and returns per-category `counts`.
- `POST /api/symptoms/*/selection/` replaces the selected symptom set for the resolved date.
- `GET /api/summary/` returns `snapshot_id`; use it for `POST /api/recommendation-completion/`.
- `GET /api/air-exposure/` and `GET /api/summary/` may return `204` until movement/exposure data exists.
