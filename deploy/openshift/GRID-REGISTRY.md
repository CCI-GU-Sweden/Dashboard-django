# Grid Registry integration in the test dashboard

The dashboard pins `cci-grids` to the registry's `v0.1.0` release commit.
Set `DASHBOARD_GRIDS_ENABLED=1` on the test Deployment to enable its card and
`/registry/` routes. Disabled is the default. Active staff and administrators
can use the registry; researchers and pending or disabled users cannot. The
registry uses existing dashboard accounts and does not import separate users.

The dashboard module contract targets PostgreSQL 15, while the upstream
registry release specifies PostgreSQL 17. The existing test database is
PostgreSQL 15.18. The integrated candidate was rehearsed against isolated
PostgreSQL 15.19: 19 registry contract tests passed and 72 dashboard account
tests passed (three skipped). A separate role test exercised preparation,
storage, denied researcher access and protected history. This is test evidence,
not a claim of upstream support for PostgreSQL 15. Review the database version
and obtain release approval separately before using the registry in production.

The Docker image collects the optional registry's static assets at build time
without turning the feature on at runtime. Verify the packaged CSS and SVGs
when building a new image. Test rollout is manual and production is independent;
see [manual test builds](TEST-BUILD-AND-DEPLOY.md).

## Database migration and permissions

Before test migration, take a fresh full dashboard database backup and verify
its checksum and an isolated restore. Review `showmigrations` and verify the
target database, migration identity, existing roles, and absence of pre-existing
registry tables. Never run this against production by substituting a namespace.

Run the registry's Django migrations once from the exact candidate image with
`DASHBOARD_GRIDS_ENABLED=1`, using the existing schema owner; keep migrations
out of web startup. The migrations create `registry_*` tables, trigger functions
and default inventory entries, and refer to dashboard accounts by foreign key.
They do not copy data from the standalone registry or from another environment.

After a successful first migration, a PostgreSQL administrator can review and
apply [17-grid-runtime-grants.sql](17-grid-runtime-grants.sql) in the test
database. It creates a non-login `dashboard_grids_runtime` group, grants it to
the existing `filestats_dashboard` login, grants registry-specific runtime
privileges, and allows the existing backup reader to read registry tables and
sequences. It intentionally fails if the role already exists; inspect existing
grants before any repeat. Runtime is not the table owner, cannot drop protections,
and does not receive DELETE privileges on registry tables. History records have
only SELECT/INSERT grants and are additionally protected by database triggers.

Immediately run another backup and verify it includes the registry tables.
Then roll out the exact migrated image and feature flag together. Test staff and
admin access, researcher denial, CSS/icons and a synthetic registry workflow;
review or remove synthetic records according to the module's history rules.
Disabling the feature flag removes its card and routes without deleting data.
