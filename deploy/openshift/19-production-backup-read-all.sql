-- Production filestatistics PostgreSQL instance: backup reader can read current
-- and future tables, views and sequences, including row-secured data.
-- Scope is all databases on this PostgreSQL instance. Requires a superuser.
\set ON_ERROR_STOP on
BEGIN;
GRANT pg_read_all_data TO dashboard_backup_reader;
ALTER ROLE dashboard_backup_reader BYPASSRLS;
COMMIT;
