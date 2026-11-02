#!/usr/bin/env bash
# End-to-end backup test against a real database (used by CI and runnable locally):
#
#   DATABASE_URL=postgresql://... deploy/backup/test-roundtrip.sh
#
# backup (encrypted, offsite via a local rclone remote) -> delete the local copy ->
# restore from offsite into a fresh database -> row counts must match the source ->
# restore drill -> tampered backups are rejected -> live restores need --yes.
set -Eeuo pipefail
export SCRIPT=roundtrip
here="$(dirname "$(readlink -f "$0")")"
# shellcheck source=lib.sh
source "$here/lib.sh"
require_db

tmp=$(mktemp -d)
target_db="loop_roundtrip_target"
target=$(url_with_db "$DB_URL" "$target_db")
cleanup() {
  psql "$DB_URL" -q -c "drop database if exists \"$target_db\"" 2>/dev/null || true
  rm -rf "$tmp"
}
trap cleanup EXIT
fail() { log "FAIL: $*"; exit 1; }
counts() { psql "$1" -At -c "select (select count(*) from loop.snapshots) || '/' || (select count(*) from loop.observations)"; }

age-keygen -o "$tmp/key.txt" 2> /dev/null
export BACKUP_AGE_RECIPIENTS
BACKUP_AGE_RECIPIENTS=$(age-keygen -y "$tmp/key.txt")
export BACKUP_AGE_IDENTITY="$tmp/key.txt"
export BACKUP_DIR="$tmp/local"
export RCLONE_CONFIG_ROUNDTRIP_TYPE=local
export BACKUP_REMOTE="roundtrip:$tmp/offsite"
export BACKUP_HEARTBEAT_URL="" VERIFY_HEARTBEAT_URL=""

log "1/6 backup"
"$here/backup.sh"
name=$(latest_backup auto)
[[ "$name" == *.dump.age ]] || fail "expected an encrypted dump, got '$name'"
[[ -f "$tmp/offsite/daily/$name" && -f "$tmp/offsite/daily/$name.sha256" ]] || fail "offsite copy missing"
head -c 21 "$tmp/offsite/daily/$name" | grep -q "age-encryption.org" || fail "offsite copy is not encrypted"
[[ -f "$BACKUP_DIR/last-success" ]] || fail "last-success marker missing"

log "2/6 restore from offsite into a fresh database"
rm -rf "$BACKUP_DIR"
psql "$DB_URL" -q -c "drop database if exists \"$target_db\"" -c "create database \"$target_db\""
RESTORE_DATABASE_URL="$target" "$here/restore.sh" "$name"
src=$(counts "$DB_URL"); got=$(counts "$target")
[[ "$src" == "$got" ]] || fail "row counts differ: source $src, restored $got"
log "restored counts match: $got (snapshots/observations)"

log "3/6 restore is idempotent (second restore replaces, does not duplicate); key from stdin"
BACKUP_AGE_IDENTITY=- RESTORE_DATABASE_URL="$target" "$here/restore.sh" "$name" < "$tmp/key.txt"
[[ "$(counts "$target")" == "$src" ]] || fail "second restore changed the counts"

log "4/6 restore drill (newest backup, must be under 1h old)"
VERIFY_MAX_AGE_HOURS=1 "$here/verify.sh"

log "5/6 tampered backup is rejected"
printf 'x' >> "$tmp/offsite/daily/$name"
if RESTORE_DATABASE_URL="$target" "$here/restore.sh" "$name" 2> "$tmp/err"; then
  fail "a tampered backup was restored"
fi
grep -q "checksum mismatch" "$tmp/err" || fail "unexpected error: $(cat "$tmp/err")"

log "6/6 restoring over the live database requires --yes"
if "$here/restore.sh" "$name" 2> "$tmp/err"; then fail "live restore ran without --yes"; fi
grep -q "refusing to overwrite" "$tmp/err" || fail "unexpected error: $(cat "$tmp/err")"

log "roundtrip OK"
