# Production installation: Grid Registry and Metrology

**Status: preparation only, 20 November 2026.** This guide describes a future production installation. Nothing in it has been applied to production by preparing the guide. Review the actual production resources and the chosen release before executing it. It supplements the existing [production migration plan](PRODUCTION-MIGRATION-PLAN.md) and [Grid Registry test notes](GRID-REGISTRY.md); if the dashboard itself has not yet been deployed to production, follow the dashboard migration plan first.

This guide installs both modules in the existing Django dashboard and its configured **filestatistics PostgreSQL database**, not the OMERO server's own PostgreSQL database. It does not copy the test database, test OMERO account or local METEOR-view data. Production metrology results are generated from production OMERO. It does not decide how to import any pre-existing production grid records: investigate those separately before making changes.

## 1. Record the release and production targets

Before the work window, record the following in the change record. Names shown in the test column are evidence, not production defaults.

| Item | Test reference on 20 November 2026 | Production value to determine |
| --- | --- | --- |
| Namespace | `core-omero-test` | Namespace, cluster and service account |
| Dashboard image | `sha256:e009c0626783dc2113f7b23be224136ced328528e0e8f35de0a1d30b2dd62d77` | Promoted image digest, registry access and previous digest |
| Processor image | `sha256:9be7a2a8e9a729485c55d8c6e387306487b6d940d296b57527ffeec26f698741` | Promoted image digest and compatible OMERO client/base image |
| Dashboard source | `13e52438c01994961070a9450ee3c7ed6337cc25` | Reviewed, built source revision |
| Grid module pin | `18c6d62dd0c8c924a6715c98debaca3985787f9b` | Reviewed release/pin in candidate image |
| Metrology module pin | `21934bfbdf5dbc2000e838494044ebcc3cab0961` | Reviewed release/pin in candidate image |
| METEOR-core | `261bb69f02980ddef53be2165320e8eb2a976bce` | Verified installed commit in processor image |
| Dashboard/filestatistics database | Test `filestatistics-pg15`, database `omerofilestats` | Host, port, database, schema, PostgreSQL version, owner and runtime login |
| OMERO | Test service `omero:4064`, Metrology group ID `103` | Production host, port, web URL and actual group ID |
| Schedule | `0 16 * * 1-5`, `Europe/Berlin` | Weekday window and timezone compatible with production uptime |

These digests identify what was running in test when this document was written, not a guarantee that they remain the current or approved release. Confirm that the dashboard and processor versions are compatible with schema version **6**, that the source commits and installed package match the images, and that no newer change needs to be included. Tag/promote the accepted immutable images and verify the production service account can pull them; do not rely on mutable `latest`. The processor build is a separate image from the dashboard. Its checked-in `Dockerfile.processor` currently starts from a **test-registry OMERO server image**: review whether that image and its OMERO/Ice client match the production server and are reachable from production; build and test a suitable equivalent if necessary. Verify the build log's `Verified METEOR-core source` line and the installed distribution's source, not merely the requested build argument.

The registry upstream documents PostgreSQL **17**. It was rehearsed on isolated PostgreSQL 15 in test, but that is not an upstream PostgreSQL 15 support claim. Check the actual production PostgreSQL version and resolve this compatibility decision before migration.

## 2. Preflight, backup and access

