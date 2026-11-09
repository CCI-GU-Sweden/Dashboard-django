"""Staff fileset inventory from the existing collector-owned table."""
from datetime import date, datetime, timedelta, timezone
from django.db import connection


class InvalidStorageFilters(ValueError):
    pass


def list_filesets(params, allowed_group=None):
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
    if allowed_group is not None:
        conditions.append('group_id = %s')
        values.append(allowed_group)
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


def list_groups(allowed_group=None):
    with connection.cursor() as cursor:
        cursor.execute('''SELECT group_id, (ARRAY_AGG(group_name ORDER BY source_priority, observed_on DESC NULLS LAST))[1]
            FROM (SELECT group_id, group_name, snapshot_date AS observed_on, 0 AS source_priority FROM public.group_storage_snapshot
                  UNION ALL SELECT group_id, group_name, imported_at::date AS observed_on, 1 AS source_priority FROM public.omero_fileset) groups
            WHERE group_id IS NOT NULL''' + (' AND group_id = %s' if allowed_group is not None else '') + ' GROUP BY group_id ORDER BY 2, group_id', [allowed_group] if allowed_group is not None else [])
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


def history(params, allowed_group=None, is_admin=False):
    period = params.get('period', '30')
    metric = params.get('metric', 'bytes')
    group = params.get('group_id', 'all')
    try:
        if metric not in (('bytes', 'ore') if is_admin else ('bytes',)):
            raise ValueError
        if group != 'all' and (not group.isdecimal() or not 1 <= int(group) <= 9223372036854775807):
            raise ValueError
        if period == 'custom':
            start = date.fromisoformat(params.get('start', ''))
            end = date.fromisoformat(params.get('end', ''))
            if start > end or (end - start).days > 3660:
                raise ValueError
        else:
            if period not in ('7', '30', '365'):
                raise ValueError
            end = date.today()
            start = end - timedelta(days=int(period) - 1)
    except (ValueError, TypeError):
        raise InvalidStorageFilters from None
    conditions = ['snapshot_date BETWEEN %s AND %s']
    values = [start, end]
    if allowed_group is not None:
        conditions.append('group_id = %s')
        values.append(allowed_group)
    if group != 'all':
        conditions.append('group_id = %s')
        values.append(int(group))
    total = 'SUM(total_bytes)::numeric / 1000000000' if metric == 'bytes' else 'SUM(total_bytes::numeric * rate_ore_per_gb_day / 1000000000)'
    billable = 'SUM(billable_bytes)::numeric / 1000000000' if metric == 'bytes' else 'SUM(daily_charge_ore)'
    with connection.cursor() as cursor:
        cursor.execute(f'SELECT snapshot_date, {total}, {billable} FROM public.group_storage_snapshot WHERE ' + ' AND '.join(conditions) + ' GROUP BY snapshot_date ORDER BY snapshot_date', values)
        rows = cursor.fetchall()
    return {'metric': metric, 'history': [{'date': row[0].isoformat(), 'total': float(row[1] or 0), 'billable': float(row[2] or 0)} for row in rows]}


def snapshot_overview(is_admin=False):
    with connection.cursor() as cursor:
        cursor.execute('''SELECT SUM(fileset_count), SUM(billable_fileset_count),
            SUM(total_bytes)::numeric / 1000000000,
            SUM(CASE WHEN policy_type = 'AGREEMENT' THEN billable_bytes ELSE 0 END)::numeric / 1000000000,
            SUM(CASE WHEN policy_type <> 'AGREEMENT' THEN billable_bytes ELSE 0 END)::numeric / 1000000000,
            SUM(overdue_fileset_count), SUM(daily_charge_ore)::numeric / 100
            FROM public.group_storage_snapshot WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM public.group_storage_snapshot)''')
        row = cursor.fetchone()
        cursor.execute('''SELECT group_id, group_name, billable_bytes::numeric / 1000000000,
            GREATEST(total_bytes - billable_bytes, 0)::numeric / 1000000000
            FROM public.group_storage_snapshot WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM public.group_storage_snapshot)
            ORDER BY billable_bytes DESC, group_name LIMIT 50''')
        groups = cursor.fetchall()
    keys = ('filesets', 'billable_filesets', 'storage_gb', 'agreement_gb', 'non_agreement_gb', 'overdue', 'daily_sek')
    metrics = {key: float(value or 0) for key, value in zip(keys, row)}
    if not is_admin:
        metrics = {key: metrics[key] for key in ('filesets', 'storage_gb')}
    return {'metrics': metrics, 'groups': [{'id': str(g[0]), 'name': g[1], 'billable': float(g[2] or 0), 'free': float(g[3] or 0)} for g in groups]}


def admin_table(kind):
    queries = {
        'policies': '''SELECT group_id, group_name, policy_type, grace_days, billing_grace_days, rate_ore_per_gb_day, valid_from, valid_until, notes FROM public.storage_policy ORDER BY group_name, group_id, valid_from DESC''',
        'health': '''SELECT status, started_at, finished_at, filesets_seen, filesets_inserted, filesets_updated, filesets_marked_deleted, snapshots_written, deletion_suppressed, error_message FROM public.collector_run ORDER BY started_at DESC, run_id DESC LIMIT 50''',
    }
    with connection.cursor() as cursor:
        cursor.execute(queries[kind])
        names = [column[0] for column in cursor.description]
        rows = [dict(zip(names, row)) for row in cursor.fetchall()]
        if kind == 'policies':
            for row in rows:
                row['group_id'] = str(row['group_id'])
        return rows


def email_draft(group_id):
    import re
    with connection.cursor() as cursor:
        cursor.execute('''SELECT s.group_name, s.snapshot_date, s.total_bytes::numeric / 1000000000,
            s.billable_bytes::numeric / 1000000000, s.daily_charge_ore::numeric / 100,
            p.policy_type, p.grace_days, p.billing_grace_days, p.rate_ore_per_gb_day
            FROM public.group_storage_snapshot s
            LEFT JOIN LATERAL (SELECT policy_type, grace_days, billing_grace_days, rate_ore_per_gb_day
                FROM public.storage_policy WHERE group_id = s.group_id AND valid_from <= s.snapshot_date
                AND (valid_until IS NULL OR valid_until >= s.snapshot_date) ORDER BY valid_from DESC LIMIT 1) p ON true
            WHERE s.group_id = %s ORDER BY s.snapshot_date DESC LIMIT 1''', [group_id])
        row = cursor.fetchone()
        if not row:
            return None
        cursor.execute('SELECT DISTINCT username FROM public.omero_fileset WHERE group_id = %s AND deleted_at IS NULL AND username IS NOT NULL ORDER BY username', [group_id])
        owners = cursor.fetchall()
    pattern = re.compile(r"[A-Z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?(?:\.[A-Z0-9](?:[A-Z0-9-]{0,61}[A-Z0-9])?)+", re.I)
    recipients = {}
    for owner in owners:
        for email in pattern.findall(owner[0]):
            recipients.setdefault(email.lower(), email)
    return {'group_name': row[0], 'snapshot_date': row[1], 'total_gb': float(row[2] or 0),
            'billable_gb': float(row[3] or 0), 'daily_sek': float(row[4] or 0), 'policy_type': row[5],
            'grace_days': row[6], 'billing_grace_days': row[7], 'rate': float(row[8] or 0),
            'recipients': sorted(recipients.values(), key=str.lower)}
