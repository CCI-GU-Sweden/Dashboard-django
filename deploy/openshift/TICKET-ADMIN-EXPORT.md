# Ticket editing and export

The Incident option is no longer available when creating tickets. Existing
incidents remain readable and can retain their legacy classification; an
administrator can reclassify them using Edit details.

Administrators can edit the original reporter, contact, equipment, report,
ticket type and a closed ticket's resolution note. Each edit is version-checked
and its before/after values are stored in ticket history. Status, issue type,
priority and assignees are changed through Update; tags and researcher links
have their existing controls. Administrators can remove attachments, with the
removal recorded in history. Existing database backups may retain removed data.
Archived tickets must first be restored before editing.

Staff and administrators can export a ZIP containing a UTF-8 `ticket.txt`,
complete ticket-event history and attached images. The export may contain
reporter contact details, internal notes and images; review it before sharing.

For each environment take and verify a database backup, build the candidate,
and have an authorized PostgreSQL administrator apply `16-ticket-admin-edit.sql`
with role names adjusted to that environment. It grants narrowly scoped column
updates and installs the image-removal function, rather than general image
DELETE permission. Recreate these grants and function during recovery. Test
admin/staff permissions, history, image removal, export and existing incidents
before promoting the image. No Django schema migration is required.