1. Confirm the production dashboard is already operational, including its accounts, ORCID, PostgreSQL connection, backups and permitted routes. Verify production namespace, database identity and server from inside the intended migration environment. The dashboard module tables must be in the database Django uses; confirm separately that this is the intended filestatistics PostgreSQL instance, **not OMERO's database**.
2. Inventory the production schema, existing roles and migration history. Check for `registry_*`, `metrology_*`, their indexes, triggers and sequences, and roles named `dashboard_grids_runtime` and `metrology_processor`. PostgreSQL roles are cluster-wide: an existing role is not evidence it is suitable. Stop and reconcile any collision; the baseline SQL and test grants are not repeatable migrations and can fail on existing objects.
3. Take a fresh full production dashboard/filestatistics backup. Confirm success, include existing and future tables, views and sequences, and test a restore to an isolated database before DDL. Ensure the backup login can read the new module objects and has any required row-level-security access. Keep an independently accessible copy according to the existing backup policy. PostgreSQL metrology artifacts include binary payloads, so account for database, WAL and backup growth. Grid spreadsheet exports are not a database backup.
4. Back up and verify **OMERO itself separately**, including the database and managed files/attachments according to its established procedure. PostgreSQL and OMERO do not share a transaction; restoring one without the other can leave references or attachments requiring reconciliation. Never restore a test dump into production.
5. Choose separate identities: a migration/schema-owner identity with the necessary DDL privileges; the existing limited dashboard runtime login; a limited metrology worker database login; a backup reader; and an OMERO service account. Verify production ORCID users and staff/admin roles are already managed by the dashboard. Grid and Metrology both use the dashboard accounts; no test accounts are copied.
6. For production OMERO, create or provision a dedicated password-login service account that can authenticate without the interactive token/2FA flow, subject to the site's account policy. Restrict membership to the intended Metrology group and grant only the required ability to read its images and create/link analysis file annotations. Verify group membership, pixel streaming and attachment write/link access with an approved representative image. Use the actual production group ID. Do not use root or copy the test account/password into production.
7. Resolve production network policy, service DNS, proxy and registry pull access. The browser assets (including Bulma, Plotly and images) are included with the dashboard; ORCID and OMERO web links remain separate services. Confirm the worker can reach the production OMERO API and filestatistics PostgreSQL. Confirm no schedule overlaps backup, shutdown or maintenance windows, and define operators/alerts for failures, pending REDOs, memory and backups.

## 3. Prepare the two images and configuration

1. Promote the approved dashboard image according to the existing [production migration plan](PRODUCTION-MIGRATION-PLAN.md). Verify the promoted digest and its ability to pull under the production service account. The Dockerfile installs pinned module packages and runs `collectstatic` with both optional modules enabled at **build time**; check the image includes registry CSS/SVGs, metrology figures/scripts, local Bulma and Plotly.
2. Promote the independently verified processor image. If a new build is required, pin the tested METEOR-core commit and retain the installed-source verification in `Dockerfile.processor`. The convenience script `scripts/update_test_meteor_core.py` is hard-coded to the **test** namespace and patches the test CronJob; do not use it as a production deployment command. Rehearse production-specific image building, digest promotion and verification separately.
3. Prepare production-only Secrets using the organisation's secret-management mechanism. The test CronJob consumes these keys:
   - OMERO Secret: `OMERO_USER`, `OMERO_PASSWORD`, `OMERO_METROLOGY_GROUP_ID`.
   - Worker database Secret: `PGUSER`, `PGPASSWORD`, for a dedicated login inheriting only the reviewed `metrology_processor` privileges.
   - The dashboard retains its own existing database and application Secrets. The OMERO service credentials belong in the processor only, not the Django web container.

   Never put real passwords in this guide, committed YAML, command history or logs. Secret names and roles in the examples must be replaced with production values.
4. Configure the dashboard feature flags **after the database is ready**:

   ```text
   DASHBOARD_GRIDS_ENABLED=1
   DASHBOARD_METROLOGY_ENABLED=1
   METROLOGY_OMERO_SOURCE=<stable-production-source-id>
   METROLOGY_OMERO_WEB_URL=https://<trusted-production-omero-web-host>
   ```

   `METROLOGY_OMERO_SOURCE` must exactly match the worker's `OMERO_SOURCE`. Keep that identifier stable across future deployments: it forms part of fileset identity and changing it can cause duplicate processing. Verify the production host, allowed hosts, CSRF origins, ORCID callback and proxy configuration remain correct. Both modules are disabled by default.
5. Prepare a production-specific CronJob manifest; do **not** apply the checked-in test example unchanged. Supply an immutable processor image digest, namespace, service account, production-only Secret references, host, port, database, OMERO group, source and limits. Keep it **suspended** until validation is complete. The following is the test schedule and operational starting point, not a production sizing recommendation:

   ```yaml
   spec:
     schedule: '0 16 * * 1-5'   # Monday–Friday at 16:00
     timeZone: Europe/Berlin
     suspend: true
     concurrencyPolicy: Forbid
     startingDeadlineSeconds: 1800
     jobTemplate:
       spec:
         backoffLimit: 0
         activeDeadlineSeconds: 3300
         template:
           spec:
             restartPolicy: Never
             containers:
               - name: processor
                 image: <production-registry>/<processor>@sha256:<verified-digest>
                 args: ['--limit', '10']
                 env:
                   - {name: OMERO_HOST, value: <production-omero-service>}
                   - {name: OMERO_SOURCE, value: <stable-production-source-id>}
                   - {name: PGHOST, value: <production-filestatistics-postgres>}
                   - {name: PGDATABASE, value: <production-filestatistics-database>}
                   - {name: METROLOGY_ACQUISITION_TIMEZONE, value: Europe/Stockholm}
   ```

   This excerpt is deliberately incomplete: add the two reviewed Secret references, port settings, service account, resources and security settings. `METROLOGY_OMERO_PORT` defaults to `4064`; use it rather than OpenShift's injected `OMERO_PORT`. `PGPORT` defaults to `5432`. The test image uses `METROLOGY_MAX_IMAGE_BYTES=1073741824`, requests 500m CPU / 2 GiB RAM, limits 2 CPU / 8 GiB RAM, and the above 55-minute deadline. Measure representative production PSF memory, image sizes, disk/scratch, duration and backlog before adopting these values. The limit is **ten filesets**, not ten images. Naive acquisition dates default to Stockholm local time; adjust only if production metadata really uses another timezone.

