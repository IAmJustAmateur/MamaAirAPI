# Public account deletion (#37) and shared cleanup (#36)

`GET /delete-account` is public. Password sign-in or a provider sign-in verifies
ownership; a second CSRF-protected POST with exactly `DELETE` performs deletion.
GET, reloads and prefetch never delete accounts. The mobile endpoint remains
`DELETE /api/auth/delete-account/` with the same confirmation and empty 204 response.

## Ownership proof

- Password: the existing local password and account eligibility checks. Unknown,
  disabled, pending and incorrect-password accounts get the same failure message.
- Google: signed ID token verified using Google's certificate verifier, the
  dedicated web audience, issuer, verified email and a browser-session nonce.
  Only an already-linked `google_sub` is accepted.
- Firebase: existing server verification checks signature, project, expiry,
  revocation and verified email. Authentication must be no older than five minutes.
  Only an already-linked `firebase_uid` is accepted. The browser button uses the
  Google provider, matching the mobile Firebase/Google flow.
- Email matching never links, creates, or selects a social account for deletion.
  Local accounts without the corresponding provider identifier must use their
  existing password or supported identity; configure/link identities through the
  existing authentication flow, never through the deletion page.

The server generates a random 256-bit proof, stores its hash with the user ID,
account-state fingerprint and five-minute expiry, and keeps the proof in the
rotated browser session. No proof, password or provider token appears in a URL.
Changing password, email, provider bindings, eligibility or deleting the account
invalidates the proof. Confirmation locks the account and proof in a transaction;
concurrent/replayed confirmations cannot delete a second account, including one
registered later with the same email. Posted user IDs and emails cannot change
the target. Cancel or failed re-verification invalidates the prior proof.

Both stages require Django CSRF protection. Fixed-window cache counters limit
POSTs to 20 per IP and password attempts to 5 per normalized email in ten minutes.
Use the existing shared Redis cache in multi-worker deployment. Cache keys contain
HMAC digests, not email addresses. Caddy replaces forwarded client headers and the
web port must remain private; do not expose Django directly behind an untrusted
forwarding proxy. Provider availability messages are global configuration state,
not disclosures about a submitted account.

The page is outside `/api/` and therefore outside AuditLog payload collection.
Sensitive POST parameters and local variables are hidden in Django error reports;
provider exceptions are not interpolated into messages. Keep production DEBUG off
and do not enable HTTP body/session logging in reverse proxies or monitoring.
The broader existing logging audit remains #35.

## Required configuration before rollout

Password verification needs no SMTP or email worker. No email deletion link is
used. Password recovery remains the existing email reset flow.

For legacy Google identities, set `DELETION_GOOGLE_CLIENT_ID` to a **Web** OAuth
client ID and register the exact HTTPS site origin in its authorized JavaScript
origins. This does not change `GOOGLE_ALLOWED_AUDS` or Android authentication.

For Firebase/Google identities, configure these public Firebase web app values:

```
DELETION_FIREBASE_API_KEY=
DELETION_FIREBASE_AUTH_DOMAIN=<project>.firebaseapp.com
DELETION_FIREBASE_PROJECT_ID=
DELETION_FIREBASE_APP_ID=
```

Use the same project as the existing server Firebase Admin credentials. Enable
Google sign-in and add the page hostname to Firebase Authentication's authorized
domains. Use the default `<project>.firebaseapp.com` auth domain, allowed by this
page's CSP; a custom auth domain needs a corresponding explicit CSP change.
These are web configuration values, not service-account credentials. Never place
Admin private keys in the browser. Missing configuration disables that provider
with an explicit message; verification failures never fall back to email alone.

The browser uses Firebase SDK 12.4.0 modules and Google's hosted GIS library,
with in-memory Firebase persistence. Google/Firebase popup authentication requires
JavaScript and permitted popups. The page sets `same-origin-allow-popups` COOP and
a restricted CSP. Real provider sign-in must be smoke-tested on the configured
HTTPS origin before rollout; mocked provider tests do not verify console settings.

