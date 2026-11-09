import os
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dashboard.settings')
import django
django.setup()
from accounts.storage import list_billing, list_filesets, list_groups, history, overview_card
from django.db import connection
with connection.cursor() as cursor:
    cursor.execute('SELECT DISTINCT group_id FROM public.group_storage_snapshot WHERE group_id IS NOT NULL ORDER BY group_id LIMIT 3')
    groups = [row[0] for row in cursor.fetchall()]
if len(groups) < 2:
    raise RuntimeError('At least two observed groups are needed for the scoped query test')
allowed = groups[:2]
assert all(int(g['id']) in allowed for g in list_groups(allowed))
assert all(int(g['group_id']) in allowed for g in list_billing({'startDate': '2000-01-01', 'endDate': '2099-01-01'}, allowed_groups=allowed)['groups'])
list_filesets({}, allowed_group=allowed)
history({}, allowed_group=allowed)
overview_card(allowed_group=allowed)
if len(groups) > 2:
    assert not list_filesets({'group_id': str(groups[2])}, allowed_group=allowed)['results']
    assert not history({'group_id': str(groups[2])}, allowed_group=allowed)['history']
print('PostgreSQL multi-group storage and billing scope checks passed.')
