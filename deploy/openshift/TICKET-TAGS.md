# Ticket categories and tags

The dashboard presents both historical `USER_REQUEST` and `USER_REPORT` as
“User issue”, and `INTERNAL_ISSUE` as “Technical issue”. Filtering user issues
includes both historical values. New user issues use `USER_REQUEST`, preserving
compatibility with the shared legacy ticket schema and other applications.
No existing rows are rewritten. Incident remains a separate category.

Tags are Django-owned and do not modify shared ticket tables. Researchers may
select existing tags when creating a permitted ticket; staff and administrators
can create tags and change ticket assignments. Only administrators may delete
a tag, which removes it from all tickets, including archived tickets. Actions
are recorded in the audit log. Other clients using the shared legacy tables do
not automatically see tags.

For each release environment: take and verify a database backup; build the
reviewed image; run migration `accounts.0006` once using the migration identity;
run `15-ticket-tag-grants.sql` as an authorized database administrator after
adjusting role names if needed; verify a new backup succeeds; test tag creation,
assignment, filtering and permissions; then promote the tested image. Both new
tables and their sequences must be readable by the backup role. Reapply grants
as part of database recovery.
