# Production dashboard operations

Cutover performed 2026-11-11 in `core-omero-prod`. The dashboard remains at
`https://dashboard-omero.apps.k8s.gu.se/`, through the existing edge-TLS Route
`dashboard` and `maintenance-nginx`. The original Route whitelist is unchanged.
The old `dashboard` Deployment is retained at zero replicas for rollback.

The new `dashboard-django` Deployment and internal Service use production
PostgreSQL `filestatistics-pg15/omerofilestats`, production ORCID and an
independent production Django signing key. No test users or tickets were
imported. The first production administrator authenticated with ORCID and was
bootstrapped, and confirmed the Administration page. The initial equipment
catalogue contains the eleven explicitly selected legacy defaults.

The production release image is digest
`sha256:1fe5f141037681554c0b5998e7c5a49109ff1367b827f897e2950ef7cc093fe1`,
source revision `bf33e39dee91b94b78d56c38d993768759a00831`. Release
tags `dashboard-django:release-20261111` were created in both test and prod;
both resolved to this digest. The production Deployment is pinned by digest;
test's build poller is suspended and does not deploy production. Treat release
tags as immutable operationally; registry enforcement has not been verified.

The shared `service-schedule` CronJob retains the existing production hours,
04:00–23:00 every day. During the window it starts Django if scaled to zero and
leaves a positive replica count unchanged; outside it enables the dashboard
maintenance flag and scales Django to zero. The `dashboard-django` HPA targets
70% CPU with a range of 1–3 and five-minute scale-down stabilization. A manual
scheduler run with two ready replicas confirmed the scheduler kept both. The
first overnight stop and morning restart still need observation. This HPA uses
CPU, not connection counts.

`dashboard-production-gateway` supplies the gateway's `default.conf`; it was
derived from the running production config and changes only the dashboard
upstream and forwarded host/scheme. Its isolated NGINX configuration check
passed, and Flask and OMERO responded after the shared gateway rollout. The
gateway Deployment uses Recreate, so changing its configuration can briefly
interrupt all three services.

## Backups and recovery

See [DASHBOARD-BACKUP.md](DASHBOARD-BACKUP.md). The 2026-11-11 scheduled backup
passed checksum/full-read checks and was restored in an isolated, socket-only
PostgreSQL instance. Migrations and a backup-reader dump were rehearsed against
that restored copy. A newer pre-migration backup, including the 07:00 collector
run, is pinned with a `KEEP` file. The first 2026-11-10 backup is separately
pinned by name in the CronJob. The post-admin backup also succeeded. Verify
retention, Job failures and free space regularly; an independent off-cluster
copy and dedicated failure/staleness alerts remain to be arranged and tested.

Never restore a production archive over the live database simply to roll back
the application: imports, collectors and user changes since the backup would be
lost. Restore in isolation and coordinate any full recovery.

## Releasing an accepted test image

1. Test the candidate in `core-omero-test`. Record the **running image digest**
   and its corresponding source revision; do not rely on a moving tag.
2. Choose a new unique release tag, confirm it does not exist, and tag that
   exact digest in test and then the same release into the production
   ImageStream. `oc tag` changes references; it does not guarantee a physical
   cross-registry copy. Confirm that the production tag resolves to the same
   digest and that the production service account can pull it.
3. Review release-specific schema and grant changes. Take and verify a fresh
   production backup and rehearse migrations in isolation before any production
   schema changes. Run migrations once as a separate Job, never on web startup.
4. Update the production Deployment to the verified **production ImageStream
   digest** deliberately, then observe rollout and test dashboard functions.
   Do not enable an automatic production image-change trigger. In the web
   console, use **Builds → ImageStreams** to inspect tags, **Workloads → Jobs**
   to inspect migrations and backups, and **Workloads → Deployments** to inspect
   the new image and rollout. Use CLI tagging if the console cannot express the
   desired cross-project digest operation.

## Rollback outline

Before any change, capture the current gateway, scheduler and replica state;
the guarded rollback patches in this directory match the 2026-11-11 cutover
state and must be revalidated against the current resources. The patch-generation
scripts accept live resource JSON as input; capture it securely with `oc get`
and review it before generating patches. Coordinate the
shared gateway interruption. Suspend the scheduler and wait for active Jobs to
finish, enable the dashboard maintenance flag, apply the validated gateway and
scheduler rollback patches, scale the old dashboard up and verify it, then
resume the scheduler and release maintenance. Confirm Flask and OMERO as well.
Keep new Django tables and production records for investigation; the old
dashboard may not understand new ticket data, so avoid concurrent writes.
