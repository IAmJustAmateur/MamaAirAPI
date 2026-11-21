#!/usr/bin/env bash

die() {
    printf 'Error: %s\n' "$*" >&2
    exit 1
}

find_db_container() {
    local repo_dir
    repo_dir=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd) ||
        die 'Cannot locate the Compose project.'

    db_container=$(docker compose --env-file "$repo_dir/.env" \
        -f "$repo_dir/deployment/docker-compose.yml" ps --status running --quiet db 2>/dev/null) ||
        die 'Cannot access Docker Compose. Check Docker and the project .env file.'
    [[ $db_container =~ ^[0-9a-f]{64}$ ]] || die 'The Compose db service must have one running container.'
}

db_exec() {
    # Read connection settings inside the running database container.
    docker exec -i "$db_container" sh -eu -c '
        unset PGHOSTADDR PGSERVICE
        export PGHOST=127.0.0.1 PGPORT=5432 PGCONNECT_TIMEOUT=5
        export PGUSER="${POSTGRES_USER:?}" PGDATABASE="${POSTGRES_DB:?}"
        export PGPASSWORD="${POSTGRES_PASSWORD:?}"
        exec "$@"
    ' sh "$@"
}
