# Daily Plan: Mobile Integration

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
