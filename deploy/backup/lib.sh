#!/usr/bin/env bash
# Shared helpers for backup.sh / restore.sh / verify.sh. Portable across GNU (CI, VPS
# host) and BusyBox (the alpine image).

: "${BACKUP_DIR:=/backups}"                 # local copies (a Docker volume)
: "${BACKUP_PREFIX:=loop}"                  # file name prefix
: "${BACKUP_REMOTE:=}"                      # rclone path, e.g. b2:my-bucket/loop (empty = local only)
: "${BACKUP_AGE_RECIPIENTS:=}"              # age public keys (space/comma separated); empty = unencrypted
: "${BACKUP_KEEP_DAILY_DAYS:=14}"
: "${BACKUP_KEEP_MONTHLY_DAYS:=400}"
: "${BACKUP_HEARTBEAT_URL:=}"               # pinged on success, <url>/fail on failure
: "${VERIFY_HEARTBEAT_URL:=}"

DB_URL="${BACKUP_DATABASE_URL:-${DATABASE_URL:-}}"

# rclone is configured entirely through RCLONE_CONFIG_<REMOTE>_* environment variables;
# point it at an empty config file so it does not look for (or complain about) one.
if [[ -z "${RCLONE_CONFIG:-}" ]]; then
  RCLONE_CONFIG="${TMPDIR:-/tmp}/loop-backup-rclone.conf"
  [[ -f "$RCLONE_CONFIG" ]] || : > "$RCLONE_CONFIG"
  export RCLONE_CONFIG
fi

log() { printf '%s [%s] %s\n' "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "${SCRIPT:-backup}" "$*" >&2; }
# A script that reports to a heartbeat sets DIE_PING_URL (not exported) so a deliberate
# failure is reported as loudly as an unexpected one (the ERR trap).
die() {
  log "ERROR: $*"
  [[ -z "${DIE_PING_URL:-}" ]] || ping "$DIE_PING_URL" fail "$*"
  exit 1
}

require_db() { [[ -n "$DB_URL" ]] || die "set BACKUP_DATABASE_URL (or DATABASE_URL)"; }

# ping URL ok|fail [message] -- best effort, never fails the caller
ping() {
  local url="$1" status="$2" body="${3:-}"
  [[ -n "$url" ]] || return 0
  url="${url%/}"
  [[ "$status" == ok ]] || url="$url/fail"
  curl -fsS -m 10 --retry 3 -o /dev/null --data-raw "${body:0:10000}" "$url" \
    || log "heartbeat ping failed (ignored)"
}

# Age recipients as repeated -r flags (accepts spaces, commas or newlines).
age_recipient_args() {
  local r
  for r in ${BACKUP_AGE_RECIPIENTS//,/ }; do printf -- '-r\n%s\n' "$r"; done
}

sha256_of() { sha256sum "$1" | cut -d' ' -f1; }

# Replace the database name in a postgres URL: url_with_db URL NAME
url_with_db() {
  local url="$1" name="$2" re='^([a-z]+://[^/]*/)([^/?]*)(\?.*)?$'
  [[ "$url" =~ $re ]] || die "cannot parse database URL"
  printf '%s%s%s' "${BASH_REMATCH[1]}" "$name" "${BASH_REMATCH[3]}"
}

# Newest backup artifact name (excludes checksums) from the local dir or the remote.
latest_backup() {
  local where="${1:-auto}" name=""
  if [[ "$where" != remote ]] && [[ -d "$BACKUP_DIR/daily" ]]; then
    local f
    for f in "$BACKUP_DIR"/daily/*; do   # globs sort; names embed a UTC timestamp
      [[ -f "$f" && "$f" != *.sha256 ]] && name="${f##*/}"
    done
  fi
  if [[ -z "$name" && -n "$BACKUP_REMOTE" ]]; then
    name=$(rclone lsf "$BACKUP_REMOTE/daily" 2>/dev/null | grep -v '\.sha256$' | sort | tail -n 1 || true)
  fi
  printf '%s' "$name"
}
