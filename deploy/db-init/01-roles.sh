#!/bin/sh
# Runs once on first database initialisation: creates the least-privilege runtime role.
# Table-level grants are applied by Alembic migration 0002 (and re-applied on every upgrade).
set -eu
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<SQL
CREATE ROLE cmms_app LOGIN PASSWORD '${CMMS_APP_DB_PASSWORD}';
REVOKE ALL ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO cmms_app;
ALTER DEFAULT PRIVILEGES FOR ROLE cmms_owner IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO cmms_app;
ALTER DEFAULT PRIVILEGES FOR ROLE cmms_owner IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO cmms_app;
SQL
