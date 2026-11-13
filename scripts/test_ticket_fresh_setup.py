"""Exercise ticket setup and runtime grants on a disposable PostgreSQL database."""
import os
from pathlib import Path

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dashboard.settings')
import django
django.setup()

from django.core.management import call_command
from django.db import connection, DatabaseError

assert os.environ.get('PGHOST') == '127.0.0.1' and os.environ.get('PGPORT') == '55481'
with connection.cursor() as cursor:
    cursor.execute('SELECT current_database()')
    assert cursor.fetchone()[0] == 'dashboard_ticket_fresh_test'
    cursor.execute("SELECT count(*) FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND c.relkind IN ('r','p','i','S','v','m','f')")
    assert cursor.fetchone()[0] == 0, 'The disposable database must be empty.'

call_command('migrate', interactive=False, verbosity=0)
call_command('setup_ticket_schema', apply=True, verbosity=0)
call_command('setup_ticket_helpers', apply=True, verbosity=0)
from accounts.models import User
admin = User.objects.create_user(username='test-admin', role=User.Role.ADMIN)
grants = Path('modules/dashboard-tickets/deploy/runtime-grants.example.sql').read_text(encoding='utf-8')
assert ':"runtime_role"' in grants
grants = grants.replace(':"runtime_role"', 'dashboard_ticket_fresh_runtime')

with connection.cursor() as cursor:
    cursor.execute('CREATE ROLE dashboard_ticket_fresh_runtime NOLOGIN')
    cursor.execute(grants)
    cursor.execute('SET ROLE dashboard_ticket_fresh_runtime')
    cursor.execute("INSERT INTO public.ticket_equipment (equipment_id,name,category) VALUES ('test','Test','Test')")
    cursor.execute("INSERT INTO public.microscope_ticket (reporter_name,message,source,created_by,updated_by) VALUES ('test','test','DASHBOARD','test','test') RETURNING ticket_id")
    ticket_id = cursor.fetchone()[0]
    cursor.execute("INSERT INTO public.microscope_ticket_event (ticket_id,event_type,actor) VALUES (%s,'CREATED','test')", [ticket_id])
    try:
        cursor.execute('DELETE FROM public.microscope_ticket WHERE ticket_id=%s', [ticket_id])
        raise AssertionError('Runtime role unexpectedly has direct DELETE')
    except DatabaseError:
        pass
    cursor.execute("INSERT INTO public.microscope_ticket_image (ticket_id, filename, extension, image_data) VALUES (%s,'test.png','png',%s) RETURNING image_id", [ticket_id, bytes.fromhex('89504e470d0a1a0a')])
    image_id = cursor.fetchone()[0]
    cursor.execute('SELECT public.dashboard_remove_ticket_image(%s,%s)', [ticket_id, image_id])
    cursor.execute('SELECT count(*) FROM public.microscope_ticket_image WHERE image_id=%s', [image_id])
    assert cursor.fetchone()[0] == 0
    cursor.execute("INSERT INTO public.microscope_ticket_image (ticket_id, filename, extension, image_data) VALUES (%s,'test.png','png',%s) RETURNING image_id", [ticket_id, bytes.fromhex('89504e470d0a1a0a')])
    archived_image_id = cursor.fetchone()[0]
    cursor.execute("INSERT INTO public.accounts_ticketarchive (ticket_id,reason,archived_at,archived_by_id) VALUES (%s,'test',now(),%s)", [ticket_id, admin.pk])
    try:
        cursor.execute('SELECT public.dashboard_remove_ticket_image(%s,%s)', [ticket_id, archived_image_id])
        raise AssertionError('Image removal unexpectedly accepted an archived ticket')
    except DatabaseError:
        pass
    cursor.execute('SELECT public.dashboard_purge_archived_ticket(%s)', [ticket_id])
    cursor.execute('RESET ROLE')
    cursor.execute('SELECT count(*) FROM public.microscope_ticket WHERE ticket_id=%s', [ticket_id])
    assert cursor.fetchone()[0] == 0
print('Fresh ticket setup, runtime grants and restricted helper passed.')
