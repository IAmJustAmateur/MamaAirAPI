# MamaAir Mobile API Guide

This guide describes the API surface used by the mobile app and follows the E2E flow in `scripts/test_server_api.py`, with Google sign-in as the documented mobile authentication entry point.

## Base URLs

- Local: `http://127.0.0.1:8000/`
- Production: `https://api.mamaair.app/`
- Swagger UI: `/api/docs/`
- OpenAPI schema: `/api/schema/`

All API endpoints below are prefixed with `/api/`.

## Authentication

Protected endpoints require:

```http
Authorization: Bearer <access_token>
```

Access tokens are issued by Google sign-in. Refresh tokens are long-lived and can be exchanged for a new access token.

Google is the only authentication flow documented for the mobile app.

JWT API calls do not require `X-CSRFTOKEN`. Swagger UI may show a CSRF header when it runs in a browser session, but mobile clients should use the Bearer token header.

### Google Sign-In

`POST /api/auth/google/`

Request:

```json
{
  "id_token": "<google_id_token_from_mobile_app>"
}
```

Response:

```json
{
  "access": "<access_token>",
  "refresh": "<refresh_token>",
  "user": {
    "id": 123,
    "email": "user@example.com",
    "avatar_url": "https://example.com/avatar.png",
    "provider": "google"
  }
}
```

### Refresh Access Token

`POST /api/auth/token/refresh/`

```json
{
  "refresh": "<refresh_token>"
}
```

Response:

```json
{
  "access": "<new_access_token>"
}
```

### Logout

`POST /api/auth/logout/`

Requires Bearer auth and the refresh token:

```json
{
  "refresh": "<refresh_token>"
}
```

Success response: `205 Reset Content`

## Recommended Mobile Flow

The E2E script exercises this sequence:

1. Sign in with Google and receive MamaAir `access` and `refresh` JWT tokens.
2. Store `access` and `refresh` tokens securely.
3. `PATCH /api/profile/` with onboarding profile fields.
4. `GET /api/lifestyle/`, then `PATCH /api/lifestyle/`.
5. Load `GET /api/meta/choices/` for dropdown values.
6. Load wellbeing catalog with `GET /api/wellbeing/`.
7. Sync daily wellbeing, check-in, and task completion state.
8. Load symptom checklists and submit selected symptoms.
9. Upload movement points with `POST /api/movements/upload/json/`.
10. Poll `GET /api/air-exposure/` and then load `GET /api/summary/`.
11. Store `summary.snapshot_id` when showing recommendations.
12. Mark recommendation dimensions with `POST /api/recommendation-completion/`.

## Profile

### Get Profile

`GET /api/profile/`

Returns the authenticated user's profile. `bmi` is calculated by the backend when `height` and `weight_pre_pregnancy` are present.

### Update Profile

`PATCH /api/profile/`

Example:

```json
{
  "name": "Jane Doe",
  "date_of_birth": "1994-06-20",
  "height": 168,
  "weight_pre_pregnancy": 64,
  "race": "african",
  "country": "NG",
  "is_first_pregnancy": false,
  "pregnancy_number": 2,
  "week_of_pregnancy": 24,
  "tracking_enabled": true,
  "notifications_enabled": true,
  "notification_window_from": "09:00",
  "notification_window_to": "21:00",
  "timezone": "Africa/Lagos",
  "consent": true,
  "preferred_share_channel": "whatsapp"
}
```

When `week_of_pregnancy` changes, the backend recalculates `pregnancy_start_date`.
When `pregnancy_number` is provided, the backend keeps legacy `is_first_pregnancy` in sync (`1` => `true`, `2+` => `false`).
`notification_window_from` and `notification_window_to` must be sent together in `HH:MM` format and must describe a same-day interval.
`timezone` must be an IANA timezone such as `Africa/Lagos`, `Europe/Minsk`, or `Europe/Warsaw`.

## Meta Choices

`GET /api/meta/choices/`

This endpoint is public and returns supported values for dropdowns:

- `languages`
- `races`
- `countries`
- `work_types`
- `diet_types`
- `cooking_methods`
- `lifestyle_areas`
- `lifestyle_time_spent`
- `lifestyle_time_of_day`
- `exposure_levels`

Use these values when submitting profile and lifestyle forms.

## Lifestyle

### Get Lifestyle

`GET /api/lifestyle/`

If the lifestyle record does not exist yet, the backend creates an empty one.

### Update Lifestyle

`PATCH /api/lifestyle/`

Example:

