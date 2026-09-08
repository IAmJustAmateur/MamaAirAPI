# Daily Plan: Mobile Integration

## Wellbeing order and graceful fallback

When possible, submit the user's current-day mood and feeling selections through
`POST /api/wellbeing/log/` before the first Daily Plan request. The answers
`distressed`, `nervous`, and `poor_sleep` can add an action whose `domain` is
`mental`.

Wellbeing is optional. If it has not been submitted, Daily Plan still returns
normally with the available tasks and recommendations. Do not treat the absence
of a mental action as an error.

The plan is immutable for its date. Wellbeing submitted after a plan has already
been created is saved, but the existing action IDs and content are not replaced.

## Load the plan

```http
GET /api/daily-plan/
Authorization: Bearer <access_token>
```

Use `?date=YYYY-MM-DD` only when a specific user-local date is needed. Render
`primary_actions`, `additional_actions`, and `support_actions` in their returned
order. The plan is stable: repeated requests for the same user and date return the
same action IDs and content.

Primary and additional actions contain:

```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "title": "Stay hydrated",
  "completion_state": "not_done"
}
```

Treat `id` as an opaque string. Do not derive task or recommendation identifiers
from it.

## Update an action

```http
PATCH /api/daily-plan/actions/{action_id}/completion/
Authorization: Bearer <access_token>
Content-Type: application/json
```

```json
{
  "completion_state": "completed"
}
```

Allowed values are:

- `completed`
- `skipped`
- `not_done`

The response contains the action ID and saved state. Repeating the same request is
safe. Use `not_done` to undo `completed` or `skipped`.

After a successful update, update the matching action in local UI state. A later
Daily Plan GET returns the persisted state.

## Errors

- `400`: invalid state, or an attempt to update a read-only support action.
- `401`: missing or expired authentication.
- `404`: action does not exist or belongs to another user.

Support actions are informational and do not contain `completion_state`. Do not
show Complete, Skip, or Undo controls for them.

Existing `/api/task-completion/` and `/api/recommendation-completion/` endpoints
remain available for legacy screens. Daily Plan screens should use only the action
UUID endpoint above.
