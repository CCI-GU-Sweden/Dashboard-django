-- Test-only initial registry permissions. Run as a PostgreSQL administrator
-- after successful registry migrations, after verifying role names and backup.
-- This role has no login; the existing dashboard login inherits its grants.
\set ON_ERROR_STOP on
BEGIN;
SET LOCAL lock_timeout = '5s';
CREATE ROLE dashboard_grids_runtime NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION;
GRANT dashboard_grids_runtime TO filestats_dashboard;
GRANT USAGE ON SCHEMA public TO dashboard_grids_runtime, dashboard_backup_reader;

-- Mutable registry state. Deliberately do not grant DELETE or object ownership.
GRANT SELECT, INSERT, UPDATE ON TABLE
    public.registry_dewar, public.registry_cane, public.registry_puck,
    public.registry_gridbox, public.registry_gridboxtype, public.registry_gridslot,
    public.registry_grid, public.registry_grididentifiercounter,
    public.registry_preparationsession, public.registry_preparationsuggestion,
    public.registry_sampleowner, public.registry_owneraccessgrant
    TO dashboard_grids_runtime;

-- History and deletion records are append-only; database triggers also protect them.
GRANT SELECT, INSERT ON TABLE
    public.registry_auditevent, public.registry_boxevent, public.registry_gridevent,
    public.registry_puckevent, public.registry_deletedgrid
    TO dashboard_grids_runtime;

GRANT SELECT ON TABLE
    public.registry_dewar, public.registry_cane, public.registry_puck,
    public.registry_gridbox, public.registry_gridboxtype, public.registry_gridslot,
    public.registry_grid, public.registry_grididentifiercounter,
    public.registry_preparationsession, public.registry_preparationsuggestion,
    public.registry_sampleowner, public.registry_owneraccessgrant,
    public.registry_auditevent, public.registry_boxevent, public.registry_gridevent,
    public.registry_puckevent, public.registry_deletedgrid
    TO dashboard_backup_reader;

DO $grant_registry_sequences$
DECLARE seq record;
BEGIN
    FOR seq IN SELECT c.relname FROM pg_class c
        JOIN pg_namespace n ON n.oid = c.relnamespace
        WHERE n.nspname = 'public' AND c.relkind = 'S'
          AND c.relname LIKE 'registry\_%' ESCAPE '\'
    LOOP
        EXECUTE format('GRANT USAGE, SELECT ON SEQUENCE public.%I TO dashboard_grids_runtime', seq.relname);
        EXECUTE format('GRANT SELECT ON SEQUENCE public.%I TO dashboard_backup_reader', seq.relname);
    END LOOP;
END;
$grant_registry_sequences$;
COMMIT;
