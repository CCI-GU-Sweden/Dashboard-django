"""Rehearse ticket model ownership migration on a disposable PostgreSQL DB."""
import os

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dashboard.settings')
import django
django.setup()

from django.db import connection
from django.db.migrations.executor import MigrationExecutor


assert os.environ.get('PGHOST') == '127.0.0.1' and os.environ.get('PGPORT') == '55480'
with connection.cursor() as cursor:
    cursor.execute('SELECT current_database()')
    assert cursor.fetchone()[0] == 'dashboard_ticket_migration_test'
    cursor.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p','i','S','v','m','f')")
    assert cursor.fetchone()[0] == 0, 'The disposable database must be empty.'

old_target = [('accounts', '0006_tickettag_tickettagassignment')]
new_target = [('dashboard_tickets', '0001_initial')]
executor = MigrationExecutor(connection)
executor.migrate(old_target)
old_apps = executor.loader.project_state(old_target).apps
User = old_apps.get_model('accounts', 'User')
user = User.objects.create(username='migration-check', password='!', role='researcher')
old_apps.get_model('accounts', 'TicketResearcherLink').objects.create(ticket_id=42, researcher_id=user.pk)
old_apps.get_model('accounts', 'TicketStaffAssignment').objects.create(ticket_id=42, staff_id=user.pk)
old_apps.get_model('accounts', 'TicketArchive').objects.create(ticket_id=42, reason='test', archived_by_id=user.pk)
tag = old_apps.get_model('accounts', 'TicketTag').objects.create(name='Test tag')
old_apps.get_model('accounts', 'TicketTagAssignment').objects.create(ticket_id=42, tag_id=tag.pk)
ContentType = old_apps.get_model('contenttypes', 'ContentType')
content_type = ContentType.objects.create(app_label='accounts', model='tickettag')
Permission = old_apps.get_model('auth', 'Permission')
permission = Permission.objects.create(name='Migration check', codename='migration_check', content_type_id=content_type.pk)
tables = ('accounts_ticketarchive', 'accounts_ticketresearcherlink', 'accounts_ticketstaffassignment', 'accounts_tickettag', 'accounts_tickettagassignment')


def table_oids():
    with connection.cursor() as cursor:
        cursor.execute('SELECT relname, oid FROM pg_class WHERE oid = ANY(%s::regclass[]) ORDER BY relname', [list(tables)])
        return cursor.fetchall()


original_oids = table_oids()
assert len(original_oids) == 5
executor = MigrationExecutor(connection)
executor.migrate(new_target)
new_apps = executor.loader.project_state(new_target).apps
for name in ('TicketResearcherLink', 'TicketStaffAssignment', 'TicketArchive', 'TicketTag', 'TicketTagAssignment'):
    assert new_apps.get_model('dashboard_tickets', name).objects.count() == 1, name
assert table_oids() == original_oids
assert ContentType.objects.get(pk=content_type.pk).app_label == 'dashboard_tickets'
assert Permission.objects.get(pk=permission.pk).content_type_id == content_type.pk

executor = MigrationExecutor(connection)
executor.migrate(old_target)
assert table_oids() == original_oids
assert old_apps.get_model('accounts', 'TicketTagAssignment').objects.get().ticket_id == 42
assert ContentType.objects.get(pk=content_type.pk).app_label == 'accounts'
assert Permission.objects.get(pk=permission.pk).content_type_id == content_type.pk

executor = MigrationExecutor(connection)
executor.migrate(new_target)
assert table_oids() == original_oids
assert ContentType.objects.get(pk=content_type.pk).app_label == 'dashboard_tickets'

# Conflicting content types must fail without losing or silently merging grants.
executor = MigrationExecutor(connection)
executor.migrate(old_target)
collision = ContentType.objects.create(app_label='dashboard_tickets', model='tickettag')
try:
    MigrationExecutor(connection).migrate(new_target)
    raise AssertionError('Conflicting content types were accepted')
except RuntimeError as exc:
    assert 'Conflicting content types' in str(exc)
assert ContentType.objects.get(pk=content_type.pk).app_label == 'accounts'
assert Permission.objects.get(pk=permission.pk).content_type_id == content_type.pk
assert table_oids() == original_oids
collision.delete()
MigrationExecutor(connection).migrate(new_target)

# Missing legacy columns must stop before the ownership transfer is recorded.
MigrationExecutor(connection).migrate(old_target)
with connection.cursor() as cursor:
    cursor.execute('ALTER TABLE accounts_tickettag RENAME COLUMN name TO unexpected_name')
try:
    MigrationExecutor(connection).migrate(new_target)
    raise AssertionError('Missing ticket column was accepted')
except RuntimeError as exc:
    assert 'missing columns' in str(exc)
with connection.cursor() as cursor:
    cursor.execute('ALTER TABLE accounts_tickettag RENAME COLUMN unexpected_name TO name')
MigrationExecutor(connection).migrate(new_target)
assert table_oids() == original_oids
assert ContentType.objects.get(pk=content_type.pk).app_label == 'dashboard_tickets'
print('Ticket migration, rollback, data preservation and collision tests passed.')
