# Production dashboard migration plan

Original planning snapshot: 2026-11-10. The migration was carried out on
2026-11-11; see [PRODUCTION-OPERATIONS.md](PRODUCTION-OPERATIONS.md) for the
actual cutover and outstanding checks. Recheck live state before further work;
no production credentials or records are included here.

## Scope and non-negotiable boundaries

- Migrate only the tested application **image**, not a database, dump, users,
  sessions, tickets, tags, policies, filesets or secrets from test to production.
- Keep the production URL and existing maintenance gateway, route, TLS and IP
  allowlist. Keep the old dashboard deployment at zero replicas for rollback.
- Use real ORCID exclusively. The first production user should be the owner of
  ORCID `0000-0003-1611-7572`, authenticated by ORCID before promotion to admin.
- Prepare reviewed production-specific manifests and SQL; the checked-in test
  manifests include test namespaces, hosts, secrets and sandbox defaults and
  **must not be applied to production unchanged**.
- Take and verify a production backup and rehearse restoration into an isolated
  production-controlled location before applying schema changes or cutover.

## Findings from read-only inspection

| Component | Observed production state | Consequence |
| --- | --- | --- |
| Public entry | Route `dashboard`: `dashboard-omero.apps.k8s.gu.se` → `maintenance-nginx:3000`, edge TLS with HTTP redirect and IP whitelist | Preserve this route, certificate and full existing whitelist. |
| Old application | Deployment `dashboard` has 1 ready replica; Service `dashboard:8080`; deployment's image trigger is currently paused | Retain the old image and deployment; record its current digest and prevent it being restarted by the scheduler after cutover. |
| Gateway | Live NGINX config is embedded in the image. It checks `dashboard.flag` and hard-codes `proxy_pass http://dashboard:8080`; the same deployment also serves Flask and OMERO. Deployment strategy is `Recreate`. | A production-specific reviewed NGINX config and rollout are needed; changing only a target in a ConfigMap does not change the live upstream. Gateway rollout may interrupt all three services. |
| Scheduler | `service-schedule` runs every 5 minutes, `Europe/Stockholm`; dashboard currently runs **04:00–23:00 every day** and its script forces exactly one replica while running. | Change only the dashboard section to start Django when zero and leave positive replica counts alone. Preserve the production schedule unless explicitly changed. |
| Database | The old dashboard and the collector use `filestatistics-pg15:5432/omerofilestats`. `filestatisticsdb` has no endpoints and its old deployment is scaled to zero. | Point Django to `filestatistics-pg15`, not the similarly named old service. |
| Existing data | `omerofilestats` is about 29 MB, with 762 imports, 21,496 filesets, 2,527 snapshots, 47 policies and 66 collector runs at inspection. | Preserve this live database and validate real production data in place. These counts naturally change. |
| Collector | The latest three recorded runs succeeded; six older failures are recorded, the latest on 2026-10-05. | Verify the current run and investigate old failures if their cause is still relevant. |
| Schema | The five existing public tables are `imports`, `omero_fileset`, `collector_run`, `group_storage_snapshot` and `storage_policy`. There are no ticket or Django tables. Named columns and types of these five tables match test; physical column order differs for two tables. | Create fresh ticket and Django schemas; named-column comparison is encouraging but does not establish complete constraint, index, permission or behavior compatibility. |
| Database permissions | `gu_cci_postgres` owns the database and can create in `public`; `filestats_dashboard` exists and can read the five existing tables and insert/update policies. The backup reader role does not yet exist. | Use a reviewed migration owner and narrowly scoped runtime/backup grants; verify column-level permissions, sequences and security-definer functions separately. |
| Backup | `postgresbackup` targets `omero-postgres-server`. A separate filestatistics CronJob was created on 2026-11-10; verified backups and the daily/Friday retention are active, with the first backup pinned. A production restore and independent copy remain unverified. | Verify alerting, isolated restore and independent copy. Existing OMERO backups do not protect filestatistics. |
| Capacity | Filestatistics uses a 1 GiB PVC; about 807 MiB was free at inspection. The shared `postgresbackup` PVC is 10 GiB; its current free space is not verified. | Check and increase capacity as appropriate, particularly for ticket images and WAL. Check backup-volume space before selecting retention. |
| Scaling | There is no production dashboard HPA. Test uses 1–3 replicas, CPU target 70%, 100m CPU and 192 MiB memory requests. | Adapt and verify the tested HPA only after the scheduler is compatible. CPU is a load metric, not a count of active connections. |
| Credentials | `filestatistics-app-credentials` exposes production DB references; an existing `django-secret-key` Secret has a lowercase `django_secret_key` key, but its purpose and suitability are unverified. | Create an independent production Django signing key and production ORCID Secret; do not assume existing keys or Secret names can be reused. |

