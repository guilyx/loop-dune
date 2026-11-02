#!/usr/bin/env bash
# Container entrypoint.
#
#   scheduler.sh                 run forever: backup daily at BACKUP_AT (UTC), restore
#                                drill after the backup on VERIFY_WEEKDAY (0 = Sunday)
#   scheduler.sh backup|verify|restore [args]   run one command and exit
set -Eeuo pipefail
export SCRIPT=scheduler
here="$(dirname "$(readlink -f "$0")")"
# shellcheck source=lib.sh
source "$here/lib.sh"

case "${1:-schedule}" in
  backup) shift; exec "$here/backup.sh" "$@" ;;
  restore) shift; exec "$here/restore.sh" "$@" ;;
  verify) shift; exec "$here/verify.sh" "$@" ;;
  roundtrip) shift; exec "$here/test-roundtrip.sh" "$@" ;;
  schedule) ;;
  *) exec "$@" ;;
esac

: "${BACKUP_AT:=03:17}"
: "${VERIFY_WEEKDAY:=0}"
: "${BACKUP_ON_START:=false}"
[[ "$BACKUP_AT" =~ ^([01][0-9]|2[0-3]):[0-5][0-9]$ ]] || die "BACKUP_AT must be HH:MM (UTC)"
hh=$((10#${BACKUP_AT%:*})); mm=$((10#${BACKUP_AT#*:}))

stop=false
trap 'stop=true; log "stopping"; [[ -n "${sleeper:-}" ]] && kill "$sleeper" 2>/dev/null; exit 0' TERM INT

date -u +%s > /tmp/scheduler-started
run_once() {
  "$here/backup.sh" || log "backup failed (will retry at the next slot)"
  if [[ "$VERIFY_WEEKDAY" != never && "$(date -u +%w)" == "$VERIFY_WEEKDAY" ]]; then
    if [[ -n "$BACKUP_AGE_RECIPIENTS" && -z "${BACKUP_AGE_IDENTITY:-}" ]]; then
      log "restore drill skipped: backups are encrypted and the private key is not on this host (run it from CI: restore-drill workflow)"
    else
      "$here/verify.sh" || log "restore drill failed"
    fi
  fi
}

[[ "$BACKUP_ON_START" != true ]] || run_once
log "scheduled: backup daily at $BACKUP_AT UTC, restore drill on weekday $VERIFY_WEEKDAY"
while ! $stop; do
  now=$(date -u +%s)
  next=$(( now - now % 86400 + hh * 3600 + mm * 60 ))
  (( next > now )) || next=$(( next + 86400 ))
  log "next backup at $(date -u -d "@$next" +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || echo "$next")"
  sleep $(( next - now )) & sleeper=$!
  wait "$sleeper" || true
  $stop || run_once
done
