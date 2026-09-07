# Daily Plan v1 — implementation report

## 1. Branch

`codex/daily-plan-v1` (created from `master`).

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
- `api/tests/test_daily_plan.py` — model, service, source mapping,
  classification, completion, API, legacy compatibility, and OpenAPI tests.
- `docs/openapi/schema.json` — regenerated committed API contract snapshot.
- `docs/daily_plan_mobile_guide.md` — focused integration instructions for the
  mobile client.
- `DAILY_PLAN_V1_REPORT.md` — this report.

## 3. Migration

Added `api/migrations/0049_dailyplan_dailyaction_and_more.py`.
Added `api/migrations/0050_userdailytaskcompletion_skipped.py` for the unified
completion contract.

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

The service calls the existing `get_or_create_fresh_snapshot` mechanism and does
not alter the recommendation engine.

Each non-empty field becomes a separate action:

- `recommendation_diet` -> source dimension `diet`, domain `nutrition`;
- `recommendation_activity` -> source dimension `activity`, domain `activity`;
- `recommendation_behavior` -> source dimension `behavior`, domain `behavior`.

The recommendation card title becomes the action title and the dimension-specific
recommendation text becomes its description. Each action persists `snapshot_id`,
`rule_id`, `version`, and source dimension. Its stable key is
`recommendation:<snapshot_id>:<rule_id>:<version>:<dimension>`.

Recommendations with the existing reliable marker `category="medical"` become
`role="support"`, `domain="service"`. No keyword or severity heuristic is used.

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
- `completed=False` -> `not_done`.
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
  three `recommendation_*` fields. Per the requested mapping contract, these cards
  do not produce Daily Actions unless a supported recommendation field is present.
- A plan explicitly requested for a past/future date is composed from the current
  fresh-snapshot mechanism because the existing engine has no historical-date
  evaluation API. Once created, that plan is still immutable through the service.
- Task and recommendation priority values are separate existing scales. V1 uses
  them deterministically, but product may want to define a single cross-source
  ranking scale later.

## 8. Tests run

- `python manage.py test api.tests.test_daily_plan --verbosity 0`:
  14/14 passed.
- Full regression suite with the CI-like coordinate encryption key configured:
  `python manage.py test api.tests recommendations.tests --verbosity 0`:
  232/232 passed, including 14 Daily Plan tests.
- `python manage.py makemigrations --check --dry-run`: no model drift.
- `python manage.py check`: no system-check issues.
- `git diff --check`: no whitespace errors.

An initial full-suite run without `MOVEMENT_COORDINATE_KEYS` failed only in existing
movement-ingestion tests because coordinate encryption was not configured. Repeating
the same suite with the repository's CI-like test key passed all 232 tests.

## 9. OpenAPI snapshot

Updated `docs/openapi/schema.json` using
`scripts/update_openapi_schema_snapshot.py`. The generator completed with validation
and `--fail-on-warn`, and the snapshot now includes the typed
`GET /api/daily-plan/` response and completion-state enum.

## 10. Confirm with the mobile developer before merge

- Confirm that using the task title as its description is acceptable until the
  legacy task catalog gains distinct descriptions.
- Confirm that support actions intentionally omit `completion_state`.
- Confirm that `dismissed` should appear as `skipped` in v1.
- Confirm that fallback cards containing only `message` should remain absent from
  Daily Plan rather than being mapped speculatively.
- Confirm expected behavior for explicitly requested historical/future dates, which
  currently compose once from today's fresh recommendation snapshot.
- Confirm the desired cross-source ordering when task `sort_order` and recommendation
  `priority` compete for the primary slot in the same domain.

No merge to `master` was performed and no pull request was opened.
