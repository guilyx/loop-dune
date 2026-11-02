#!/usr/bin/env bash
# Docker HEALTHCHECK: unhealthy when the last successful backup is older than
# BACKUP_MAX_AGE_HOURS (default 30h). A fresh container gets that long to make its first.
set -euo pipefail
: "${BACKUP_DIR:=/backups}" "${BACKUP_MAX_AGE_HOURS:=30}"
limit=$(( BACKUP_MAX_AGE_HOURS * 3600 ))
now=$(date -u +%s)
if [[ -f "$BACKUP_DIR/last-success" ]]; then
  last=$(date -u -r "$BACKUP_DIR/last-success" +%s)
else
  last=$(cat /tmp/scheduler-started 2>/dev/null || echo "$now")
fi
(( now - last < limit )) || { echo "no successful backup for $(( (now - last) / 3600 ))h"; exit 1; }
