# Account deletion: mobile integration

Use this endpoint only after showing the user a clear irreversible-deletion warning.

## Request

```bash
curl -i -X DELETE "$BASE_URL/api/auth/delete-account/" \
  -H "Authorization: Bearer $ACCESS" \
  -H "Content-Type: application/json" \
  -d '{"confirmation":"DELETE"}'
```

The `confirmation` value is case-sensitive and must be exactly `DELETE`.

## Responses

- `204 No Content`: deletion completed; the response body is empty.
- `400 Bad Request`: confirmation is missing or incorrect.
- `401 Unauthorized`: the access token is missing, invalid, or belongs to a deleted account.

After `204`, clear the access token, refresh token, cached profile, and other local
user data, then return to the signed-out screen. The server permanently deletes the
account, its related data, and its uploaded avatar. Existing access and refresh
tokens stop working. The same email address can be registered again as a new account.

The operation is not recoverable. Do not retry automatically after a network
timeout: first treat the user as signed out and let them sign in or register again.
