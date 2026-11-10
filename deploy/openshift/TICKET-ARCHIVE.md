# Ticket archive deployment and operation

Staff and administrators can archive a ticket with a reason. Archived tickets
are excluded from the Django dashboard's inventory, researcher access and
statistics. Administrators can review their history and images, restore them,
or permanently delete them by entering the ticket number. Archive, restore and
delete actions are recorded in the administration audit log. Deletion removes
the ticket, its events, images, researcher link and staff assignments in one
database transaction; existing backups and the audit log remain.

The archive marker belongs to Django. Other applications reading the shared
legacy tables directly will not automatically hide archived tickets. Permanent
deletion affects those shared tables and therefore all applications using them.

## Release procedure

1. Make and verify a current backup of the shared database and confirm that a
   restore procedure is available. Build a reviewed immutable application image.
2. Run the image's Django migrations once using the documented migration Job.
   Migration `accounts.0005` creates `accounts_ticketarchive`; it does not
   modify existing ticket rows. Keep the current application running until the
   migration and grants are complete.
3. A PostgreSQL administrator must run `14-ticket-delete-function.sql` against
   the target database with `ON_ERROR_STOP`. It grants the runtime role access
   to the archive table and installs a narrowly scoped, schema-qualified function
   to delete only archived tickets. The function's owner needs DELETE rights
   on the three shared ticket tables. Do not grant the runtime role broad DELETE
   on those tables. Recreate this function and grants on database recovery:
   database backups do not restore roles or ACLs.
4. The SQL grants SELECT on `public.accounts_ticketarchive` to the test
   cluster's `dashboard_backup_reader` role. Adjust that role and the runtime
   role if another environment uses different names. Verify that the scheduled
   backup succeeds after the migration.
5. Roll out the same image digest, then verify archiving and restoration using
   a disposable ticket. Check admin/staff/researcher access and audit history.
   Test permanent deletion only with a disposable ticket and confirm that its
   images and history are removed. Existing backups retain deleted information
   until their normal retention expires.

The database operations above must be done separately in each environment; the
test cluster's database roles and settings should not be assumed in production.