References: [Google GIS API](https://developers.google.com/identity/gsi/web/reference/js-reference),
[Firebase Google sign-in](https://firebase.google.com/docs/auth/web/google-signin).

## Shared deletion and ownership inventory

Both entry points call `api.account_deletion.delete_account`. The account is locked
before deleting owned rows. AuditLog cleanup from PR #33 is preserved.

| Data | Ownership and removal |
| --- | --- |
| User/MyUser profile, notification preferences, consent compatibility fields | User row and inherited parent deleted |
| UserLifeStyle | One-to-one CASCADE |
| UserMommySymptoms, UserBabySymptoms | User FK CASCADE; symptom catalog retained |
| GeneratedSymptomChecklist and items | User FK CASCADE, then item FK CASCADE |
| SymptomChecklistResponse and items | Responses explicitly removed first because checklist FK is PROTECT; items cascade |
| Movement, AirExposureLog, Exposure, DailyExposure, WeeklyExposure | User FK CASCADE, including coordinate fields |
| HealthInsightSnapshot, RecommendationCompletion | User/snapshot FK CASCADE |
| DailyPlan, DailyAction | User/plan FK CASCADE |
| UserWellbeingLog and moods/feelings membership | User CASCADE and join rows removed; Wellbeing catalog retained |
| DailyCheckin, UserDailyTaskCompletion | User FK CASCADE; shared DailyTask retained |
| OutstandingToken and blacklist rows | Explicit token deletion; blacklist children cascade |
| AuditLog | Explicit account-specific deletion, preserving PR #33 behavior |
| AccountDeletionGrant | User FK CASCADE; expired unused grants removed by cleanup worker |
| Uploaded avatar | Durable cleanup intent committed with user deletion; storage deletion after commit |
| avatar_url, upstream Firebase/Google identity | External resources are never deleted |
| Shared risk factors, rules, advice, symptom/task catalogs, guideline limits | Retained; these are shared configuration, not owned records |

The only deferred task found in the repository is `send_account_email`. It does
not create records, checks existence and an expected state including the original
user ID, and cannot target a replacement account with the same email. An SMTP
delivery already in flight can finish, but cannot recreate database records; its
old verification/reset link becomes invalid after deletion. Tests cover queued
execution after deletion/re-registration and deletion during delivery.

## Durable avatar cleanup

`AccountFileCleanup` has no FK to the removed user. It contains only the generated
storage name, original numeric owner, attempts, next retry time and error class.
It is deleted after successful storage removal. It is operational cleanup state,
not an exception allowing retention of profile/health records.

Only names matching `avatars/user_<id>/<32 hex characters>.<extension>` are
eligible. This matches current upload generation. Another user's directory,
external URL, shared/ambiguous legacy name or traversal path is never deleted.
At each retry, any live user reference to the same file prevents deletion. Do not
reuse generated upload names or assign arbitrary storage paths outside the upload
flow. Ambiguous historical files require a separate ownership investigation;
this change does not scan or purge existing storage.

The first attempt runs after commit. A lost callback, process crash or storage
failure leaves the committed intent for a later retry. No broker enqueue is needed.
Storage errors record only their class and use bounded backoff. Missing files and
repeated successful retries are safe. Database rollback preserves the file and
does not create cleanup intent.

`deployment/docker-compose.yml` adds `account_cleanup`, a dedicated process that
runs `python manage.py retry_account_file_cleanup --loop` once a minute, up to 100
due intents per iteration. It uses the web service's media volume and database,
and starts after the migrated web service is healthy. It does not use the email
queue or require changing Celery routing. The command also supports a single pass.

Before rollout: apply migrations 0055 and 0056, configure provider origins, then
start web and the cleanup service with the same storage configuration. Confirm
that worker logs continue to show `Account cleanup checked=... pending=...`;
investigate a stopped process, increasing pending count, overdue `next_attempt_at`,
or repeated `error_type` values. Verify a synthetic account/avatar in an isolated
environment, including temporary storage failure and recovery. Stop the cleanup
service to pause retries; committed intents remain for resumption. Do not reverse
the cleanup migration while pending intents exist.

No deployment or cleanup of existing server data is performed by this work.
Production worker execution and provider configuration remain unverified until
operators perform the rollout checks.

## Validation

Run the Django suite on PostgreSQL to exercise row locking and concurrent web
confirmation. Focused tests: `test_deletion_pages`, `test_account_deletion`,
`test_account_cleanup`. The ownership graph test populates both users' records
and asserts shared catalogs and the second user's graph remain.

`python scripts/test_deletion_browser.py` starts a temporary SQLite server and
uses real Chromium for password verification, reload, exact confirmation and
success at mobile width. Install `requirements-browser-e2e.txt` and Chromium
first. Screenshots go to `.e2e-artifacts/deletion/`. It never contacts deployment.