## 4. Install the Grid Registry schema

1. From the exact production candidate image, use an isolated migration Job with the schema-owner database credentials and `DASHBOARD_GRIDS_ENABLED=1`. First run `python manage.py showmigrations registry` and `python manage.py migrate registry --plan`; review dependencies and the database target. Django must use the existing dashboard's `AUTH_USER_MODEL` and database. Do not run migrations automatically on web pod startup.
2. With the target and plan confirmed, run `python manage.py migrate registry` once in the migration Job. Record the Job, migration output and resulting migration state. The migrations create `registry_*` tables, sequences, constraints and immutable-history triggers. They seed a default dewar, cane, puck colours and box types; review those defaults against the intended production inventory. They do **not** import a standalone registry or test data.
3. Review and adapt [17-grid-runtime-grants.sql](17-grid-runtime-grants.sql) to the real production identities and already existing objects. It is a **test-only, initial-install example**: it creates a NOLOGIN group, grants runtime table/sequence access without ordinary DELETE and grants backup access. Do not apply it unchanged or re-create an existing role blindly. A PostgreSQL administrator should grant only the reviewed runtime privileges and protect the history triggers and table ownership. Verify the actual dashboard login inherits them and the backup reader can read all new objects.
4. Check registry tables, migration history, default rows, triggers and grants. Take a fresh post-migration backup and verify the new objects are included; retain the pre-migration backup separately. Do not restore a whole old shared database just to undo a module deployment.

## 5. Install the Metrology schema and database role

