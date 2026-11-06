"""Staff fileset inventory from the existing collector-owned table."""
from datetime import date, datetime, timedelta, timezone
from django.db import connection


class InvalidStorageFilters(ValueError):
    pass


def list_filesets(params):
    try:
        page = int(params.get('page', '1'))
        size = int(params.get('pageSize', '50'))
        if page < 1 or page > 1000000 or size < 1 or size > 100:
            raise ValueError
    except ValueError:
        raise InvalidStorageFilters from None
    sort_columns = {'fileset_id': 'fileset_id', 'username': 'username', 'group_name': 'group_name', 'imported_at': 'imported_at', 'total_bytes': 'total_bytes', 'source_file_count': 'source_file_count', 'image_count': 'image_count'}
    sort, order = params.get('sort', 'imported_at'), params.get('order', 'desc').lower()
    status = params.get('status', 'active')
    search = params.get('search', '').strip()
    group = params.get('group_id', 'all')
    imported = params.get('imported', 'all')
    minimum = params.get('size', 'any')
    durations = {'all': None, '30d': 30, '90d': 90, '1y': 365}
    sizes = {'any': None, '10gb': 10_000_000_000, '100gb': 100_000_000_000, '1tb': 1_000_000_000_000}
    if (sort not in sort_columns or order not in ('asc', 'desc') or status not in ('active', 'deleted', 'all') or len(search) > 200
            or imported not in durations or minimum not in sizes or (group != 'all' and (not group.isdecimal() or int(group) > 9223372036854775807))):
        raise InvalidStorageFilters
    conditions, values = [], []
    if status == 'active':
        conditions.append('deleted_at IS NULL')
    elif status == 'deleted':
        conditions.append('deleted_at IS NOT NULL')
    if search:
        conditions.append('(username ILIKE %s OR firstname ILIKE %s OR lastname ILIKE %s OR group_name ILIKE %s OR CAST(fileset_id AS text) ILIKE %s)')
        values.extend([f'%{search}%'] * 5)
    if group != 'all':
        conditions.append('group_id = %s')
        values.append(int(group))
    if durations[imported]:
        conditions.append('imported_at >= %s')
        values.append(datetime.now(timezone.utc) - timedelta(days=durations[imported]))
    if sizes[minimum]:
        conditions.append('total_bytes > %s')
        values.append(sizes[minimum])
    where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
    with connection.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) FROM public.omero_fileset' + where, values)
        count = cursor.fetchone()[0]
        cursor.execute(
            'SELECT fileset_id, username, group_name, imported_at, total_bytes, deleted_at, source_file_count, image_count, firstname, lastname '
            'FROM public.omero_fileset' + where + ' ORDER BY ' + sort_columns[sort] + ' ' + order.upper() +
            ' NULLS LAST, fileset_id ASC LIMIT %s OFFSET %s', values + [size, (page - 1) * size],
        )
        rows = cursor.fetchall()
    return {'count': count, 'page': page, 'page_size': size, 'results': [
        {'fileset_id': str(row[0]), 'username': row[1], 'group_name': row[2], 'imported_at': row[3], 'total_bytes': row[4], 'deleted_at': row[5], 'source_file_count': row[6], 'image_count': row[7], 'firstname': row[8], 'lastname': row[9]} for row in rows
    ]}


def list_groups():
    with connection.cursor() as cursor:
        cursor.execute('SELECT group_id, MAX(group_name) FROM public.omero_fileset WHERE group_id IS NOT NULL GROUP BY group_id ORDER BY 2, group_id')
        return [{'id': str(row[0]), 'name': row[1]} for row in cursor.fetchall()]


def list_billing(params):
    try:
        start = date.fromisoformat(params.get('startDate', ''))
        end = date.fromisoformat(params.get('endDate', ''))
        limit = int(params.get('limit', '25'))
        if start > end or limit not in (10, 25, 50):
            raise ValueError
    except (ValueError, TypeError):
        raise InvalidStorageFilters from None
    with connection.cursor() as cursor:
        cursor.execute('''
            SELECT group_id, (ARRAY_AGG(group_name ORDER BY snapshot_date DESC))[1],
                   COUNT(DISTINCT snapshot_date),
                   SUM(billable_bytes)::numeric / 1000000000,
                   SUM(daily_charge_ore)::numeric / 100
            FROM public.group_storage_snapshot
            WHERE snapshot_date BETWEEN %s AND %s
            GROUP BY group_id ORDER BY 5 DESC, 2, group_id LIMIT %s
        ''', [start, end, limit])
        rows = cursor.fetchall()
    return {'period': {'from': start.isoformat(), 'to': end.isoformat(), 'inclusive': True}, 'groups': [
        {'group_id': str(row[0]), 'group_name': row[1], 'snapshot_days': row[2], 'billable_gb_days': float(row[3] or 0), 'total_sek': float(row[4] or 0)} for row in rows
    ]}
