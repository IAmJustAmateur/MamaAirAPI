# MamaAir email authentication: curl walkthrough

This is the expected mobile flow for a new email/password account. Run the
commands below in Bash with `curl`.

Use a new test email that has never been registered in MamaAir and whose inbox
you can open. Do not use a production user's account: password reset revokes that
user's existing access and refresh tokens.

```bash
BASE_URL=https://api.mamaair.work
TEST_EMAIL=replace-with-a-real-inbox@example.com
INITIAL_PASSWORD=Birch!Quartz85-frost
NEW_PASSWORD=Ocean!Quartz62-spring
```

Set these variables once in the current Bash session. Keep the passwords only in
your local test environment; do not commit them. The example passwords do not
contain JSON-sensitive quote or backslash characters.

## Flow summary

Follow the steps in this order:

1. Register the account.
2. **Do not confirm the email yet.** Optionally try to log in and verify that it
   returns `401` while the account is pending.
3. If the first verification email did not arrive, optionally request another one.
4. Open the verification link in the browser, or confirm with the curl request.
5. Log in with the verified account.
6. Request password reset and complete the reset.
7. Verify the new password and JWT revocation.

Steps 2 and 3 are diagnostic checks. In the normal mobile flow, the user can go
directly from registration to opening the verification link, then log in.

## 1. Register a new account

`password_confirm` is required and must equal `password`.

```bash
curl --include --request POST "$BASE_URL/api/auth/email/register/" \
  --header "Content-Type: application/json" \
  --data-raw "{\"email\":\"$TEST_EMAIL\",\"password\":\"$INITIAL_PASSWORD\",\"password_confirm\":\"$INITIAL_PASSWORD\"}"
```

Expected: `202 Accepted`.

```json
{"detail":"If the account is eligible, an email will be sent. Please check your inbox."}
```

This creates a pending account and queues a verification email. A registration
request without `password_confirm` returns `400 Bad Request`, creates no account,
and queues no email.

For the complete test below, wait before opening the verification link: first run
the optional pending-login check in step 2. If you only need the normal user flow,
you can skip steps 2 and 3 and open the link immediately.

## 2. Optional: confirm that login is blocked before verification

At this point the email must still be unconfirmed. Do not open its verification
link until this negative check is complete.

```bash
curl --include --request POST "$BASE_URL/api/auth/email/login/" \
  --header "Content-Type: application/json" \
  --data-raw "{\"email\":\"$TEST_EMAIL\",\"password\":\"$INITIAL_PASSWORD\"}"
```

Expected: `401 Unauthorized`. A pending user must not receive JWT tokens.

## 3. Optional: resend verification when necessary

Use this only for an existing pending account:

```bash
curl --include --request POST "$BASE_URL/api/auth/email/resend/" \
  --header "Content-Type: application/json" \
  --data-raw "{\"email\":\"$TEST_EMAIL\"}"
```

Expected: `202 Accepted`. Wait for the newest email. Older verification links may
still be valid, but using the newest message avoids confusion.

`202` deliberately does not prove that an account exists or that an email was
delivered. No verification email is sent for an unknown, disabled, or already
verified account.

## 4. Verify the email address (required before login and password reset)

The email contains a URL similar to:

```text
https://api.mamaair.work/verify-email?uid=ENCODED_UID&token=TOKEN
```

The normal user flow is to open this URL in a browser and save the password on
the page. For a curl-only test, copy `uid` and `token` from the URL:

```bash
VERIFY_UID=ENCODED_UID_FROM_EMAIL
VERIFY_TOKEN=TOKEN_FROM_EMAIL

curl --include --request POST "$BASE_URL/api/auth/email/verify/" \
  --header "Content-Type: application/json" \
  --data-raw "{\"uid\":\"$VERIFY_UID\",\"token\":\"$VERIFY_TOKEN\",\"new_password\":\"$INITIAL_PASSWORD\",\"password_confirm\":\"$INITIAL_PASSWORD\"}"
```

Expected: `200 OK`.

```json
{"detail":"Password saved. You can now sign in."}
```

The email owner chooses the final password during verification. It may be the
same password entered during registration. The link cannot be reused after a
successful verification.

## 5. Log in after verification

```bash
curl --include --request POST "$BASE_URL/api/auth/email/login/" \
  --header "Content-Type: application/json" \
  --data-raw "{\"email\":\"$TEST_EMAIL\",\"password\":\"$INITIAL_PASSWORD\"}"
```

