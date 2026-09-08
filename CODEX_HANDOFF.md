# Codex Handoff: MamaAir API

## Repository

- Project: MamaAir API / `aq_agent_api`
- GitHub: `https://github.com/IAmJustAmateur/aq_agent_api.git`
- Current main branch: `master`
- Latest completed feature branch: `codex/mental-wellbeing-recommendations`
- Latest completed PR: `#26 feat: add mental wellbeing recommendations to daily plan`
- PR URL: `https://github.com/IAmJustAmateur/aq_agent_api/pull/26`
- Merge commit: `1dea995`
- Feature commits: `f46125d`, `b6c7320`

Start new work from the current remote `master` unless the user explicitly asks
to inspect an older branch.

## Project Overview

This is a Django REST Framework backend for the MamaAir mobile app. It stores user
profile, pregnancy, lifestyle, wellbeing, symptom, movement, air-quality, weather,
exposure, recommendation, and Daily Plan data.

Important areas:

- `api/`: mobile API models, serializers, views, authentication, exposure,
  wellbeing, dashboard, and Daily Plan logic.
- `recommendations/`: recommendation rules, evaluator, context builder, fallbacks,
  migrations, and tests.
- `api/services/daily_plan.py`: immutable Daily Plan composition and completion
  adapters.
- `scripts/test_server_api.py`: current-contract local/server e2e API test.
- `docs/mobile_api_guide.md`: general mobile API integration guide.
- `docs/daily_plan_mobile_guide.md`: focused Daily Plan integration guide.
- `DAILY_PLAN_V1_REPORT.md`: implementation decisions and known limitations.

## Current Development Stage

Daily Plan v1 was merged in PR #25. Mental wellbeing recommendations were then
added and merged in PR #26. Existing endpoints remain compatible; no separate
mental or wellbeing endpoint was introduced.

Current flow:

1. The mobile client submits the current day's wellbeing selections through
   `POST /api/wellbeing/log/`.
2. A change to mood or feeling selections for the user's current local date
   generates a fresh recommendation snapshot synchronously.
3. `GET /api/daily-plan/` creates the user's immutable plan for that local date.
4. Matching wellbeing rules can add one `mental` action to the plan.
5. If wellbeing is absent, Daily Plan still returns HTTP 200 with a valid plan and
   simply has no wellbeing-derived mental action.

The implemented MVP mental signals are:

- mood `distressed`;
- mood `nervous` when `distressed` is absent;
- feeling `poor_sleep` when neither mental mood above is selected.

This gives the precedence `distressed` -> `nervous` -> `poor_sleep` and prevents
multiple wellbeing-derived mental actions from these rules.

Daily Plans are snapshots. Submitting wellbeing after a plan has already been
created does not modify that plan. The new recommendation can affect a plan created
for a later local date.

## Latest Completed Work

PR #26 added:

- `recommendation_mental` to recommendation rules, snapshots, API schema, and
  Daily Plan source mapping;
- `mental` as a recommendation completion dimension;
- current-local-day wellbeing data and `mood(code)` / `feeling(code)` helpers in
  the recommendation context;
- migrations `recommendations/0009_recommendationrule_recommendation_mental.py`
  and `api/0051_mental_recommendation_dimension.py`;
- safe degradation when wellbeing is missing or snapshot refresh fails;
- API, integration, schema, evaluator, and e2e coverage;
- updated README, mobile guides, and committed OpenAPI schema.

The standalone mental e2e scenario automatically derives a unique address from
the supplied email on each run. This prevents an immutable plan from an earlier
run from leaking into the next run.

## Recommendation Engine Notes

- Active rules are evaluated in explicit `priority` order; lower values are more
  important.
- `severity` is client-facing urgency metadata and does not determine ordering.
- `ttl_hours` is used to calculate `expires_at`. Snapshot freshness is controlled
  separately by `HEALTH_INSIGHT_SNAPSHOT_FRESH_HOURS`.
- `cooldown_hours` is stored as policy metadata but is not currently enforced by
  the evaluator.
- Evaluation errors are treated as a rule non-match.
- Medical recommendation actions are exposed by Daily Plan as read-only
  service/support actions.

Earlier Level 3 medical, air-quality, heat, cooking, and outdoor-activity rules
were merged in PR #15 and remain part of the engine.

## Local Development

Typical setup:

```powershell
python -m venv venv
.\venv\Scripts\activate
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

The project uses a `.env` next to `manage.py`; use `env.dist` as the starting
point. Swagger endpoints:

- Local UI: `http://127.0.0.1:8000/api/docs/`
- Local schema: `http://127.0.0.1:8000/api/schema/`
- Production UI: `https://api.mamaair.work/api/docs/`

Movement tests and the full local e2e require a configured coordinate encryption
key. For local-only testing in PowerShell:

```powershell
$env:MOVEMENT_COORDINATE_KEYS='{"1":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="}'
.\venv\Scripts\python.exe manage.py test -v 1
```

For the full e2e, configure the same variable in the terminal that starts Django,
then restart the server. The all-zero key is for local tests only.

Run the focused mental scenario:

```powershell
.\venv\Scripts\python.exe scripts\test_server_api.py --env local --only mental-wellbeing
```

Run the complete current-contract scenario:

```powershell
.\venv\Scripts\python.exe scripts\test_server_api.py --env local
```

The server's `REGISTRATION_API_KEY` must match the script's `--reg-api-key` value.

## Verification For PR #26

The following checks passed during feature development before merge:

- full Django regression suite: 255/255;
- standalone mental wellbeing e2e: passed twice consecutively with the same base
  email, using a fresh generated address each time;
- `python manage.py makemigrations --check --dry-run`: no model drift;
- OpenAPI schema regeneration: no warnings;
- `git diff --check`: no whitespace errors.

## Recommended Start For The Next Session

```powershell
git fetch origin
git checkout master
git pull origin master
.\venv\Scripts\python.exe manage.py migrate
.\venv\Scripts\python.exe manage.py check
```

Create a new `codex/...` branch for implementation work. CI runs on pushes to any
branch and on pull requests targeting `master`.

## Things To Watch

- Local `db.sqlite3`, `.env`, logs, and generated media are not source of truth.
- E2E scripts create and mutate test users and related data.
- Run migrations before testing recommendation or Daily Plan behavior; migration
  `0009` seeds the mental rules.
- Preserve stable recommendation `rule_id` and version semantics when changing
  rules referenced by snapshots or completion records.
- Submit wellbeing before the first Daily Plan GET when testing mental actions.
- A plan already created for a local date is intentionally not recomposed.
- If recommendation response fields change, update serializers, the committed
  OpenAPI snapshot, mobile guides, and e2e schema assertions together.
