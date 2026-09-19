# MamaAir email authentication: curl walkthrough

This is the expected mobile flow for a new email/password account. The commands
below work in PowerShell 7 with `curl.exe` and in a POSIX shell with `curl`.
On Windows, use `curl.exe` explicitly so PowerShell does not select another command.

Use a new test email that has never been registered in MamaAir and whose inbox
you can open. Do not use a production user's account: password reset revokes that
user's existing access and refresh tokens.

```text
BASE_URL=https://api.mamaair.work
TEST_EMAIL=replace-with-a-real-inbox@example.com
INITIAL_PASSWORD=Birch!Quartz85-frost
NEW_PASSWORD=Ocean!Quartz62-spring
```

Replace the values directly in each command. Keep the password only in your local
test environment; do not commit it.

## 1. Register a new account

`password_confirm` is required and must equal `password`.

```powershell
curl.exe --include --request POST "https://api.mamaair.work/api/auth/email/register/" --header "Content-Type: application/json" --data-raw '{"email":"replace-with-a-real-inbox@example.com","password":"Birch!Quartz85-frost","password_confirm":"Birch!Quartz85-frost"}'
```

Expected: `202 Accepted`.

```json
{"detail":"If the account is eligible, an email will be sent. Please check your inbox."}
```

This creates a pending account and queues a verification email. A registration
request without `password_confirm` returns `400 Bad Request`, creates no account,
and queues no email.

## 2. Confirm that login is blocked before verification

```powershell
curl.exe --include --request POST "https://api.mamaair.work/api/auth/email/login/" --header "Content-Type: application/json" --data-raw '{"email":"replace-with-a-real-inbox@example.com","password":"Birch!Quartz85-frost"}'
```

Expected: `401 Unauthorized`. A pending user must not receive JWT tokens.

## 3. Resend verification when necessary

Use this only for an existing pending account:

```powershell
curl.exe --include --request POST "https://api.mamaair.work/api/auth/email/resend/" --header "Content-Type: application/json" --data-raw '{"email":"replace-with-a-real-inbox@example.com"}'
```

Expected: `202 Accepted`. Wait for the newest email. Older verification links may
still be valid, but using the newest message avoids confusion.

`202` deliberately does not prove that an account exists or that an email was
delivered. No verification email is sent for an unknown, disabled, or already
verified account.

## 4. Verify the email address

The email contains a URL similar to:

```text
https://api.mamaair.work/verify-email?uid=ENCODED_UID&token=TOKEN
```

The normal user flow is to open this URL in a browser and save the password on
the page. For a curl-only test, copy `uid` and `token` from the URL and call:

```powershell
curl.exe --include --request POST "https://api.mamaair.work/api/auth/email/verify/" --header "Content-Type: application/json" --data-raw '{"uid":"ENCODED_UID_FROM_EMAIL","token":"TOKEN_FROM_EMAIL","new_password":"Birch!Quartz85-frost","password_confirm":"Birch!Quartz85-frost"}'
```

Expected: `200 OK`.

```json
{"detail":"Password saved. You can now sign in."}
```

The email owner chooses the final password during verification. It may be the
same password entered during registration. The link cannot be reused after a
successful verification.

## 5. Log in after verification

```powershell
curl.exe --include --request POST "https://api.mamaair.work/api/auth/email/login/" --header "Content-Type: application/json" --data-raw '{"email":"replace-with-a-real-inbox@example.com","password":"Birch!Quartz85-frost"}'
```

Expected: `200 OK` with `access`, `refresh`, and `user`. Save the returned tokens
as `OLD_ACCESS` and `OLD_REFRESH` for the revocation checks below.

Verify the access token:

```powershell
curl.exe --include "https://api.mamaair.work/api/profile/" --header "Authorization: Bearer OLD_ACCESS"
```

Expected: `200 OK`.

## 6. Request a password-reset email

Password reset is available only after the account is verified.

```powershell
curl.exe --include --request POST "https://api.mamaair.work/api/auth/password-reset/request/" --header "Content-Type: application/json" --data-raw '{"email":"replace-with-a-real-inbox@example.com"}'
```

Expected: `202 Accepted`. A pending account does not receive a reset email; use
the verification resend endpoint from step 3 instead.

## 7. Set the new password

The reset email contains a URL similar to:

```text
https://api.mamaair.work/reset-password?uid=ENCODED_UID&token=TOKEN
```

The normal user flow is the browser page. For a curl-only test, copy its values:

```powershell
curl.exe --include --request POST "https://api.mamaair.work/api/auth/password-reset/confirm/" --header "Content-Type: application/json" --data-raw '{"uid":"ENCODED_UID_FROM_RESET_EMAIL","token":"TOKEN_FROM_RESET_EMAIL","new_password":"Ocean!Quartz62-spring","password_confirm":"Ocean!Quartz62-spring"}'
```

Expected: `200 OK` with `Password saved`. Repeating this exact request must return
`400 Bad Request` because a successful reset invalidates the link.

## 8. Verify password and JWT revocation

The old password must fail:

```powershell
curl.exe --include --request POST "https://api.mamaair.work/api/auth/email/login/" --header "Content-Type: application/json" --data-raw '{"email":"replace-with-a-real-inbox@example.com","password":"Birch!Quartz85-frost"}'
```

Expected: `401 Unauthorized`.

The new password must work:

```powershell
curl.exe --include --request POST "https://api.mamaair.work/api/auth/email/login/" --header "Content-Type: application/json" --data-raw '{"email":"replace-with-a-real-inbox@example.com","password":"Ocean!Quartz62-spring"}'
```

Expected: `200 OK`. Save these tokens as `NEW_ACCESS` and `NEW_REFRESH`.

Old tokens must be rejected:

```powershell
curl.exe --include "https://api.mamaair.work/api/profile/" --header "Authorization: Bearer OLD_ACCESS"
curl.exe --include --request POST "https://api.mamaair.work/api/auth/token/refresh/" --header "Content-Type: application/json" --data-raw '{"refresh":"OLD_REFRESH"}'
```

Expected: `401 Unauthorized` for both.

New tokens must work:

```powershell
curl.exe --include "https://api.mamaair.work/api/profile/" --header "Authorization: Bearer NEW_ACCESS"
curl.exe --include --request POST "https://api.mamaair.work/api/auth/token/refresh/" --header "Content-Type: application/json" --data-raw '{"refresh":"NEW_REFRESH"}'
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
