# Codex Handoff: MamaAir API

## Repository

- Project: MamaAir API / `aq_agent_api`
- GitHub: `https://github.com/IAmJustAmateur/aq_agent_api.git`
- Main development branch after the latest PR: `master`
- Last completed feature branch: `codex/recommendation-engine-level3`
- Latest completed PR: `#15 Add level 3 recommendation rules`
- PR URL: `https://github.com/IAmJustAmateur/aq_agent_api/pull/15`
- PR state: merged into `master`
- Merge commit: `53fc1f54400c79ee834bd9f1e0bfa71419880ed9`
- Feature commit: `23be9fc Add level 3 recommendation rules`

When continuing on a new machine, start from the current remote `master` unless the user explicitly asks to inspect or extend the old feature branch.

## Project Overview

This is a Django REST Framework backend for the MamaAir mobile app. It stores user profile, pregnancy, lifestyle, wellbeing, symptom, movement, air quality, weather, and exposure data. It exposes mobile API endpoints for authentication, profile setup, lifestyle, symptoms, movement upload, air exposure, dashboard summary, advice, and recommendation completion.

The recommendation engine lives mainly in the `recommendations` app and is used by summary/advice flows to produce pregnancy health risk awareness recommendations.

Important areas:

- `api/`: main mobile API models, serializers, views, auth, exposure, air quality, weather, wellbeing, and dashboard logic.
- `recommendations/`: recommendation rules, evaluator, context builder, fallbacks, migrations, and recommendation-specific tests.
- `scripts/test_server_api.py`: local/server e2e API smoke test script.
- `docs/mobile_api_guide.md`: mobile API guide.
- `README.MD`: project setup and endpoint overview.

## Local Development Notes

Typical local setup:

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

The project uses a `.env` next to `manage.py`. Start from `env.dist` if needed. Common local settings include:

- `SECRET_KEY`
- `DEBUG=True`
- `DJANGO_ENV=development`
- `OPENWEATHER_API_KEY`
- PostgreSQL settings for deployed-style environments, or SQLite for local development.

Swagger/OpenAPI:

- Local Swagger: `/api/docs/`
- Local schema: `/api/schema/`
- Production Swagger: `https://api.mamaair.app/api/docs/`

## Current Development Stage

The latest completed work updated the recommendation engine to support Level 3 recommendation rules derived from the uploaded document `recomendations_engine.odt` from the previous workstation.

The original document path on the previous machine was:

```text
C:\Users\ighiz\OneDrive\D\BSI\MamaAir\recomendations_engine.odt
```

Do not assume this file exists on a new machine. The implemented rules are already captured in the merged code and migration.

## Latest Completed Work

PR #15 added and tested Level 3 recommendation rules.

Changed files:

- `recommendations/context.py`
- `recommendations/migrations/0008_level3_recommendation_engine_rules.py`
- `recommendations/tests/test_context.py`
- `recommendations/tests/test_rules_medical.py`
- `recommendations/tests/test_advice_recommendations.py`
- `scripts/test_server_api.py`

Main implementation details:

- Added new recommendation migration `0008_level3_recommendation_engine_rules.py`.
- Expanded recommendation context with additional lifestyle fields.
- Added symptom aliases used by the rules.
- Added latest `AirExposureLog` weather/AQ data into recommendation context.
- Added or updated Level 3 medical, air quality, heat, cooking, and outdoor activity rules.
- Updated unit/API tests for context and recommendation rule behavior.
- Updated `scripts/test_server_api.py` to validate new Level 3 recommendations through `/api/summary/`.

New or newly validated rule IDs:

- `alert.prom`
- `alert.fetal_hypoxia`
- `alert.hyperemesis`
- `alert.anemia`
- `alert.cardiovascular`
- `alert.heat.high`
- `alert.cooking.indoor_solid_fuel`
- `alert.outdoor.midday`
- `alert.pm25.daily`
- `alert.cooking.solid_fuel`

Also updated existing rule behavior for:

- placental abruption
- preeclampsia
- preterm labor
- gestational diabetes mellitus
- low birth weight risk
- PM2.5
- solid fuel cooking
- gas cooking with high NO2

Important logic fixes from the latest work:

- Preterm labor no longer double-counts contraction symptoms through both alias and canonical names.
- Preeclampsia uses `20w+` as a gate and then requires enough clinical indicators, instead of counting gestational age itself as one of the symptoms.
- `scripts/test_server_api.py` now validates the new recommendations explicitly, not just the old PM2.5 debug exposure path.

## Verification Already Performed

These checks passed on the previous workstation before PR #15 was merged:

```powershell
.\venv\Scripts\python.exe manage.py test recommendations.tests -v 1
```

Result:

```text
Ran 31 tests
OK
```

Local e2e/API check:

```powershell
.\venv\Scripts\python.exe .\scripts\test_server_api.py --env local
```

Result:

```text
EXIT_CODE=0
E2E flow passed.
```

The e2e script validated these expected recommendation `rule_id` values in `/api/summary/`:

- `alert.anemia`
- `alert.cardiovascular`
- `alert.cooking.indoor_solid_fuel`
- `alert.cooking.solid_fuel`
- `alert.fetal_hypoxia`
- `alert.heat.high`
- `alert.hyperemesis`
- `alert.outdoor.midday`
- `alert.pm25.daily`
- `alert.prom`

## Recommended Start For The Next Codex Session

1. Fetch the latest repository state.
2. Work from updated `master`, because PR #15 is already merged.
3. Run migrations.
4. Run the focused recommendation test suite.
5. Run `scripts/test_server_api.py --env local` when changing API, summary, advice, exposure, lifestyle, symptoms, or recommendations.
6. Create a new `codex/...` branch for the next task.

Useful commands:

```powershell
git fetch origin
git checkout master
git pull origin master
python manage.py migrate
python manage.py test recommendations.tests -v 1
```

For local e2e:

```powershell
python manage.py runserver 127.0.0.1:8000
python scripts/test_server_api.py --env local
```

## Things To Watch

- Local `db.sqlite3`, `.env`, logs, and media/debug artifacts may differ between machines and should not be treated as source of truth.
- `scripts/test_server_api.py` mutates local data during e2e checks.
- Recommendation migrations use rule IDs and `update_or_create`; preserve stable `rule_id` and version behavior when extending existing rules.
- If changing symptoms, check both public checklist behavior and local test data setup in `scripts/test_server_api.py`.
- If changing air quality or weather context, check both `recommendations/context.py` and API summary/advice tests.
- If changing recommendation text, update snippet assertions in tests and e2e script if needed.

## Suggested Additions For Future Handoffs

If the next task introduces new behavior, append a short section with:

- branch name
- PR number and URL
- main files changed
- migrations added
- tests run and exact results
- known local-only setup assumptions
- any user decisions or product constraints that are not obvious from code