1. Obtain the reviewed metrology source at the exact module commit in the selected release. The numbered SQL scripts are in the [dashboard-metrology repository](https://github.com/CCI-GU-Sweden/dashboard-metrology/tree/21934bfbdf5dbc2000e838494044ebcc3cab0961/sql). Before applying, review each script and adapt the database role names and grants to production. In particular `001_initial.sql` assumes `filestats_dashboard` and creates a cluster-wide `metrology_processor` role. If the role or tables already exist, stop and plan an upgrade/reconciliation rather than running the fresh baseline. Confirm the database is the dashboard/filestatistics database, not OMERO's.
2. For a confirmed **fresh** install, a production database administrator applies the scripts in order as a setup identity with `ON_ERROR_STOP`, stopping on any error:

   ```text
   001_initial.sql
   002_analysis_override.sql
   003_artifact_payload.sql
   004_processing_date.sql
   005_redo.sql
   006_thresholds_and_failed_redo.sql
   ```

   For example, after securely configuring the setup connection and `METROLOGY_SOURCE` to the reviewed checkout, invoke each file individually:

   ```sh
   psql -X -v ON_ERROR_STOP=1 -f "$METROLOGY_SOURCE/sql/001_initial.sql"
   psql -X -v ON_ERROR_STOP=1 -f "$METROLOGY_SOURCE/sql/002_analysis_override.sql"
   psql -X -v ON_ERROR_STOP=1 -f "$METROLOGY_SOURCE/sql/003_artifact_payload.sql"
   psql -X -v ON_ERROR_STOP=1 -f "$METROLOGY_SOURCE/sql/004_processing_date.sql"
   psql -X -v ON_ERROR_STOP=1 -f "$METROLOGY_SOURCE/sql/005_redo.sql"
   psql -X -v ON_ERROR_STOP=1 -f "$METROLOGY_SOURCE/sql/006_thresholds_and_failed_redo.sql"
   ```

   Each script commits separately; if one fails, inspect the state and resume only with a reviewed recovery plan. Do not rerun the baseline on an installed schema. The current worker requires `SELECT max(version) FROM public.metrology_schema_version` to return **6**.
3. Create a separate worker **login** through the approved credential process and grant it membership in the reviewed NOLOGIN `metrology_processor` role. Verify worker access to the metrology tables, sequences, current-run view and REDO queue, and its lack of unrelated DDL/ownership. Verify the dashboard runtime can read results and can perform the narrowly granted threshold, REDO and measurement-status/audit operations; the Django application enforces the admin boundary. The SQL assumes the tested role layout and needs production review.
4. Verify the production backup identity can lock/read all metrology tables, views and sequences, including future objects. Take a post-install backup and test or inspect it for the new objects. Review the rollback-only `sql/verify_redo_test.sql` as a test pattern; it assumes test role names and existing data and must not be run unchanged against production.

## 6. Roll out and validate

1. With both database setups and backups complete, deploy the approved dashboard image and production configuration. Verify rollout health and logs, the local `/static/vendor/bulma/bulma.min.css` and other module assets through the production Route, and access from the proxy-restricted networks. Confirm staff/admin can open `/registry/` and `/metrology/`, while researcher/pending/inactive users are denied direct module URLs. Verify dashboard account and ORCID behaviour without changing unrelated routes or collectors.
2. Check Grid Registry navigation, cards, CSS/SVGs and permissions. Validate a representative workflow in a separately agreed safe dataset or environment: preparation, storage, access boundaries and audit history. Grid histories are protected, so do not assume synthetic production entries can simply be deleted. If there are existing production grid records to import, use a separately reviewed data migration with identity mapping, validation and backup; this guide does not perform one.
3. Confirm the production Metrology group and account can access a representative set of OMERO images and metadata. Required inputs include image dimensions/channels from OMERO and calibration/key-value metadata; X/Y pixel sizes are in micrometres, with Z and NA required for relevant analyses. The processor supports multiple images within one fileset. It processes the newest eligible filesets, with queued REDOs first, and skips previously completed filesets unless a REDO is requested.
4. If the maintenance window permits, create **one controlled validation Job** from the suspended production CronJob with a unique name and a reviewed one-fileset limit. This will perform real analysis, insert production PostgreSQL results and create OMERO attachments; choose the representative fileset intentionally and document it. Observe completion, logs, CPU/RAM, run state and `analysis_version`; check measurements, acquisition/import/processing dates and matching file attachments in OMERO. A job can produce scientifically relevant warnings even when it completes—review figures and warnings, especially PSF/RSF. Verify no duplicate processing on a subsequent run, and remove the one-time Job according to the production retention policy.
5. On the Metrology page verify microscope cards and overdue count, charts, category figures, attention links and threshold display. Staff may view; admins can set thresholds and request fileset REDO or ignore/restore individual measurements. Thresholds are scoped to magnification, NA, category, measurement and unit across microscopes; without a configured threshold the app uses a provisional median ±10% when at least three comparable values exist. Scores are calculated on demand and may change as data or thresholds change. Verify a REDO in an agreed safe case: previous successful results remain current until a replacement and its attachments complete; failed requests remain visible in the REDO queue. Older OMERO attachments are retained.
6. Only after validation, set the CronJob to the approved weekday schedule and unsuspend it. Confirm `concurrencyPolicy: Forbid`, the time zone, actual service uptime and the first scheduled run. Backlog processing is at most ten filesets per scheduled run; plan how long the initial production backlog will take. Review alerts for failed Jobs, stuck/pending queues, missing permissions, memory limits, backup failures and storage growth. Keep the test environment and its CronJob independent.

## 7. Recovery and ownership

- Record the prior dashboard image/configuration and processor image/schedule. If the rollout has a problem, suspend the processor first; revert the dashboard image and feature flags only after checking schema compatibility. Disabling a module removes its UI/routes but does not remove its data.
- Do not delete new tables, reverse protected registry history or restore a full database over ongoing production collector writes as a routine rollback. Escalate schema recovery to the database owner and reconcile any grid changes, queued actions, new measurements and OMERO annotations.
- A completed processing run records its METEOR-core revision. Upgrading the processor does not automatically reprocess completed filesets; an admin must queue REDO. On interrupted cross-system writes, inspect the REDO queue, run state and artifact links before intervention. Filesets inaccessible to the service account can remain pending until access is fixed.
- Record the final production image digests, schedule, database schema version, Secret names (not values), backup/restore evidence, the accountable service owner and the support/rotation procedure in the production operations record.