Expected: `200 OK` with `access`, `refresh`, and `user`. Copy the returned token
values into Bash variables for the revocation checks below:

```bash
OLD_ACCESS='paste-access-token-here'
OLD_REFRESH='paste-refresh-token-here'
```

Verify the access token:

```bash
curl --include "$BASE_URL/api/profile/" \
  --header "Authorization: Bearer $OLD_ACCESS"
```

Expected: `200 OK`.

## 6. Request a password-reset email

Password reset is available only after the account is verified.

```bash
curl --include --request POST "$BASE_URL/api/auth/password-reset/request/" \
  --header "Content-Type: application/json" \
  --data-raw "{\"email\":\"$TEST_EMAIL\"}"
```

Expected: `202 Accepted`. A pending account does not receive a reset email; use
the verification resend endpoint from step 3 instead.

## 7. Set the new password

The reset email contains a URL similar to:

```text
https://api.mamaair.work/reset-password?uid=ENCODED_UID&token=TOKEN
```

The normal user flow is the browser page. For a curl-only test, copy its values:

```bash
RESET_UID=ENCODED_UID_FROM_RESET_EMAIL
RESET_TOKEN=TOKEN_FROM_RESET_EMAIL

curl --include --request POST "$BASE_URL/api/auth/password-reset/confirm/" \
  --header "Content-Type: application/json" \
  --data-raw "{\"uid\":\"$RESET_UID\",\"token\":\"$RESET_TOKEN\",\"new_password\":\"$NEW_PASSWORD\",\"password_confirm\":\"$NEW_PASSWORD\"}"
```

Expected: `200 OK` with `Password saved`. Repeating this exact request must return
`400 Bad Request` because a successful reset invalidates the link.

## 8. Verify password and JWT revocation

The old password must fail:

```bash
curl --include --request POST "$BASE_URL/api/auth/email/login/" \
  --header "Content-Type: application/json" \
  --data-raw "{\"email\":\"$TEST_EMAIL\",\"password\":\"$INITIAL_PASSWORD\"}"
```

Expected: `401 Unauthorized`.

The new password must work:

```bash
curl --include --request POST "$BASE_URL/api/auth/email/login/" \
  --header "Content-Type: application/json" \
  --data-raw "{\"email\":\"$TEST_EMAIL\",\"password\":\"$NEW_PASSWORD\"}"
```

Expected: `200 OK`. Copy these token values:

```bash
NEW_ACCESS='paste-new-access-token-here'
NEW_REFRESH='paste-new-refresh-token-here'
```

Old tokens must be rejected:

```bash
curl --include "$BASE_URL/api/profile/" \
  --header "Authorization: Bearer $OLD_ACCESS"

curl --include --request POST "$BASE_URL/api/auth/token/refresh/" \
  --header "Content-Type: application/json" \
  --data-raw "{\"refresh\":\"$OLD_REFRESH\"}"
```

Expected: `401 Unauthorized` for both.

New tokens must work:

```bash
curl --include "$BASE_URL/api/profile/" \
  --header "Authorization: Bearer $NEW_ACCESS"

curl --include --request POST "$BASE_URL/api/auth/token/refresh/" \
  --header "Content-Type: application/json" \
  --data-raw "{\"refresh\":\"$NEW_REFRESH\"}"
```

Expected: `200 OK` for both.

## Endpoint state rules

| Account state | Registration | Verification resend | Password reset request |
| --- | --- | --- | --- |
| Unknown email | Creates pending account only with a valid registration payload | Returns 202, sends nothing | Returns 202, sends nothing |
| Pending email | Returns 202 without replacing the existing password | Returns 202 and queues verification | Returns 202, sends nothing |
| Verified active email | Returns 202 without changing the account | Returns 202, sends nothing | Returns 202 and queues reset |
| Disabled email | Returns a generic response | Returns 202, sends nothing | Returns 202, sends nothing |

Generic `202` responses prevent account enumeration. They mean that the request
was accepted for processing, not that Gmail accepted or delivered a message.

## Troubleshooting delivery

If an eligible account receives no email, check the Celery worker on the server:

```bash
docker compose --env-file .env -f deployment/docker-compose.yml logs --since=10m --tail=100 celery_worker web
```

Also check spam. A fast `Task ... succeeded ... None` can mean that the task safely
skipped an unknown or ineligible account before contacting SMTP.
