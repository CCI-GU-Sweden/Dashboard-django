"""Integration test against a disposable, empty PostgreSQL database only."""
import os
from io import StringIO

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dashboard.settings')
import django
django.setup()

from django.core.management import call_command, CommandError
from django.db import connection, DatabaseError


def run(command, apply=False):
    output = StringIO()
    call_command(command, apply=apply, stdout=output)
    return output.getvalue()


def expect_collision(command):
    try:
        run(command, apply=True)
    except CommandError as exc:
        assert 'collid' in str(exc), str(exc)
    else:
        raise AssertionError(f'{command} accepted an incompatible object')


with connection.cursor() as cursor:
    cursor.execute('SELECT current_database()')
    database = cursor.fetchone()[0]
    assert database == 'dashboard_schema_test' and os.environ.get('PGHOST') == '127.0.0.1' and os.environ.get('PGPORT') == '55479'
    cursor.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p','i','S','v','m','f')")
    assert cursor.fetchone()[0] == 0, 'The disposable database must be empty.'
    cursor.execute('CREATE TABLE public.imports (id integer)')
expect_collision('setup_upload_schema')
with connection.cursor() as cursor:
    cursor.execute('DROP TABLE public.imports')
assert 'No collisions' in run('setup_upload_schema')
assert 'Created' in run('setup_upload_schema', apply=True)
with connection.cursor() as cursor:
    cursor.execute("INSERT INTO public.imports (time,username,groupname,scope,file_count,total_file_size_mb,import_time_s) VALUES (now(),'test','test','test',1,1,1)")
assert 'matches' in run('setup_upload_schema', apply=True)
with connection.cursor() as cursor:
    cursor.execute('SELECT count(*) FROM public.imports')
    assert cursor.fetchone()[0] == 1
    cursor.execute('CREATE TABLE public.storage_policy (policy_id integer)')
expect_collision('setup_omero_schema')
with connection.cursor() as cursor:
    cursor.execute("SELECT to_regclass('public.omero_fileset')")
    assert cursor.fetchone()[0] is None
    cursor.execute('DROP TABLE public.storage_policy')
    cursor.execute('CREATE TABLE public.unrelated (group_id bigint)')
    cursor.execute('CREATE INDEX idx_omero_fileset_active_group ON public.unrelated (group_id)')
expect_collision('setup_omero_schema')
with connection.cursor() as cursor:
    cursor.execute('DROP TABLE public.unrelated')
assert 'No collisions' in run('setup_omero_schema')
assert 'Created' in run('setup_omero_schema', apply=True)
assert 'matches' in run('setup_omero_schema', apply=True)
with connection.cursor() as cursor:
    cursor.execute('CREATE TABLE public.ticket_equipment (equipment_id text)')
expect_collision('setup_ticket_schema')
with connection.cursor() as cursor:
    cursor.execute("SELECT to_regclass('public.microscope_ticket')")
    assert cursor.fetchone()[0] is None
    cursor.execute('DROP TABLE public.ticket_equipment')
assert 'No collisions' in run('setup_ticket_schema')
assert 'Created' in run('setup_ticket_schema', apply=True)
with connection.cursor() as cursor:
    cursor.execute('SELECT count(*) FROM public.ticket_equipment')
    assert cursor.fetchone()[0] == 0
    cursor.execute("INSERT INTO public.microscope_ticket (reporter_name,message,source,created_by,updated_by) VALUES ('test','test','DASHBOARD','test','test')")
assert 'matches' in run('setup_ticket_schema', apply=True)
with connection.cursor() as cursor:
    cursor.execute('SELECT count(*) FROM public.microscope_ticket')
    assert cursor.fetchone()[0] == 1
    cursor.execute('CREATE TABLE public.accounts_ticketarchive (ticket_id bigint PRIMARY KEY)')
    cursor.execute("CREATE FUNCTION public.dashboard_purge_archived_ticket(bigint) RETURNS void LANGUAGE sql AS 'SELECT'")
expect_collision('setup_ticket_helpers')
with connection.cursor() as cursor:
    cursor.execute('DROP FUNCTION public.dashboard_purge_archived_ticket(bigint)')
assert 'No helper collisions' in run('setup_ticket_helpers')
assert 'Created' in run('setup_ticket_helpers', apply=True)
assert 'match' in run('setup_ticket_helpers', apply=True)
with connection.cursor() as cursor:
    cursor.execute('GRANT EXECUTE ON FUNCTION public.dashboard_purge_archived_ticket(bigint) TO PUBLIC')
expect_collision('setup_ticket_helpers')
with connection.cursor() as cursor:
    cursor.execute('REVOKE EXECUTE ON FUNCTION public.dashboard_purge_archived_ticket(bigint) FROM PUBLIC')
    cursor.execute('SELECT ticket_id FROM public.microscope_ticket')
    ticket_id = cursor.fetchone()[0]
    cursor.execute('INSERT INTO public.accounts_ticketarchive (ticket_id) VALUES (%s)', [ticket_id])
    cursor.execute('CREATE ROLE dashboard_ticket_test_runtime NOLOGIN')
    cursor.execute('GRANT USAGE ON SCHEMA public TO dashboard_ticket_test_runtime')
    cursor.execute('GRANT EXECUTE ON FUNCTION public.dashboard_purge_archived_ticket(bigint) TO dashboard_ticket_test_runtime')
    cursor.execute('SET ROLE dashboard_ticket_test_runtime')
    try:
        cursor.execute('DELETE FROM public.microscope_ticket WHERE ticket_id = %s', [ticket_id])
        raise AssertionError('Runtime role unexpectedly has direct DELETE')
    except DatabaseError:
        pass
    cursor.execute('SELECT public.dashboard_purge_archived_ticket(%s)', [ticket_id])
    cursor.execute('RESET ROLE')
    cursor.execute('SELECT count(*) FROM public.microscope_ticket')
    assert cursor.fetchone()[0] == 0
assert 'match' in run('setup_ticket_helpers', apply=True)
with connection.cursor() as cursor:
    cursor.execute('ALTER TABLE public.omero_fileset ADD COLUMN unexpected integer')
expect_collision('setup_omero_schema')
with connection.cursor() as cursor:
    cursor.execute("SELECT count(*) FROM pg_namespace WHERE nspname LIKE 'dashboard_check_%'")
    assert cursor.fetchone()[0] == 0
print('Schema creation, reuse, data preservation and collision tests passed.')
