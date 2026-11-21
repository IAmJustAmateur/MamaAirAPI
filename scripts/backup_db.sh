#!/usr/bin/env bash
set -euo pipefail
umask 077

source "$(dirname -- "${BASH_SOURCE[0]}")/db_common.sh"

usage='Usage: bash scripts/backup_db.sh [--output-dir DIRECTORY]'
case ${1:-} in
    '')
        [[ $# -eq 0 ]] || die "$usage"
        output_dir=${HOME:?}/mamaair-db-backups
        ;;
    --output-dir)
        [[ $# -eq 2 && -n $2 ]] || die "$usage"
        output_dir=$2
        ;;
    -h|--help)
        printf '%s\n' "$usage"
        exit 0
        ;;
    *) die "$usage" ;;
esac

SECONDS=0
find_db_container
mkdir -p -- "$output_dir" || die 'Cannot create the backup directory.'
output_dir=$(CDPATH= cd -P -- "$output_dir" && pwd) || die 'Cannot access the backup directory.'
timestamp=$(date -u +%Y%m%dT%H%M%SZ)
staging=$(mktemp -d -- "$output_dir/.postgresql-$timestamp-XXXXXXXX") ||
    die 'Cannot create a private staging directory for the backup.'
filename=${staging##*/.}.dump
archive=$output_dir/$filename
checksum=$archive.sha256
staged_dump=$staging/$filename
staged_checksum=$staged_dump.sha256

cleanup() {
    if [[ $checksum -ef $staged_checksum && ! $archive -ef $staged_dump ]]; then
        rm -f -- "$checksum" || :
    fi
    rm -f -- "$staged_dump" "$staged_checksum" || :
    rmdir -- "$staging" || :
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

db_exec pg_dump --format=custom --no-password </dev/null >"$staged_dump" 2>/dev/null ||
    die "pg_dump failed (exit $?). Check PostgreSQL availability and credentials."

# Render the full archive to /dev/null so pg_restore also reads the data blocks.
docker exec -i "$db_container" pg_restore --file=/dev/null <"$staged_dump" 2>/dev/null ||
    die "pg_restore could not read the generated archive (exit $?)."

(cd -- "$staging" && sha256sum -- "$filename") >"$staged_checksum" ||
    die 'Cannot calculate the archive SHA-256.'
chmod 600 -- "$staged_dump" "$staged_checksum" || die 'Cannot secure the archive and checksum permissions.'
size=$(wc -c <"$staged_dump") || die 'Cannot read the archive size.'

# Publish the verified archive last. Hard links are atomic and fail if the name exists.
ln -T -- "$staged_checksum" "$checksum" || die 'Cannot publish the checksum.'
ln -T -- "$staged_dump" "$archive" || die 'Cannot publish the archive.'

printf 'Backup complete: %s bytes in %ss. SHA-256 saved to %s\n' "$size" "$SECONDS" "$checksum" >&2
printf '%s\n' "$archive"
