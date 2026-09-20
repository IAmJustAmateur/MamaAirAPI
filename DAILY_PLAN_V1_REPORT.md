# Daily Plan v1 — implementation report

## 1. Branch

Originally implemented in `codex/daily-plan-v1` and merged through PR #25.
Mental wellbeing support was added in
`codex/mental-wellbeing-recommendations` and merged through PR #26.

The branch is additive. It does not remove, rename, or replace legacy task,
recommendation, or completion models and endpoints.

## 2. Files changed

- `api/models.py` — added `DailyPlan` and `DailyAction`.
- `api/services/daily_plan.py` — stable plan creation, source composition,
  deterministic classification, user-local date handling, and completion adapter.
- `api/serializers.py` — explicit mobile response serializers.
- `api/views.py` — authenticated Daily Plan GET view.
- `api/urls.py` — Daily Plan route.
- `api/admin.py` — useful admin list, filter, and search configuration.
- `api/migrations/0049_dailyplan_dailyaction_and_more.py` — schema migration.
- `api/migrations/0050_userdailytaskcompletion_skipped.py` — adds compatible
  skipped-state storage for legacy daily tasks.
- `api/migrations/0051_mental_recommendation_dimension.py` — adds `mental` to
  recommendation and Daily Action source-dimension choices.
- `api/tests/test_daily_plan.py` — model, service, source mapping,
  classification, completion, API, legacy compatibility, and OpenAPI tests.
- `docs/openapi/schema.json` — regenerated committed API contract snapshot.
- `docs/daily_plan_mobile_guide.md` — focused integration instructions for the
  mobile client.
- `recommendations/context.py` — current-local-day wellbeing context and
  `mood(code)` / `feeling(code)` helpers.
- `recommendations/models.py` and `recommendations/evaluator.py` — mental
  recommendation content and snapshot serialization.
- `recommendations/migrations/0009_recommendationrule_recommendation_mental.py`
  — mental field migration and MVP wellbeing rule seed data.
- `recommendations/tests/test_wellbeing_recommendations.py` — mental rule and
  user-local-date coverage.
- `DAILY_PLAN_V1_REPORT.md` — this report.

## 3. Migration

Added `api/migrations/0049_dailyplan_dailyaction_and_more.py`.
Added `api/migrations/0050_userdailytaskcompletion_skipped.py` for the unified
completion contract.
Added `api/migrations/0051_mental_recommendation_dimension.py` for mental
recommendation completion metadata.
Added `recommendations/migrations/0009_recommendationrule_recommendation_mental.py`
to add `recommendation_mental` and seed the initial wellbeing rules.

It creates:

- one `DailyPlan` per `(user, local_date)`, including the timezone snapshot;
- UUID-keyed `DailyAction` rows unique by `(plan, stable_key)`;
- indexes for plan lookup, ordered role lookup, and recommendation source lookup;
- database constraints that reject mixed/incomplete task and recommendation source
  metadata;
- a database constraint that allows `service` only for `support` actions and vice
  versa.

`source_task_id` is intentionally an identifier rather than a new foreign key. This
matches the explicit-source-metadata design requested in the task, avoids coupling
the immutable plan composition to later edits/deletion-policy changes in the legacy
task catalog, and is sufficient to reconnect to `UserDailyTaskCompletion`. The
existing `DailyTask` uses `PROTECT` only through completion rows, while plan rows are
a historical snapshot. The shape of source metadata is guarded by check constraints;
referential lookup remains intentionally adapter-based.

## 4. Endpoint

Added authenticated `GET /api/daily-plan/`.

- Without a query parameter, it uses the user's current date in `User.timezone`.
- `?date=YYYY-MM-DD` returns or creates that user's plan for the requested local
  date.
- Invalid dates return HTTP 400.
- Missing or invalid user timezones fall back to `settings.TIME_ZONE` (currently
  `UTC`). The effective timezone name is persisted with the plan.
- The first creation and all action inserts run in one transaction.
- Later GETs return the same plan and actions without recomposition, even when a
  newer `HealthInsightSnapshot` exists.
- The GET endpoint performs no completion mutation. Completion changes use the
  action UUID endpoint described below.

### Completion update

`PATCH /api/daily-plan/actions/{action_id}/completion/` accepts `completed`,
`skipped`, or `not_done`. The endpoint resolves the opaque action UUID to the
existing task or recommendation completion storage, is idempotent, and rejects
actions owned by another user. Support actions remain read-only.

## 5. Source mapping

### Legacy `DailyTask`

- One active `DailyTask` becomes one `DailyAction`.
- Stable key: `task:<DailyTask.id>`.
- `diet` -> `nutrition`.
- `activity` -> `activity`.
- `behavior` -> `behavior`.
- `mental` -> `mental`.
- `title` -> action `title`.
- Because the legacy model has no description, the task title is also used as the
  action description.
- Because the legacy model has no timing, duration, or context, those response
  values are `null`.
- `DailyTask.sort_order` participates in deterministic priority ordering.
- `source_task_id` stores the legacy task identifier.

### Existing recommendation snapshot

The service calls the existing `get_or_create_fresh_snapshot` mechanism. PR #26
extended the recommendation engine and snapshot contract with the mental
dimension; the Daily Plan endpoint and its URL did not change.

