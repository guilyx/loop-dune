#!/usr/bin/env bash
# Take one backup of the Loop database.
#
#   pg_dump (custom format) -> validate with pg_restore --list -> encrypt (age, optional)
#   -> sha256 -> keep locally (daily/, plus monthly/ on the 1st) -> copy offsite
#   (rclone, optional) -> prune by age -> heartbeat.
#
# Only the age *public* key lives on the server: a compromised host cannot read the
# offsite history, and the private key is needed only to restore.
set -Eeuo pipefail
export SCRIPT=backup
# shellcheck source=lib.sh
source "$(dirname "$(readlink -f "$0")")/lib.sh"

DIE_PING_URL="$BACKUP_HEARTBEAT_URL"
require_db
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
trap 'log "backup FAILED (line $LINENO)"; ping "$BACKUP_HEARTBEAT_URL" fail "backup failed at line $LINENO"; exit 1' ERR

started=$(date -u +%s)
stamp=$(date -u +%Y%m%dT%H%M%SZ)
name="${BACKUP_PREFIX}-${stamp}.dump"

log "dumping database"
# --no-owner: restorable by any role; privileges are kept (grants to loop_reader).
pg_dump --format=custom --compress=6 --no-owner --dbname="$DB_URL" --file="$work/$name"
pg_restore --list "$work/$name" > /dev/null   # refuse to keep a dump we could not restore
size=$(wc -c < "$work/$name")
log "dump OK: $name ($size bytes)"

if [[ -n "$BACKUP_AGE_RECIPIENTS" ]]; then
  mapfile -t recipients < <(age_recipient_args)
  age "${recipients[@]}" -o "$work/$name.age" "$work/$name"
  rm -f "$work/$name"
  name="$name.age"
  log "encrypted for $(( ${#recipients[@]} / 2 )) recipient(s)"
else
  log "WARNING: BACKUP_AGE_RECIPIENTS is empty, backup is NOT encrypted"
fi
printf '%s  %s\n' "$(sha256_of "$work/$name")" "$name" > "$work/$name.sha256"

mkdir -p "$BACKUP_DIR/daily" "$BACKUP_DIR/monthly"
cp "$work/$name" "$work/$name.sha256" "$BACKUP_DIR/daily/"
tiers=(daily)
if [[ "$(date -u +%d)" == 01 ]]; then
  cp "$work/$name" "$work/$name.sha256" "$BACKUP_DIR/monthly/"
  tiers+=(monthly)
fi

if [[ -n "$BACKUP_REMOTE" ]]; then
  for tier in "${tiers[@]}"; do
    rclone copy "$work/$name" "$BACKUP_REMOTE/$tier/"
    rclone copy "$work/$name.sha256" "$BACKUP_REMOTE/$tier/"
  done
  rclone check "$work" "$BACKUP_REMOTE/daily" --one-way --include "$name*" > /dev/null 2>&1 \
    || die "offsite copy does not match the local backup"
  log "copied offsite to $BACKUP_REMOTE (${tiers[*]})"
fi

# Retention runs only after a successful backup, so the newest copy is never pruned.
find "$BACKUP_DIR/daily" -type f -mtime +"$BACKUP_KEEP_DAILY_DAYS" -delete
find "$BACKUP_DIR/monthly" -type f -mtime +"$BACKUP_KEEP_MONTHLY_DAYS" -delete
if [[ -n "$BACKUP_REMOTE" ]]; then
  for tier_days in "daily:$BACKUP_KEEP_DAILY_DAYS" "monthly:$BACKUP_KEEP_MONTHLY_DAYS"; do
    tier=${tier_days%%:*}
    rclone lsf "$BACKUP_REMOTE/$tier" > /dev/null 2>&1 || continue   # nothing there yet
    rclone delete --retries 1 --min-age "${tier_days#*:}d" "$BACKUP_REMOTE/$tier" \
      || log "WARNING: could not prune $BACKUP_REMOTE/$tier"
  done
fi

elapsed=$(( $(date -u +%s) - started ))
printf '%s %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$name" > "$BACKUP_DIR/last-success"
log "backup complete: $name in ${elapsed}s"
ping "$BACKUP_HEARTBEAT_URL" ok "$name ($size bytes, ${elapsed}s)"
