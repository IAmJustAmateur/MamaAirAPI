# Request audit log

`/admin/api/auditlog/` provides a read-only diagnostic log. Staff need the
`api.view_auditlog` permission; superusers already have access.

Recorded requests:

- API responses with HTTP status 400 or higher, including anonymous requests.
- Successful POST/PUT/PATCH to mommy/baby symptom selection endpoints.
- Movement uploads with non-empty `errors` or `exposure_errors`, even with 201/207.

Other successful requests, including successful movements, are skipped.
Every API response receives a server-generated `X-Request-ID` for correlation.
The path is the resolved route template (unknown routes use `/api/[unresolved]`),
so arbitrary path segments cannot introduce secrets into the log.

JSON request/response bodies and repeated query parameters are captured. Passwords,
tokens, cookies and location fields are recursively redacted, including known
sensitive values echoed elsewhere. Only Content-Type, Accept and Accept-Language
request headers are retained; User-Agent is sanitized and limited to 1024 characters.
IP uses REMOTE_ADDR, not an untrusted forwarded header.

Bodies are limited to 64 KiB each by default. Uploads, non-JSON bodies, malformed
JSON and oversized bodies are omitted with an explanation in metadata. Streaming
responses are never consumed. If a request body could not be inspected, response
text values are omitted too, since parser errors can echo sensitive input.
Symptom values are retained. Do not add secrets or coordinates to arbitrary
free-text fields: redaction targets structured sensitive fields and common text
patterns, not every possible encoding of sensitive information.

Known response diagnostics (`code`, `token_type`, `token_class`) are retained
only for explicitly allowed values such as `token_not_valid`, `access` and
`AccessToken`. Request codes, actual tokens and arbitrary values under these
field names remain redacted.

For anonymous 401 responses, an expired Bearer access token can identify the
token's owner in the User column. Its signature, algorithm, configured issuer
and audience, and other temporal claims are verified; only expiration is
relaxed for this diagnostic lookup. The request still receives 401. Metadata
marks `user_source=expired_access_token`, `authentication_succeeded=false`, the
expiry time and elapsed seconds. This identifies the owner of the credential,
not necessarily the person presenting it. Invalid signatures, refresh tokens,
missing users or failed lookups leave User empty. Lookup uses the configured
JWT user claim (currently email); a changed email cannot recover the old owner.

Unhandled exceptions include their type and stack frame locations, without the
exception message, source lines or local variables. Handled errors retain their
sanitized JSON response. Audit persistence failures do not change the API response.
This is best-effort diagnostics, not a guaranteed compliance event ledger.

Configuration:

| Environment variable | Default | Meaning |
| --- | --- | --- |
| AUDIT_LOG_ENABLED | true | Enable capture |
| AUDIT_LOG_MAX_BODY_BYTES | 65536 | Per-body storage/capture limit |
| AUDIT_LOG_RETENTION_DAYS | 14 | Retention window for cleanup |

Apply the migration with `python manage.py migrate`.
Run `python manage.py purge_audit_logs` daily through the deployment scheduler.
The command removes expired entries in batches of 1000. Setting the retention
window alone does not schedule cleanup.

Tests: `python manage.py test api.tests.test_audit_log api.tests.test_audit_log_e2e`.
The E2E test uses a real local HTTP server, JWT, the database, admin login with
CSRF and admin read/write permissions. It does not require external services.

For the additional Chromium login/search/detail check, install the existing
`requirements-browser-e2e.txt` dependencies and Chromium (`python -m playwright
install chromium`), then run the E2E test with `AUDIT_BROWSER_E2E=1`.
