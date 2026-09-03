"""Regenerate the committed OpenAPI schema snapshot.

The snapshot is generated with CI-like settings so integer field formats stay
stable across local SQLite development and PostgreSQL-backed CI/staging.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
SNAPSHOT_PATH = PROJECT_ROOT / "docs" / "openapi" / "schema.json"


def configure_environment() -> None:
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "agent_api.settings")
    os.environ["DJANGO_ENV"] = "staging"
    os.environ["DEBUG"] = "False"
    os.environ.setdefault("SECRET_KEY", "schema-snapshot-only-not-production")
    os.environ.setdefault("ALLOWED_HOSTS", "127.0.0.1,localhost")
    os.environ.setdefault("REGISTRATION_API_KEY", "schema-snapshot-key")
    os.environ.setdefault("DB_NAME", "mamaair_schema_snapshot")
    os.environ.setdefault("DB_USER", "postgres")
    os.environ.setdefault("DB_PASSWORD", "postgres")
    os.environ.setdefault("DB_HOST", "127.0.0.1")
    os.environ.setdefault("DB_PORT", "5432")
    os.environ.setdefault("MOVEMENT_H3_RESOLUTION", "8")
    os.environ.setdefault("MOVEMENT_COORDINATE_ACTIVE_KEY_VERSION", "1")
    os.environ.setdefault(
        "MOVEMENT_COORDINATE_KEYS",
        '{"1":"AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="}',
    )


def main() -> None:
    sys.path.insert(0, str(PROJECT_ROOT))
    configure_environment()
    SNAPSHOT_PATH.parent.mkdir(parents=True, exist_ok=True)

    import django
    from django.core.management import call_command

    django.setup()
    call_command(
        "spectacular",
        "--format",
        "openapi-json",
        "--file",
        str(SNAPSHOT_PATH),
        "--validate",
        "--fail-on-warn",
        verbosity=0,
    )


if __name__ == "__main__":
    main()