Each non-empty field becomes a separate action:

- `recommendation_diet` -> source dimension `diet`, domain `nutrition`;
- `recommendation_activity` -> source dimension `activity`, domain `activity`;
- `recommendation_behavior` -> source dimension `behavior`, domain `behavior`;
- `recommendation_mental` -> source dimension `mental`, domain `mental`.

The recommendation card title becomes the action title and the dimension-specific
recommendation text becomes its description. Each action persists `snapshot_id`,
`rule_id`, `version`, and source dimension. Its stable key is
`recommendation:<snapshot_id>:<rule_id>:<version>:<dimension>`.

Recommendations with the existing reliable marker `category="medical"` become
`role="support"`, `domain="service"`. No keyword or severity heuristic is used.

### Mental wellbeing input

Mental recommendation rules use mood and feeling codes from the existing
`UserWellbeingLog` for the user's current local date. No new endpoint is required.

The MVP rules use this precedence:

1. mood `distressed`;
2. mood `nervous`, only when `distressed` is absent;
3. feeling `poor_sleep`, only when both mental moods are absent.

Submitting changed mood or feeling selections for the current local date creates
a fresh recommendation snapshot synchronously. Failure to refresh that snapshot
is logged but does not fail the wellbeing POST.

If wellbeing has not been submitted, Daily Plan creation still succeeds and
returns a valid plan without a wellbeing-derived mental action. Wellbeing submitted
after a plan has already been created does not modify that immutable plan.

### Classification

Candidates are sorted deterministically from existing task sort order and
recommendation priority, with stable source keys as tie-breakers.

- The first action in each of `nutrition`, `activity`, `behavior`, and `mental`
  becomes primary.
- Therefore there are at most four primary actions and never more than one primary
  per main domain.
- Remaining non-service actions become additional.
- Medical/service actions become support.

## 6. Completion-state mapping

### Task actions

Lookup key: same user + `source_task_id` + plan `local_date` in
`UserDailyTaskCompletion`.

- `completed=True` -> `completed`.
- `skipped=True` -> `skipped`.
- Otherwise `completed=False` -> `not_done`.
- Missing row -> `not_done`.

### Recommendation actions

Lookup key: same user + snapshot + rule ID + rule version + mapped source dimension
in `RecommendationCompletion`.

- `done` -> `completed`.
- `skipped` -> `skipped`.
- `dismissed` -> `skipped` for v1.
- Missing row -> `not_done`.

`completion_state` is omitted from support actions in the mobile response. No
legacy completion record is created or updated while reading a plan.

## 7. Existing-code ambiguities and limitations

- `DailyTask` has no description, timing, duration, or context fields. V1 uses the
  title as description and returns `null` for the other values.
- Recommendation cards provide no structured timing, duration, or context fields,
  so V1 also returns `null` for these values.
- Only `category="medical"` is a reliable existing service/escalation marker. V1
  intentionally does not infer service actions from free text or severity.
- Existing fallback recommendation cards generally use `message` rather than the
  dimension-specific `recommendation_*` fields. Per the requested mapping contract, these cards
  do not produce Daily Actions unless a supported recommendation field is present.
- `cooldown_hours` is stored on rules but is not currently enforced by the
  evaluator. `ttl_hours` calculates `expires_at`; snapshot freshness remains a
  separate setting.
- A plan explicitly requested for a past/future date is composed from the current
  fresh-snapshot mechanism because the existing engine has no historical-date
  evaluation API. Once created, that plan is still immutable through the service.
- Task and recommendation priority values are separate existing scales. V1 uses
  them deterministically, but product may want to define a single cross-source
  ranking scale later.

## 8. Tests run

- Full regression suite with the CI-like coordinate encryption key configured:
  `python manage.py test --verbosity 0`: 255/255 passed.
- Standalone mental wellbeing e2e:
  `python scripts/test_server_api.py --env local --only mental-wellbeing`: passed
  twice consecutively. Each run used a unique generated test address.
- `python manage.py makemigrations --check --dry-run`: no model drift.
- `python manage.py check`: no system-check issues.
- `git diff --check`: no whitespace errors.

An initial full-suite run without `MOVEMENT_COORDINATE_KEYS` failed only in existing
movement-ingestion tests because coordinate encryption was not configured. The
suite passes when the CI-like local test key documented in README is configured.

## 9. OpenAPI snapshot

Updated `docs/openapi/schema.json` using
`scripts/update_openapi_schema_snapshot.py`. The generator completed with validation
and `--fail-on-warn`, and the snapshot now includes the typed
`GET /api/daily-plan/` response and completion-state enum.

## 10. Mobile integration contract and follow-up decisions

- The mobile client should submit wellbeing before its first Daily Plan GET of the
  local day when mental personalization is available.
- Missing wellbeing is a supported partial-functionality state and must not block
  Daily Plan rendering.
- Support actions intentionally omit `completion_state`.
- `dismissed` is represented as `skipped` in v1.
- Historical and future dates still compose once from the current recommendation
  context because the engine has no historical evaluation API.
- Cross-source ordering may need a future product decision when task `sort_order`
  and recommendation `priority` compete within the same domain.

PR #25 and the mental wellbeing extension in PR #26 are merged into `master`.
