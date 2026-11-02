#!/usr/bin/env bash
# Operate the VPS stack. Run from anywhere; reads deploy/vps/.env.
#
#   stack.sh deploy [TAG]       pull images (commit SHA or "latest"), restart, health-check
#   stack.sh build              build the images on this machine instead of pulling
#   stack.sh status             containers, freshness per chain, last backup
#   stack.sh backup             take a backup now
#   stack.sh restore NAME|latest [KEYFILE]
#                               restore over the live database (pauses the indexer and
#                               dashboard); KEYFILE is the age private key, read from
#                               your machine through stdin, never stored on the server
#   stack.sh backups            list local backups
#   stack.sh psql [ARGS]        psql as the owner role
#   stack.sh indexer ARGS       one-off indexer command, e.g. `stack.sh indexer run --interval 1d`
#   stack.sh <compose args>     anything else goes to docker compose (up -d, logs -f, ps...)
set -Eeuo pipefail
here="$(cd "$(dirname "$(readlink -f "$0")")" && pwd)"
env_file="${STACK_ENV_FILE:-$here/.env}"

[[ -f "$env_file" ]] || { echo "missing $env_file (copy .env.example and fill it in)" >&2; exit 1; }
compose() { docker compose --project-directory "$here" -f "$here/docker-compose.yml" --env-file "$env_file" "$@"; }
log() { printf '\033[1m==> %s\033[0m\n' "$*" >&2; }

refresh_dashboard() {
  # shellcheck disable=SC2016  # JavaScript, not shell
  compose exec -T dashboard node -e '
    const token = process.env.REVALIDATE_TOKEN;
    if (!token) process.exit(0);
    fetch("http://127.0.0.1:3000/api/revalidate", { method: "POST", headers: { authorization: `Bearer ${token}` } })
      .then(r => process.exit(r.ok ? 0 : 1)).catch(() => process.exit(1));' \
    || log "dashboard refresh failed (pages refresh on their own within the hour)"
}

set_env() {  # set_env KEY VALUE: update .env in place so the next `up` keeps the value
  if grep -q "^$1=" "$env_file"; then
    sed -i "s|^$1=.*|$1=$2|" "$env_file"
  else
    printf '%s=%s\n' "$1" "$2" >> "$env_file"
  fi
}

cmd="${1:-status}"
[[ $# -gt 0 ]] && shift
case "$cmd" in
  deploy)
    tag="${1:-}"
    if [[ -n "$tag" ]]; then
      [[ "$tag" =~ ^[A-Za-z0-9._-]+$ ]] || { echo "invalid tag: $tag" >&2; exit 1; }
      set_env IMAGE_TAG "$tag"
    fi
    log "pulling images (${tag:-tag from .env})"
    compose pull --quiet
    log "starting"
    if ! compose up -d --remove-orphans --wait --wait-timeout 180; then
      log "services did not become healthy; previous images are still on disk:"
      log "  stack.sh deploy <previous-tag>   to roll back"
      compose ps
      exit 1
    fi
    refresh_dashboard
    docker image prune -f --filter "until=168h" > /dev/null
    log "deployed"
    compose ps
    ;;
  build)
    log "building images from this checkout"
    compose build --pull "$@"
    ;;
  status)
    compose ps
    echo
    compose exec -T db psql -U loop -d loop -c \
      "select chain_id, last_snapshot, lag from loop.chain_freshness order by chain_id" 2>/dev/null \
      || log "database not reachable"
    compose exec -T backup sh -c 'cat /backups/last-success 2>/dev/null || echo "no backup yet"' 2>/dev/null \
      | sed 's/^/last backup: /' || true
    ;;
  backup)
    compose exec -T backup backup.sh
    ;;
  backups)
    compose exec -T backup sh -c 'ls -lh /backups/daily /backups/monthly'
    ;;
  restore)
    name="${1:?usage: stack.sh restore NAME|latest [KEYFILE]}"
    key="${2:-/dev/null}"
    [[ -r "$key" ]] || { echo "cannot read key file $key" >&2; exit 1; }
    log "pausing the indexer and dashboard"
    compose stop indexer dashboard
    trap 'log "restarting the indexer and dashboard"; compose start indexer dashboard; refresh_dashboard' EXIT
    compose run --rm --no-deps -T -e BACKUP_AGE_IDENTITY=- backup restore "$name" --yes < "$key"
    ;;
  psql)
    compose exec db psql -U loop -d loop "$@"
    ;;
  indexer)
    compose run --rm --no-deps indexer "$@"
    ;;
  *)
    compose "$cmd" "$@"
    ;;
esac
