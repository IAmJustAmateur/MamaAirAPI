#!/usr/bin/env bash
set -euo pipefail

source "$(dirname -- "${BASH_SOURCE[0]}")/db_common.sh"

usage='Usage: bash scripts/restore_db.sh ARCHIVE --database NEW_DB --confirm-container FULL_CONTAINER_ID'
[[ $# -gt 0 ]] || die "$usage"
case $1 in
    -h|--help)
        printf '%s\n' "$usage"
        exit 0
        ;;
esac

archive=$1
shift
database=
confirmed_container=
while [[ $# -gt 0 ]]; do
    case $1 in
        --database)
            [[ $# -ge 2 && -z $database ]] || die "$usage"
            database=$2
            ;;
        --confirm-container)
            [[ $# -ge 2 && -z $confirmed_container ]] || die "$usage"
            confirmed_container=$2
            ;;
        *) die "$usage" ;;
    esac
    shift 2
done

[[ $database =~ ^[a-z][a-z0-9_]{0,62}$ ]] ||
    die 'Use --database with a new PostgreSQL name of 1 to 63 lowercase ASCII letters, digits or underscores, starting with a letter.'
case $database in
    postgres|template0|template1) die 'Cannot restore into a PostgreSQL maintenance database.' ;;
esac
[[ $confirmed_container =~ ^[0-9a-f]{64}$ ]] ||
    die 'Supply the full database container ID from the verified target server with --confirm-container.'

SECONDS=0
[[ -f $archive && -r $archive ]] || die "Cannot read archive: $archive"
checksum=$archive.sha256
[[ -f $checksum && -r $checksum ]] || die "Cannot read SHA-256 sidecar: $checksum"
IFS=' ' read -r expected_hash checksum_filename <"$checksum" || die 'Cannot read the SHA-256 checksum.'
[[ $expected_hash =~ ^[[:xdigit:]]{64}$ && -n $checksum_filename ]] || die 'Invalid SHA-256 checksum format.'
actual_hash=$(sha256sum <"$archive") || die 'Cannot calculate the archive SHA-256.'
[[ ${actual_hash%% *} == "${expected_hash,,}" ]] || die 'Archive SHA-256 does not match the sidecar.'

find_db_container
[[ $confirmed_container == "$db_container" ]] || die 'The running db container does not match --confirm-container.'

archive_info=$(docker exec -i "$db_container" env LC_ALL=C pg_restore --list <"$archive" 2>/dev/null |
    awk '/^;[[:space:]]+Dumped (from database|by pg_dump) version:/ { print $6 }') ||
    die 'The target pg_restore cannot read the archive. Check the archive format and PostgreSQL version.'
mapfile -t archive_versions <<<"$archive_info"
[[ ${#archive_versions[@]} -eq 2 && ${archive_versions[0]} =~ ^[1-9][0-9]{1,3}\.[0-9]+$ &&
    ${archive_versions[1]} =~ ^[1-9][0-9]{1,3}\.[0-9]+$ ]] ||
    die 'Cannot determine the PostgreSQL major versions from the archive (PostgreSQL 10 or newer required).'

target_info=$(db_exec sh -eu -c '
    printf "%s\n" "$PGDATABASE"
    exec psql --no-psqlrc --no-password --no-align --tuples-only --dbname=postgres \
        --set=ON_ERROR_STOP=1 --set=target_db="$1"
' sh "$database" 2>/dev/null <<'SQL'
SHOW server_version_num;
SELECT CASE WHEN EXISTS (SELECT FROM pg_catalog.pg_database WHERE datname = :'target_db') THEN 'exists' ELSE 'new' END;
SQL
) || die 'Cannot query PostgreSQL on the target. Check server availability and credentials.'
mapfile -t target <<<"$target_info"
[[ ${#target[@]} -eq 3 && ${target[1]} =~ ^[1-9][0-9]{5,7}$ ]] || die 'Cannot determine the target PostgreSQL version.'
[[ $database != "${target[0]}" ]] || die 'Cannot restore into the configured POSTGRES_DB.'
[[ ${target[2]} == new ]] || die "Database '$database' already exists. Choose a new database name."

source_major=${archive_versions[0]%%.*}
dump_major=${archive_versions[1]%%.*}
target_major=$((target[1] / 10000))
(( target_major >= source_major && target_major >= dump_major )) ||
    die "Incompatible PostgreSQL versions: source $source_major, pg_dump $dump_major, target $target_major."

# PostgreSQL also rejects the CREATE if a concurrent operation claimed this name.
db_exec createdb --no-password --maintenance-db=postgres --template=template0 -- "$database" \
    </dev/null 2>/dev/null || die "Could not create new database '$database'. Check privileges and that the name is unused."

db_exec pg_restore --no-password --exit-on-error --single-transaction --no-owner --no-privileges \
    --dbname="$database" <"$archive" 2>/dev/null ||
    die "pg_restore failed after ${SECONDS}s (exit $?). The new database '$database' was retained."

printf "Restored database '%s' on PostgreSQL %s in %ss.\n" "$database" "$target_major" "$SECONDS"