```json
{
  "average_sleep_hours": 7.5,
  "work_type": "Desk",
  "diet_type": "omnivore",
  "cooking_method": "gas",
  "activity_duration_minutes": 30,
  "standing_hours_per_day": 3,
  "area": "urban",
  "time_spent": "mostly_outdoors",
  "time_of_day": "changes_day_to_day",
  "commute_mode": "car",
  "hydration_target_ml_per_day": 2200,
  "cooking_venue": "indoor",
  "ventilation_level": "medium"
}
```

Lifestyle onboarding choices:

- `area`: `urban`, `peri_urban`, `rural`
- `time_spent`: `mostly_indoors`, `mostly_outdoors`, `both_equally`
- `time_of_day`: `morning_hours`, `midday_or_afternoon`, `evening`, `changes_day_to_day`

## Wellbeing and Daily State

### Catalog

`GET /api/wellbeing/`

Returns water goal, mood chips, and feeling chips. Use returned `id` values in `POST /api/wellbeing/log/`.

### Get Wellbeing Log

`GET /api/wellbeing/log/?date=YYYY-MM-DD`

If no log exists, the backend returns an empty state:

```json
{
  "date": "2026-02-28",
  "water_amount": 0,
  "water_unit": "ml",
  "moods": [],
  "feelings": []
}
```

### Upsert Wellbeing Log

`POST /api/wellbeing/log/`

```json
{
  "date": "2026-02-28",
  "water_amount": 250,
  "water_unit": "ml",
  "mood_ids": [1, 2],
  "feeling_ids": [10]
}
```

Important behavior:

- `water_amount` is additive. Posting `250` adds 250 ml to the stored daily amount.
- `mood_ids` replaces selected moods when provided.
- `feeling_ids` replaces selected feelings when provided.
- Omit `mood_ids` or `feeling_ids` to keep previous selections unchanged.

### Daily Check-In

`GET /api/daily-checkin/?date=YYYY-MM-DD`

```json
{
  "date": "2026-04-21",
  "exists": false
}
```

`POST /api/daily-checkin/`

```json
{
  "date": "2026-04-21"
}
```

Posting the same date twice returns a validation error.

### Daily Tasks

`GET /api/daily-tasks/`

Response is an ordered list:

```json
[
  {
    "code": "drink_water",
    "title": "Drink water",
    "category": "diet",
    "sort_order": 10
  }
]
```

`category` is one of: `diet`, `activity`, `behavior`, `mental`.
`mental` is reserved for future mental wellbeing tasks and may have no active tasks yet.

### Task Completion

`GET /api/task-completion/?date=YYYY-MM-DD`

```json
{
  "date": "2026-04-30",
  "tasks": ["drink_water"],
  "counts": {
    "diet": { "done": 1, "total": 1 },
    "activity": { "done": 0, "total": 1 },
    "behavior": { "done": 0, "total": 1 },
    "mental": { "done": 0, "total": 0 }
  }
}
```

`POST /api/task-completion/`

```json
{
  "date": "2026-04-30",
  "tasks": ["drink_water", "avoid_smoke"],
  "counts": {
    "diet": { "done": 1, "total": 1 },
    "activity": { "done": 0, "total": 1 },
    "behavior": { "done": 1, "total": 1 },
    "mental": { "done": 0, "total": 0 }
  }
}
```

Important behavior: this is replace-all for the date. Send the full desired list. Send an empty list to clear completions.
`counts` contains done/total counts by task category for active tasks.

## Symptoms

### Mommy Symptoms

`GET /api/symptoms/mommy/checklist/`

```json
{
  "symptoms": [
    {"id": 10, "name": "Headache"},
    {"id": 12, "name": "Nausea"}
  ]
}
```

`GET /api/symptoms/mommy/selection/?date=YYYY-MM-DD`

`POST /api/symptoms/mommy/selection/`

```json
{
  "symptom_ids": [10, 12],
  "recorded_at": "2026-04-21T08:30:00+03:00"
}
```

Important behavior: symptom selection is replace-all for the resolved calendar date. Send `symptom_ids: []` to clear the date.

Date resolution priority:

1. `?date=YYYY-MM-DD`
2. `recorded_at`
3. Server current date

### Baby Symptoms

Baby endpoints follow the same selection behavior:

- `GET /api/symptoms/baby/checklist/`
- `GET /api/symptoms/baby/selection/?date=YYYY-MM-DD`
- `POST /api/symptoms/baby/selection/`
- `GET /api/symptoms/baby/statistics/classes/`

### Statistics

Mommy statistics:

