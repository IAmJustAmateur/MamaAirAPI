# Firebase authentication

## Configuration and deployment

The mobile app and backend must use the same Firebase project. The backend reads
`project_id` from the service-account JSON referenced by `FIREBASE_CREDENTIALS`.
There is no separate project-ID environment variable. In production Compose the
file is mounted from `/home/ec2-user/secrets/firebase_service_account.json` to
`/run/secrets/firebase_service_account.json`. Never include the private key in the
mobile app or repository. The service account needs permission to read Firebase
Authentication users (`firebaseauth.users.get`) for revocation checks.

Apply migration `0054_user_firebase_uid` before starting the updated application.
The nullable unique UID is populated on the next successful Firebase sign-in;
existing accounts cannot be backfilled from provider labels alone. Keep the
Firebase project stable after linking accounts; changing projects requires an
explicit identity migration.

## Mobile contract

1. Sign in using the mobile Firebase SDK and obtain a Firebase ID token.
2. POST `/api/auth/firebase/` with JSON `{"id_token": "<Firebase ID token>"}`.
3. Store the returned `access` and `refresh`. Use the API access token in
   `Authorization: Bearer <access>` for protected API requests.
4. POST `/api/auth/token/refresh/` with `{"refresh": "<API refresh token>"}` to
   obtain a new access token. This endpoint does not accept Firebase tokens.

The response includes `user.id`, `user.email`, `user.name`, `user.avatar_url`, and
`user.provider` (`firebase`). New profiles receive the Firebase name and valid
avatar URL; existing nonempty profile values and passwords are preserved.
`user.name` is always present and is an empty string when no name is available.

The endpoint verifies signature, project, expiry, revocation, disabled status,
and confirmed email. It looks up the persistent Firebase UID first. On first
link only, a unique case-insensitive email match can link an active, locally
verified account. Conflicting UIDs, ambiguous emails, disabled accounts, and
accounts awaiting local email verification are rejected.

A later Firebase email change does not change the local account email or create
a new account. The local email is still the identifier used by password login
and existing JWTs; changing it needs a separate account-email workflow.

Responses: 400 invalid input, 401 invalid/unavailable identity or session,
409 concurrent account conflict (retry sign-in), 429 sign-in rate limit, and
503 Firebase service/configuration unavailable (retry later, retain credentials).

## Session revocation

New Firebase-issued API access and refresh tokens carry the UID, project ID,
and original Firebase `auth_time`. Each protected request and refresh looks up
the Firebase user and rejects disabled/deleted users or sessions whose original
authentication time precedes `tokens_valid_after_timestamp`. Refresh preserves
that original time; it does not bypass revocation. No successful lookup is cached.

This adds a Firebase network lookup to each authenticated Firebase request.
Firebase outages fail closed with 503. Existing local disabled/pending/password
checks still apply. Independent password and direct Google sessions retain their
existing behavior; a Firebase block is not a global local-account block.

Legacy API tokens issued before this change have no Firebase session marker and
cannot be distinguished from other login methods. They retain their previous
behavior until expiry (access: 48 hours; refresh: 30 days) or local revocation.
For an immediate complete cutover, plan a forced logout of existing sessions;
this deployment does not silently rotate signing keys or reset passwords.

## Release verification

Automated tests mock Firebase and cover linking, UID conflicts, changed email,
profile protection, failed verification, service outages, and revocation of both
access and refresh tokens. They do not prove production credentials or mobile
provider configuration are correct.

With the mobile developer, use a dedicated test user in the intended project:
sign in, fetch `/api/profile/`, refresh, repeat login, then disable the Firebase
user or revoke their sessions and verify both API tokens return 401. Re-enable
and sign in afresh to verify recovery. Confirm Firebase project IDs match before
running this test. Do not disable real users as a smoke test.
