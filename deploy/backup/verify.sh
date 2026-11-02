#!/usr/bin/env bash
# Restore drill: restore the newest backup into a scratch database, sanity-check it,
# drop it. A backup is only trusted once it has been restored.
#
#   verify.sh [NAME]     VERIFY_MAX_AGE_HOURS=N also fails if the newest backup is older
#
# Encrypted backups need the private key (BACKUP_AGE_IDENTITY), which should not live
# on the server: .github/workflows/restore-drill.yml runs this weekly from CI instead.
set -Eeuo pipefail
export SCRIPT=verify
# shellcheck source=lib.sh
source "$(dirname "$(readlink -f "$0")")/lib.sh"

DIE_PING_URL="$VERIFY_HEARTBEAT_URL"
require_db
scratch_name="${VERIFY_DATABASE:-loop_restore_check}"
scratch=$(url_with_db "$DB_URL" "$scratch_name")
key_dir=$(mktemp -d)
cleanup() {
  psql "$DB_URL" -q -c "drop database if exists \"$scratch_name\"" 2>/dev/null || true
  rm -rf "$key_dir"
}
trap cleanup EXIT
if [[ "${BACKUP_AGE_IDENTITY:-}" == - ]]; then   # key on stdin (CI secret): keep it in memory-ish tmp
  (umask 077 && cat > "$key_dir/identity")
  export BACKUP_AGE_IDENTITY="$key_dir/identity"
fi
trap 'log "verify FAILED (line $LINENO)"; ping "$VERIFY_HEARTBEAT_URL" fail "restore drill failed at line $LINENO"; exit 1' ERR

name="${1:-$(latest_backup auto)}"
[[ -n "$name" ]] || die "no backup to verify"
if [[ -n "${VERIFY_MAX_AGE_HOURS:-}" ]]; then
  # names embed the UTC time: loop-20261102T031700Z.dump[.age]
  [[ "$name" =~ ([0-9]{4})([0-9]{2})([0-9]{2})T([0-9]{2})([0-9]{2})([0-9]{2})Z ]] \
    || die "cannot read the time from $name"
  r=("${BASH_REMATCH[@]}")
  taken=$(date -u -d "${r[1]}-${r[2]}-${r[3]} ${r[4]}:${r[5]}:${r[6]}" +%s)
  age_hours=$(( ($(date -u +%s) - taken) / 3600 ))
  (( age_hours <= VERIFY_MAX_AGE_HOURS )) \
    || die "backup $name is ${age_hours}h old (limit ${VERIFY_MAX_AGE_HOURS}h)"
fi
log "restore drill for $name into $scratch_name"
psql "$DB_URL" -v ON_ERROR_STOP=1 -q -c "drop database if exists \"$scratch_name\"" \
  -c "create database \"$scratch_name\""

RESTORE_DATABASE_URL="$scratch" "$(dirname "$(readlink -f "$0")")/restore.sh" "$name"

read -r snapshots observations series < <(psql "$scratch" -At -F ' ' -c \
  "select (select count(*) from loop.snapshots), (select count(*) from loop.observations),
          (select count(*) from loop.series)")
(( snapshots > 0 && observations > 0 && series > 0 )) \
  || die "restored database is empty ($snapshots snapshots, $observations observations)"
# The views must still compute on restored data.
psql "$scratch" -v ON_ERROR_STOP=1 -q -At -c "select count(*) from loop.market_daily" > /dev/null

log "restore drill OK: $snapshots snapshots, $observations observations, $series series"
ping "$VERIFY_HEARTBEAT_URL" ok "$name: $snapshots snapshots, $observations observations"
