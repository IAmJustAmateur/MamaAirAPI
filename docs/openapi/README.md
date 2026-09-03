# OpenAPI Schema Snapshot

`schema.json` is the committed OpenAPI contract snapshot for the public MamaAir mobile API.

Use it when the mobile app needs a stable backend contract for endpoints, response codes, field types, nullable fields, enums, and authentication requirements.

## Update The Snapshot

Regenerate the snapshot after an intentional API contract change:

```bash
python scripts/update_openapi_schema_snapshot.py
```

Review the diff before committing it. A changed snapshot means the mobile API contract changed.

Use this script instead of calling `manage.py spectacular` directly. It pins
CI-like schema generation settings so the snapshot stays stable across local
SQLite development and PostgreSQL-backed CI/staging.

## CI Drift Check

GitHub Actions regenerates `docs/openapi/schema.json` and fails if it differs from the committed file.

If CI fails on the OpenAPI snapshot step:

1. Decide whether the API contract change was intentional.
2. If intentional, regenerate and commit `docs/openapi/schema.json`.
3. If accidental, fix the serializer, view schema annotation, route, or settings change that caused the drift.

The snapshot intentionally excludes legacy auth, debug, and demo endpoints from the public mobile contract.
