#!/usr/bin/env bash
# Runs once, when the Postgres volume is first initialised (docker-entrypoint-initdb.d).
# Creates the read-only role the migrations grant to, and the dashboard's login role.
# Rotate the dashboard password later with:
#   ./stack.sh psql -c "alter role dashboard password '...'"
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" \
  -v dashboard_password="$DASHBOARD_DB_PASSWORD" <<'SQL'
select 'create role loop_reader nologin'
where not exists (select 1 from pg_roles where rolname = 'loop_reader')
\gexec
select format('create role dashboard login password %L in role loop_reader', :'dashboard_password')
where not exists (select 1 from pg_roles where rolname = 'dashboard')
\gexec
SQL