- `GET /api/symptoms/mommy/statistics/?date=YYYY-MM-DD`
- `GET /api/symptoms/mommy/statistics/?start_date=YYYY-MM-DD&end_date=YYYY-MM-DD`
- `GET /api/symptoms/mommy/statistics/classes/?date=YYYY-MM-DD`

Baby class statistics:

- `GET /api/symptoms/baby/statistics/classes/?date=YYYY-MM-DD`

If no date range is provided, class statistics use the current week from Monday through today.

## Movement Upload and Exposure

### Preferred JSON Upload

`POST /api/movements/upload/json/`

```json
{
  "movements": [
    {
      "latitude": 52.2297,
      "longitude": 21.0122,
      "timestamp": "2026-04-21T08:00:00+02:00"
    },
    {
      "latitude": 52.2301,
      "longitude": 21.0128,
      "timestamp": "2026-04-21T08:05:00+02:00",
      "indoor": false
    }
  ]
}
```

Success response:

```json
{
  "status": "ok",
  "imported": 24,
  "air_exposure_created": 24,
  "air_exposure_updated": 0,
  "exposures_recomputed": 1,
  "exposure_errors": [],
  "errors": []
}
```

`timestamp` should include a timezone offset when available. After upload, the backend recomputes daily exposure for each affected date.

### CSV Upload

`POST /api/movements/upload/`

Content type: `multipart/form-data`

Field: `file`

CSV:

```csv
latitude,longitude,timestamp
52.229700,21.012200,2026-04-21T08:00:00+02:00
52.230100,21.012800,2026-04-21T08:05:00+02:00
```

### Current Air Exposure

`GET /api/air-exposure/`

Returns the latest air quality, weather, and UV data derived from the user's exposure logs. If the user has no movement/exposure data yet, the endpoint returns `204`.

### Exposure History

`GET /api/exposure/history/`

`GET /api/exposure/history/?days=14`

Response:

```json
{
  "start_date": "2026-04-15",
  "end_date": "2026-04-21",
  "days_requested": 7,
  "items": [
    {
      "date": "2026-04-21",
      "integrated_score": 1.42
    }
  ]
}
```

`days` defaults to 7 and is clamped to the range `1..90`. Missing days are absent from `items`.

## Dashboard Summary

`GET /api/summary/`

This is the main dashboard endpoint. It requires at least one air exposure log; otherwise it returns `204`.

Important fields:

- `snapshot_id`: ID of the generated recommendation snapshot. Use this when marking recommendations complete.
- `aq_weather_uv`: latest AQ/weather/UV payload.
- `mom_exposure` and `baby_exposure`: latest exposure objects or `null`.
- `recommendations`: generated recommendation cards.
- `today_journey`: movement distance for today.
- `daily_checkins`: check-in dates in the current week.
- `water`: today's water state.
- `task_completions`: completed task codes by date for the current week, including per-category `counts`.
- `exposure_history`: last 7 days of integrated exposure scores.
- `pollutant_compliance`: per-pollutant guideline comparison.

## Recommendation Completion

`GET /api/recommendation-completion/?snapshot_id=<snapshot_id>`

`POST /api/recommendation-completion/`

```json
{
  "snapshot_id": 123,
  "rule_id": "alert.pm25.daily",
  "rule_version": 1,
  "dimension": "behavior",
  "status": "done"
}
```

The upsert key is:

- `snapshot_id`
- `rule_id`
- `rule_version`
- `dimension`

Posting the same key again updates `status`.

## Useful cURL Examples

```bash
BASE_URL="http://127.0.0.1:8000"
ACCESS="<access_token>"
REFRESH="<refresh_token>"
GOOGLE_ID_TOKEN="<google_id_token_from_mobile_app>"

# Google sign-in returns MamaAir access and refresh JWT tokens.
curl -X POST "$BASE_URL/api/auth/google/" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d "{\"id_token\":\"$GOOGLE_ID_TOKEN\"}"

curl "$BASE_URL/api/profile/" \
  -H "Accept: application/json" \
  -H "Authorization: Bearer $ACCESS"

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

curl -X POST "$BASE_URL/api/auth/token/refresh/" \
  -H "Accept: application/json" \
  -H "Content-Type: application/json" \
  -d "{\"refresh\":\"$REFRESH\"}"
```

## E2E Verification

Run the Django server first:

```bash
python manage.py runserver
```

Then run the mobile API E2E check:

```bash
python scripts/test_server_api.py --env local
```

Useful overrides:

```bash
python scripts/test_server_api.py --env production
python scripts/test_server_api.py --base-url https://api.mamaair.app/
```
