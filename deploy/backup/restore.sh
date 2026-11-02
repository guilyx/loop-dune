#!/usr/bin/env bash
# Restore a backup into a database.
#
#   restore.sh [NAME|latest] [--target URL] [--yes]
#
# NAME is a backup file name (from the local volume or the offsite remote); default
# "latest". Encrypted backups need the age private key: BACKUP_AGE_IDENTITY=/path/key.
# The restore is a single transaction (--clean --if-exists): it either replaces the
# `loop` objects completely or changes nothing.
set -Eeuo pipefail
export SCRIPT=restore
# shellcheck source=lib.sh
source "$(dirname "$(readlink -f "$0")")/lib.sh"

name=latest
target="${RESTORE_DATABASE_URL:-$DB_URL}"
confirm="${RESTORE_CONFIRM:-no}"
while [[ $# -gt 0 ]]; do
  case "$1" in
    --target) target="$2"; shift 2 ;;
    --yes) confirm=yes; shift ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) name="$1"; shift ;;
  esac
done
[[ -n "$target" ]] || die "no target database (set RESTORE_DATABASE_URL or pass --target)"
if [[ "$target" == "$DB_URL" && "$confirm" != yes ]]; then
  die "refusing to overwrite the live database without --yes (or RESTORE_CONFIRM=yes)"
fi

work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT

[[ "$name" != latest ]] || name=$(latest_backup auto)
[[ -n "$name" ]] || die "no backup found locally or offsite"

# Fetch the artifact and its checksum: local volume first, then the remote.
found=""
for tier in daily monthly; do
  if [[ -f "$BACKUP_DIR/$tier/$name" ]]; then
    cp "$BACKUP_DIR/$tier/$name" "$BACKUP_DIR/$tier/$name.sha256" "$work/"
    found="local $tier"; break
  fi
done
if [[ -z "$found" && -n "$BACKUP_REMOTE" ]]; then
  for tier in daily monthly; do
    if rclone copy "$BACKUP_REMOTE/$tier/$name" "$work/" 2>/dev/null && [[ -f "$work/$name" ]]; then
      rclone copy "$BACKUP_REMOTE/$tier/$name.sha256" "$work/"
      found="remote $tier"; break
    fi
  done
fi
[[ -n "$found" ]] || die "backup $name not found"
log "restoring $name ($found)"

(cd "$work" && sha256sum -c "$name.sha256" > /dev/null) || die "checksum mismatch for $name"

dump="$work/$name"
if [[ "$name" == *.age ]]; then
  [[ -n "${BACKUP_AGE_IDENTITY:-}" && -r "${BACKUP_AGE_IDENTITY}" ]] \
    || die "$name is encrypted: set BACKUP_AGE_IDENTITY to the age private key file"
  age -d -i "$BACKUP_AGE_IDENTITY" -o "$work/${name%.age}" "$dump"
  dump="$work/${name%.age}"
fi
pg_restore --list "$dump" > /dev/null

# Grants in the dump reference this role; create it if the target cluster is new.
psql "$target" -v ON_ERROR_STOP=1 -q -c \
  "do \$\$ begin if not exists (select 1 from pg_roles where rolname = 'loop_reader') then create role loop_reader nologin; end if; end \$\$;"
pg_restore --clean --if-exists --no-owner --single-transaction --exit-on-error \
  --dbname="$target" "$dump"

summary=$(psql "$target" -At -c \
  "select count(*) || ' snapshots, latest ' || coalesce(max(ts)::text, 'none') from loop.snapshots")
log "restore complete: $summary"
