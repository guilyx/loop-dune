# syntax=docker/dockerfile:1.7
# Backups for the Loop database: pg_dump (matching the server's major version),
# age encryption and rclone offsite copies. Build context: deploy/backup/
#   docker build -t loop-backup deploy/backup
FROM postgres:16-alpine

RUN apk add --no-cache age rclone curl bash coreutils tzdata \
 && mkdir -p /backups \
 && chown postgres:postgres /backups

COPY --chmod=0755 lib.sh backup.sh restore.sh verify.sh scheduler.sh healthcheck.sh test-roundtrip.sh /usr/local/bin/

ENV BACKUP_DIR=/backups \
    BACKUP_AT=03:17 \
    VERIFY_WEEKDAY=0 \
    TZ=UTC
VOLUME ["/backups"]
USER postgres
HEALTHCHECK --interval=1h --timeout=30s --start-period=5m --start-interval=10s CMD ["healthcheck.sh"]
ENTRYPOINT ["scheduler.sh"]