The test Deployment currently runs Git commit
`bf33e39dee91b94b78d56c38d993768759a00831`, image digest
`sha256:1fe5f141037681554c0b5998e7c5a49109ff1367b827f897e2950ef7cc093fe1`
(OpenShift build `dashboard-django-42`). This is a snapshot, not an instruction
to use it if test changes before release. Verify the **running and accepted**
test digest and its full source revision again immediately before tagging.

## Before the migration window

1. **Agree operating choices.** Keep the existing 04:00–23:00, seven-day
   schedule unless the service owner requests otherwise. Back up on weekdays,
   retaining five successful weekday backups and five older Friday backups,
   as detailed below. The schedule runs at 06:20 Stockholm;
   imports rollup starts at 06:15 and the collector at 07:00. Verify
   the shared backup PVC has room, or provision independent storage and an
   off-cluster copy. Set alerts for failures, stale backups and low disk space.
2. **Check storage capacity.** A ticket can contain five images of up to 5 MiB
   each; the 1 GiB PostgreSQL PVC can fill much sooner than the current database
   size suggests. Account for WAL, backups and growth. Confirm the storage class
   supports the intended expansion before resizing; monitor usage afterward.
3. **Register the real ORCID callback:**
   `https://dashboard-omero.apps.k8s.gu.se/accounts/orcid/login/callback/`.
   Keep the existing test callback and add this URI to the same real-ORCID
   public client. ORCID's public-client terms allow an individual only one set
   of Public API credentials. The dashboards need independent Django signing
   keys, Secrets, databases, accounts and sessions, but the two Secret objects
   contain the same ORCID client ID and secret. In ORCID Developer tools, edit
   the client, add the exact HTTPS callback and save it. See [ORCID public-client
   registration](https://info.orcid.org/documentation/integration-guide/registering-a-public-api-client/),
   [redirect URI management](https://info.orcid.org/ufaqs/how-do-redirect-uris-work/)
   and [Public API terms](https://info.orcid.org/public-client-terms-of-service/).
   Do not put the client secret in the repository or chat.
4. The production Secret `dashboard-django-app` was created with a newly
   generated independent `DJANGO_SECRET_KEY` and the real ORCID client ID and
   secret copied from test `dashboard-app`. Verify the key references without
   exposing values. Prepare separate production DB runtime references and a
   backup-reader credential. Set `ORCID_ENVIRONMENT=production`; do not import test
   identities or use sandbox values. Confirm the exact Secret key names in the
   production manifests and restrict who can read them.
5. Record the current production route, whitelist, gateway deployment and
   running NGINX config, scheduler script/resource version, old deployment/image,
   network policy, role bindings and database target in a secure operational
   record. Do not export secret values. Confirm source control and cluster access
   for the operators. Confirm how the first login is limited to the main admin;
   temporarily narrowing the existing IP allowlist to an approved admin source
   is one option, with the full original list restored after bootstrap.
6. Prepare a **production-specific** maintenance ConfigMap from the live NGINX
   config. Preserve the Flask and OMERO server blocks and the dashboard flag;
   change only the dashboard upstream to `dashboard-django:80` and the required
   trusted Host/HTTPS forwarding. The current `maintenance-gateway-config`
   contains stale test host/target values and is not the running NGINX upstream.
   Review the candidate with `nginx -t` in isolation, coordinate the shared
   gateway restart, and verify Flask and OMERO as well as the dashboard.
7. Prepare an exact-match, guarded scheduler patch from the **live production**
   CronJob. Modify only the dashboard branch: within the window, scale zero to
   one, preserve any positive replica count, wait for readiness, then clear the
   flag; outside, set the flag and scale to zero. Do not reuse
   `prepare_dashboard_schedule_patch.py` unchanged: it targets test. The
   existing `scaler-sa` role can get/scale deployments and patch the named
   maintenance ConfigMap; revalidate access and concurrent runs before cutover.
8. Prepare reviewed production manifests for Deployment, Service, HPA, backup
   CronJob and one-off migrations. Do not create a public direct-Django Route.
   The old and new deployments should have different names and selectors.
   Do not enable an automatic image-change deployment trigger.

## Backup and restore gate

1. The `dashboard_backup_reader` login and `dashboard-backup-reader` Secret
   were created for production on 2026-11-10. Verify least privilege and
   SELECT on all required current production tables and sequences, and grant it
   again after each new table/sequence is created. Ensure the reader can also
   dump function and schema definitions; test with the actual backup role.
2. The production CronJob now has tested five-daily/five-Friday retention and a
   pinned pre-migration archive. The test CronJob in
   `13-dashboard-database-backup.yaml` has a different schedule and retention;
   do not change it without a separate decision. The production backup has its
   own storage path and the pruning script selects only its own backup folders.
3. Before migration, run a fresh full custom-format `pg_dump` of the **production
   filestatistics database**. Verify completion, full archive readability and
   checksum; store access-controlled copies, including one outside the shared
   PVC or cluster where feasible. A successful dump is not a restore test.
4. Restore that production archive into an isolated production-controlled
   PostgreSQL instance/database, never into the live database or test database.
   Check counts, schema and representative read-only dashboard queries; then
   rehearse both sets of migrations, grants and a rollback there. Test restoration
   of roles, object ownership, ACLs and security-definer functions separately:
   the archive excludes owners and ACLs. Protect and dispose of the rehearsal
   copy according to the organization's data policy.
5. After the live migration, run and verify a second production backup including
   all new tables and sequences. Run periodic restore exercises and monitor
   backup age. Define recovery point/time objectives and an authorized operator.

### Weekday and Friday retention design

- Run one full backup each Monday through Friday at 06:20 `Europe/Stockholm`.
  Retain the five most recent
  successful weekday snapshots and, separately, the five newest successful
  Friday snapshots that are no longer among those five daily snapshots. Each
  is a distinct recovery point. A successful Friday backup first belongs to the
  daily tier; an older Friday is promoted to the weekly tier when it would
  otherwise leave daily retention. No backup is scheduled for weekends.
- In a normal week this retains ten distinct snapshots. The oldest Friday is
  approximately five weeks old just after a Friday backup and nearly six weeks
  old by the following Thursday; this is not a guaranteed full six weeks of
  age. Retention fills gradually. If Friday is missed, keep the previous
  successful Fridays and never count the missing backup as a slot. Dedicated
  failure and stale-backup alerts still need to be configured and verified.
- Produce each uniquely named backup in an isolated staging directory on the
  destination filesystem. Require `pg_dump` success, a nonempty archive,
  full archive readability with `pg_restore --exit-on-error --file=/dev/null`,
  and a checksum verified against the finished file. Atomically publish the
  complete directory and manifest only after all checks succeed. The archive
  validation does not replace an actual restore rehearsal.
- After each successful publication, calculate the retention sets using the
  backup's Stockholm date. Both tiers select from the same immutable archive
  directories; no physical copy or promotion is needed. Verify all archives'
  checksums before pruning excess snapshots within this backup's own directory.
  Keep unique names and never overwrite a known-good backup to make room. The
  initial pre-migration backup is explicitly pinned in addition to normal
  retention and must be unpinned deliberately after migration and restore tests.
- A failed, incomplete, interrupted, corrupt or unverified backup
  must cause no pruning in either tier. Keep extra backups if necessary, report
  the job as failed and alert on failed or stale backups and low space. Use
  `concurrencyPolicy: Forbid`. Missed Fridays and corrupt archives were tested
  with synthetic fixtures; interrupted runs and disk-full conditions still need
  testing. Provision spare capacity for staging; retaining extra copies during
  errors is intentional.
- Store a separate access-controlled copy outside the backup PVC or cluster,
  and test restoring it. Daily and weekly snapshots on one PVC do not protect
  against failure, loss or corruption of that PVC. Determine the off-cluster
  destination and permissions before relying on backups for production recovery.

## Image promotion and database preparation

1. After acceptance in test, record the running image digest and Git commit;
   tag that **specific image digest** in the test ImageStream with an immutable
   release name, then tag the same image into a separate production ImageStream.
   OpenShift image streams are metadata references, so do not assume tagging
   physically copies image layers or grants cross-project pull access. Inspect
   the resolved production pull specification and digest and test pulling from
   the actual production service account; arrange the minimum registry
   permissions or a deliberate image copy if necessary. Deploy by verified
   production digest. Do not restore or copy any test database content. The
   source build uses Git, and `.dockerignore` excludes local backups and SQLite;
   inspect release contents and provenance as part of approval.
   [Red Hat image stream documentation](https://docs.redhat.com/en/documentation/openshift_container_platform/4.20/html-single/images/index)
   explains image tags and cross-project access.
   For example, after creating/confirming the destination ImageStream and
   choosing a fresh release tag, the CLI equivalent is:

   ```sh
   oc tag core-omero-test/dashboard-django@sha256:VERIFIED_DIGEST core-omero-test/dashboard-django:release-20261111
   oc tag core-omero-test/dashboard-django:release-20261111 core-omero-prod/dashboard-django:release-20261111
   ```

   Replace the placeholder with the actual tested digest and confirm both tags
   resolve to that digest before deployment. Never overwrite a release tag.
   In the web console, inspect the test build/ImageStream and its digest under
   **Builds → ImageStreams**; use the available tag/import controls for the
   destination, then verify the production tag and pull permissions. Exact
   console wording depends on the cluster version. Test's build poller was
   suspended on 2026-11-18; production promotion remains a deliberate operation.
2. Before any DDL, recheck that the target is the writable production
   `omerofilestats`, no ticket/Django tables have appeared, the backup and restore
   gate passed, and no migrations run concurrently. Review owner and role grants.
3. The legacy repository has a fresh baseline
   `db/migrations/001_microscope_tickets.sql` at revision
   `28d83ff02e455f6da004a58f798ac5d093333451`. Its current baseline already
   creates equipment and accepts both legacy user types; **do not run 002–004
   after the current fresh 001**. Review and adapt before production: it seeds
   11 equipment records and grants the collector ticket access. Decide whether
   to start with an empty catalogue or an explicitly verified production list;
   do not copy the test catalogue. Avoid unnecessary collector privileges.
4. Apply the reviewed fresh ticket schema under a controlled migration identity.
   Then run all Django/allauth migrations once from the exact candidate image,
   separately from web startup. Do not copy users or existing Django tables from
   test. The migration role `gu_cci_postgres` can create in `public` but its
   credentials and complete privileges must be verified at execution time.
5. Apply and verify the **complete current** runtime grants, not just the old
   `06-django-runtime-grants.sql`: include verified OMERO groups, researcher
   links, staff assignments, archive, tag tables and sequences, ticket and
   equipment column-level permissions, and policy permissions. Review the
   tested archive/tag/admin SQL files `14`, `15` and `16`; adapt role names.
   Their restricted security-definer functions must be owned by an authorized
   role, use a fixed search path, and grant execution only to the runtime role.
   Verify no broad legacy ticket/image DELETE rights are introduced.
6. Verify the backup role can read the newly created objects, take the post-DDL
   backup and verify the restore plan. Validate uploads, storage, billing,
   policies and collector health against the production schema using read-only
   queries before serving traffic. Verify groups and email drafts against the
   real production records; do not infer access rights from ORCID alone.

## Cutover and verification

1. Create the production Django Deployment and internal Service with the
   verified image and production-only configuration; check pod health and DB
   connectivity privately. Ensure the tested image works with the actual
   production data volume and within CPU/memory limits. Configure the 1–3 CPU
   HPA only when the scheduler transition has been coordinated.
2. Make router forwarded-header handling explicit and trusted for the dashboard
   Route, then verify the gateway forwards the actual host and HTTPS scheme.
   Set Django allowed hosts/CSRF origins for the real production host and the
   internal probe host; enable proxy HTTPS trust only after that verification.
   Preserve the current allowlist, edge TLS and maintenance behavior; test both
   allowed and blocked networks and any authorized admin-only bootstrap window.
3. Coordinate a short maintenance window and prevent the scheduler from
   undoing the transition. Save a precise rollback snapshot. Apply the guarded
   production scheduler change and the production-specific NGINX config, roll
   out the gateway, and verify its three virtual hosts. Route remains on the
   gateway. Confirm Django is ready before removing `dashboard.flag`.
4. After the old deployment is disconnected from the scheduler and gateway,
   scale `dashboard` to zero; retain it and its old image. Ensure neither an
   image trigger nor a scheduler restarts it. Confirm new Django replicas remain
   above one when HPA asks for them; a scheduler must not force them to one.
5. The main administrator signs in with real ORCID `0000-0003-1611-7572` and
   initially sees Pending. An authorized operator independently verifies the
   authenticated `orcid` identity and serially runs the reviewed
   `bootstrap_admin` command once. Confirm its audit entry and admin access;
   restore the original full IP whitelist if it was temporarily narrowed.
   The command requires an already-authenticated active user and refuses to run
   if another active admin exists. Configure a second verified admin/recovery
   procedure when appropriate.

   ```sh
   oc -n core-omero-prod exec deployment/dashboard-django -- python manage.py bootstrap_admin 0000-0003-1611-7572
   ```

   Run only after the first successful production ORCID login and independent
   verification; do not invoke it simultaneously from multiple replicas.
6. Verify existing fileset, uploads, policies and billing figures; admin/staff/
   researcher permissions and verified group scope; ticket create/update,
   tags, images, archive/restore/delete and export with an explicitly identified
   disposable ticket; and ORCID callback, CSRF, session, readiness and liveness.
   Do not expose a researcher until their real group access is verified.
7. Test HPA metrics and a controlled 2-replica condition, confirm the next
   scheduler run leaves it alone, and check the overnight flag/scale-to-zero
   and morning readiness/flag removal. Preserve the 04:00–23:00 seven-day
   production schedule unless approved otherwise. Review monitoring and alerts.

## OpenShift web-console map

Select project `core-omero-prod` before creating or editing anything. Names and
menu wording can vary by console version.

- **Workloads → Secrets / ConfigMaps:** create the reviewed production-only
  Secrets and configuration. Enter credentials directly in the console; do
  not place values in source-controlled YAML or screenshots.
- **Builds → ImageStreams:** inspect the accepted test tag and digest, then
  inspect/create the production ImageStream and verify the promoted digest.
  Use the `oc tag` commands above if the console does not support the desired
  cross-project digest operation.
- **Workloads → CronJobs / Jobs:** review the separate backup schedule and its
  Job logs; create uniquely named one-off migration Jobs from reviewed YAML and
  inspect completion and logs. `service-schedule` is a shared CronJob: compare
  its live YAML and use a guarded, reviewed patch for its dashboard branch.
- **Networking → Routes:** inspect the existing `dashboard` Route, TLS and all
  whitelist entries before and after any reviewed annotation changes. The Route
  continues to point to `maintenance-nginx`.
- **Workloads → Deployments / Pods:** inspect old and new dashboard workloads,
  image digests, rollout status, readiness and the shared maintenance gateway.
  Retain the old dashboard at zero only after its scheduler and traffic have
  been disconnected. Review autoscaling under the new Deployment.
- Before applying any production YAML in **+ Add → Import YAML**, replace every
  test-specific namespace, hostname, Secret reference and digest, and compare
  it with the live production resource. The examples in this repository are
  starting points, not directly deployable production manifests.

## Rollback

- If cutover fails, restore the recorded production gateway configuration and
  dashboard scheduler branch together, keep the maintenance flag in place while
  switching, and bring the original `dashboard` deployment back to its recorded
  replica count. Verify Flask and OMERO as well as the old dashboard, whitelist
  and TLS. Preserve the new deployment, migration state, diagnostic logs and
  newly written production data for investigation.
- New ticket/Django tables are additive; switching the old dashboard back does
  not transfer or erase them. The old application does not necessarily understand
  Django-only ticket links, tags, archive markers or multiple assignments. Avoid
  concurrent old/new ticket writes; reconcile any production changes before a
  later retry.
- Never restore an old full database dump over live production merely to revert
  the dashboard: collector, imports, policies and other writes after the backup
  would be lost. A full recovery is a separate, coordinated decision and should
  be rehearsed in isolation first.

## Remaining checks before execution

- Verify backup alerts and off-cluster storage. An archive was restored in
  isolation; continue periodic restore tests.
- Confirm the initial production equipment catalogue with administrators; the
  chosen 11 legacy defaults were seeded.
- The real ORCID callback and production Secrets were verified during cutover;
  never paste credentials into chat or manifests.
- Verify registry tag/pull behavior with the production service account, the
  live router's forwarded-header policy, and the exact current gateway and
  scheduler state. Compare full collector constraints/permissions and rehearse
  representative queries with production data in isolation.
- Revalidate production YAML/SQL and rollback patches against live resources
  before reusing them. Never blindly reapply the initial zero-replica manifest.
- Verify a blocked network is rejected by the unchanged production whitelist.
