#!/usr/bin/env bash
# Restore drill: restore the newest backup into a scratch database, sanity-check it,
# drop it. A backup is only trusted once it has been restored.
set -Eeuo pipefail
export SCRIPT=verify
# shellcheck source=lib.sh
source "$(dirname "$(readlink -f "$0")")/lib.sh"

require_db
scratch_name="${VERIFY_DATABASE:-loop_restore_check}"
scratch=$(url_with_db "$DB_URL" "$scratch_name")
cleanup() { psql "$DB_URL" -q -c "drop database if exists \"$scratch_name\"" 2>/dev/null || true; }
trap cleanup EXIT
trap 'log "verify FAILED (line $LINENO)"; ping "$VERIFY_HEARTBEAT_URL" fail "restore drill failed at line $LINENO"; exit 1' ERR

name="${1:-$(latest_backup auto)}"
[[ -n "$name" ]] || die "no backup to verify"
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
