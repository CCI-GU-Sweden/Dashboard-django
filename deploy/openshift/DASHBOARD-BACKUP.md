# Dashboard database backup and recovery

## Test cluster configuration

`dashboard-filestatistics-backup` backs up the dashboard's `omerofilestats`
database on `filestatistics-pg15`, separately from the existing `postgresbackup`
CronJob, which targets `omero-postgres-server`.

- Schedule: weekdays at 17:30, `Europe/Stockholm`.
- Storage: the `postgresbackup` PVC, under `/postgresbackup/dashboard-filestatistics`.
- Retention: the latest 30 completed dashboard archives and their checksum files.
- Format: PostgreSQL custom archive, with owner and ACL statements excluded.
- Credentials: the `dashboard-backup-reader` Secret, backed by the PostgreSQL
  login of the same purpose. Its password is never written to this repository.
- Each Job runs `pg_dump`, reads the whole archive through `pg_restore`, writes
  a SHA-256 checksum, and only then retains it and prunes older dashboard
  archives. A failed operation results in a failed Job; it must be monitored.
  The job does not delete files in the OMERO backup directory.

The backup role has SELECT on the current public tables and sequences, USAGE
on the public schema and no write privilege on those tables. It is not a
superuser and cannot create roles or databases. After any migration or collector
change that creates a table or sequence, an authorized database administrator
must grant this account SELECT on the new objects. The backup Job must fail and
alert if it cannot read an object; do not silently omit it. Check the first
scheduled backup after schema changes and periodically perform a restore test.

The archive contains database data and Django account, ticket and audit tables.
It does **not** include PostgreSQL global roles, database credentials, Kubernetes
Secrets, Route settings or other cluster configuration; these require separate
documented recovery. The PVC is shared with OMERO and is not, by itself, proof
of an off-cluster copy or resilience to loss of the entire storage system.
Review capacity, permissions, encryption and any institutional backup policy.

## Restore test performed on 2026-11-09

A fresh administrator-produced archive and the first archive produced by the
scheduled-backup Job were each restored with `pg_restore --exit-on-error` into
separate databases in a temporary PostgreSQL pod, using a local Unix socket only.
The restored user, ticket, image, assignment, fileset, snapshot and Django
migration counts matched the live database at the time. The scheduled backup's
SHA-256 checksum matched. Temporary pods were removed after the check.

This was a database restore and count comparison, not an application login or
full end-to-end service recovery test. Restoring without owners and ACLs means
database roles, grants and Secrets must be recreated before an application can
use the restored database. Do not restore over the shared live database without
a coordinated recovery decision: changes made after a backup would be lost.

## Recovery outline

1. Select and checksum-verify a known-good archive. Preserve the failed system
   and current data for investigation.
2. Restore into a separate PostgreSQL instance or database with a compatible
   major version. Use `pg_restore --exit-on-error --no-owner --no-acl` against
   the new database and inspect any failures.
3. Recreate the required database roles, Secrets, object ownership and grants;
   use separately provisioned credentials. Restore deployment configuration,
   route restrictions, TLS and scheduled jobs from reviewed manifests.
4. Verify Django migrations, account/role and group isolation, ticket and image
   access, collector snapshots, billing and a real ORCID login before switching
   traffic. Test rollback and record the recovery point and any missing writes.
5. Arrange an administrator recovery path. `bootstrap_admin` only promotes an
   already-authenticated ORCID account when no active administrator exists.
   If an active administrator is unavailable, database-level recovery requires
   an authorized operator, independent identity verification and an audit
   record; no automated break-glass procedure has been implemented yet.
