"""Read-only staff ticket inventory; legacy ownership does not grant access."""
from datetime import date, datetime, time, timedelta
import hashlib
import json
from zoneinfo import ZoneInfo
from django import forms
from django.db import connection, transaction
from django.utils import timezone


class InvalidTicketFilters(ValueError):
    pass


class TicketConflict(ValueError):
    pass


class TicketCreateForm(forms.Form):
    reporter_name = forms.CharField(max_length=200, strip=True)
    reporter_identifier = forms.EmailField(max_length=254)
    microscope = forms.CharField(max_length=150, required=False, strip=True)
    message = forms.CharField(max_length=20000, strip=True)
    ticket_type = forms.ChoiceField(choices=[(value, value) for value in ('USER_REQUEST', 'USER_REPORT', 'INTERNAL_ISSUE', 'INCIDENT')])
    issue_type = forms.ChoiceField(required=False, choices=[('', 'Unspecified')] + [(value, value) for value in ('SOFTWARE', 'HARDWARE', 'CONNECTION', 'ACCESS_PERMISSIONS', 'ACQUISITION_IMAGE_QUALITY', 'OTHER')])
    priority = forms.ChoiceField(choices=[(value, value) for value in ('LOW', 'NORMAL', 'HIGH', 'CRITICAL')])
    source_event_id = forms.UUIDField()


class TicketUpdateForm(forms.Form):
    version = forms.IntegerField(min_value=1, max_value=2147483647)
    status = forms.ChoiceField(choices=[(value, value) for value in ('OPEN', 'IN_PROGRESS', 'WAITING', 'RESOLVED', 'CANCELLED')])
    priority = forms.ChoiceField(choices=[(value, value) for value in ('LOW', 'NORMAL', 'HIGH', 'CRITICAL')])
    change_note = forms.CharField(max_length=2000, required=False, strip=True)
    resolution_note = forms.CharField(max_length=2000, required=False, strip=True)


def update_ticket(ticket_id, form, user):
    data = form.cleaned_data
    if not 1 <= ticket_id <= 9223372036854775807:
        return None
    actor = f'dashboard-user:{user.pk}'
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SELECT status, priority, resolution_note, version FROM public.microscope_ticket WHERE ticket_id = %s FOR UPDATE', [ticket_id])
            old = cursor.fetchone()
            if not old:
                return None
            if old[3] != data['version']:
                raise TicketConflict('This ticket changed since you opened it. Reload before saving.')
            status, priority = data['status'], data['priority']
            was_closed = old[0] in ('RESOLVED', 'CANCELLED')
            closing = status != old[0] and status in ('RESOLVED', 'CANCELLED')
            reopening = status != old[0] and was_closed
            if reopening and status not in ('OPEN', 'IN_PROGRESS'):
                raise InvalidTicketFilters('Reopen a closed ticket to Open or In progress first.')
            if reopening and not data['change_note']:
                raise InvalidTicketFilters('Explain why the ticket is being reopened.')
            if data['resolution_note'] and not closing:
                raise InvalidTicketFilters('A closing note can only be added when closing a ticket.')
            resolution = (data['resolution_note'] or None) if closing else (None if reopening else old[2])
            if status == old[0] and priority == old[1] and not data['change_note']:
                return {'ticket_id': str(ticket_id), 'version': old[3]}
            resolved_at = timezone.now() if closing and status == 'RESOLVED' else None
            cursor.execute('''UPDATE public.microscope_ticket SET status = %s, priority = %s,
                resolution_note = %s, resolved_at = CASE WHEN %s THEN %s ELSE resolved_at END,
                updated_at = now(), updated_by = %s, version = version + 1
                WHERE ticket_id = %s RETURNING version''',
                [status, priority, resolution, closing or reopening, resolved_at, actor, ticket_id])
            version = cursor.fetchone()[0]
            changes = {'status': {'before': old[0], 'after': status}, 'priority': {'before': old[1], 'after': priority}, 'resolution_note': {'before': old[2], 'after': resolution}}
            cursor.execute('''INSERT INTO public.microscope_ticket_event
                (ticket_id, event_type, old_status, new_status, note, changes, actor)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)''',
                [ticket_id, 'STATUS_CHANGED' if status != old[0] else 'UPDATED', old[0], status, (resolution if closing else data['change_note']) or None, json.dumps(changes), actor])
    return {'ticket_id': str(ticket_id), 'version': version}


def create_ticket(form, user):
    values = form.cleaned_data
    actor = f'dashboard-user:{user.pk}'
    request_id = str(values['source_event_id'])
    fields = {key: (values[key] or None) for key in ('reporter_name', 'reporter_identifier', 'microscope', 'message', 'ticket_type', 'issue_type', 'priority')}
    request_hash = hashlib.sha256(json.dumps({'fields': fields, 'actor': actor}, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    with transaction.atomic():
        with connection.cursor() as cursor:
            if fields['microscope']:
                cursor.execute('SELECT active FROM public.ticket_equipment WHERE equipment_id = %s FOR SHARE', [fields['microscope']])
                equipment = cursor.fetchone()
                if not equipment or not equipment[0]:
                    raise InvalidTicketFilters('Select active equipment.')
            cursor.execute('''INSERT INTO public.microscope_ticket
                (reporter_name, reporter_identifier, microscope, message, ticket_type, issue_type, priority, source, source_event_id, created_by, updated_by)
                VALUES (%s,%s,%s,%s,%s,%s,%s,'DASHBOARD',%s,%s,%s)
                ON CONFLICT (source, source_event_id) DO NOTHING RETURNING ticket_id, version''',
                [*fields.values(), request_id, actor, actor])
            inserted = cursor.fetchone()
            if not inserted:
                cursor.execute('''SELECT t.ticket_id, t.version, e.changes ->> 'request_hash'
                    FROM public.microscope_ticket t LEFT JOIN public.microscope_ticket_event e
                    ON e.ticket_id = t.ticket_id AND e.event_type = 'CREATED'
                    WHERE t.source = 'DASHBOARD' AND t.source_event_id = %s
                    ORDER BY e.event_id LIMIT 1''', [request_id])
                existing = cursor.fetchone()
                if not existing or existing[2] != request_hash:
                    raise TicketConflict('This submission has already been used with different data.')
                return {'ticket_id': str(existing[0]), 'version': existing[1]}, False
            cursor.execute('''INSERT INTO public.microscope_ticket_event
                (ticket_id, event_type, old_status, new_status, note, changes, actor)
                VALUES (%s, 'CREATED', NULL, 'OPEN', NULL, %s::jsonb, %s)''',
                [inserted[0], json.dumps({'request_hash': request_hash, 'initial': fields}), actor])
    return {'ticket_id': str(inserted[0]), 'version': inserted[1]}, True


def list_equipment():
    with connection.cursor() as cursor:
        cursor.execute('SELECT equipment_id, name, category FROM public.ticket_equipment WHERE active = true ORDER BY category, name')
        return [{'id': row[0], 'name': row[1], 'category': row[2]} for row in cursor.fetchall()]


def list_tickets(params):
    try:
        page = int(params.get('page', '1'))
        size = int(params.get('pageSize', '50'))
        if not 1 <= page <= 1000000 or not 1 <= size <= 100:
            raise ValueError
    except ValueError:
        raise InvalidTicketFilters from None
    search = params.get('search', '').strip()
    statuses = params.getlist('status') if hasattr(params, 'getlist') else [params.get('status', 'all')]
    if not statuses:
        statuses = ['OPEN', 'IN_PROGRESS', 'WAITING']
    if 'all' in statuses:
        statuses = []
    sorts = {'opened_at': 'opened_at', 'updated_at': 'updated_at', 'resolved_at': 'resolved_at', 'reporter_name': 'reporter_name', 'microscope': 'microscope', 'status': 'status', 'issue_type': 'issue_type', 'priority': "CASE priority WHEN 'CRITICAL' THEN 4 WHEN 'HIGH' THEN 3 WHEN 'NORMAL' THEN 2 ELSE 1 END"}
    sort, order = params.get('sort', 'opened_at'), params.get('order', 'desc').lower()
    status_options = ('OPEN', 'IN_PROGRESS', 'WAITING', 'RESOLVED', 'CANCELLED')
    source = params.get('source', 'all')
    date_field = params.get('dateField', 'opened_at')
    if (len(search) > 200 or len(statuses) > len(status_options) or any(s not in status_options for s in statuses) or sort not in sorts
            or order not in ('asc', 'desc') or source not in ('all', 'CONTACT_FORM', 'DASHBOARD')
            or date_field not in ('opened_at', 'updated_at', 'resolved_at')):
        raise InvalidTicketFilters
    conditions, values = [], []
    if statuses:
        conditions.append('status IN (' + ','.join(['%s'] * len(statuses)) + ')')
        values.extend(statuses)
    if source != 'all':
        conditions.append('source = %s')
        values.append(source)
    for key, column in (('reporter', 'reporter_name'), ('message', 'message'), ('microscope', 'microscope')):
        value = params.get(key, '').strip()
        if len(value) > 200:
            raise InvalidTicketFilters
        if value:
            conditions.append(column + ' ILIKE %s')
            values.append(f'%{value}%')
    for key, column, allowed in (('priority', 'priority', ('LOW', 'NORMAL', 'HIGH', 'CRITICAL')), ('type', 'ticket_type', ('USER_REQUEST', 'USER_REPORT', 'INTERNAL_ISSUE', 'INCIDENT')), ('issueType', 'issue_type', ('SOFTWARE', 'HARDWARE', 'CONNECTION', 'ACCESS_PERMISSIONS', 'ACQUISITION_IMAGE_QUALITY', 'OTHER'))):
        value = params.get(key, '')
        if value:
            if value not in allowed:
                raise InvalidTicketFilters
            conditions.append(column + ' = %s')
            values.append(value)
    try:
        start = date.fromisoformat(params['startDate']) if params.get('startDate') else None
        end = date.fromisoformat(params['endDate']) if params.get('endDate') else None
        if start and end and start > end:
            raise ValueError
        if start:
            conditions.append(date_field + ' >= %s')
            values.append(datetime.combine(start, time.min, tzinfo=ZoneInfo('Europe/Stockholm')))
        if end:
            conditions.append(date_field + ' < %s')
            values.append(datetime.combine(end + timedelta(days=1), time.min, tzinfo=ZoneInfo('Europe/Stockholm')))
    except (ValueError, OverflowError):
        raise InvalidTicketFilters from None
    if search:
        conditions.append('(reporter_name ILIKE %s OR microscope ILIKE %s OR message ILIKE %s OR CAST(ticket_id AS text) ILIKE %s)')
        values.extend([f'%{search}%'] * 4)
    where = ' WHERE ' + ' AND '.join(conditions) if conditions else ''
    with connection.cursor() as cursor:
        cursor.execute('SELECT COUNT(*) FROM public.microscope_ticket' + where, values)
        count = cursor.fetchone()[0]
        cursor.execute('SELECT ticket_id, reporter_name, microscope, message, status, priority, opened_at, ticket_type, issue_type, assigned_to, resolved_at, updated_at, source FROM public.microscope_ticket' + where + ' ORDER BY ' + sorts[sort] + ' ' + order.upper() + ' NULLS LAST, ticket_id DESC LIMIT %s OFFSET %s', values + [size, (page - 1) * size])
        rows = cursor.fetchall()
    return {'count': count, 'page': page, 'page_size': size, 'results': [
        {'ticket_id': str(row[0]), 'reporter_name': row[1], 'microscope': row[2], 'message': row[3], 'status': row[4], 'priority': row[5], 'opened_at': row[6], 'ticket_type': row[7], 'issue_type': row[8], 'assigned_to': row[9], 'resolved_at': row[10], 'updated_at': row[11], 'source': row[12]} for row in rows
    ]}


def ticket_summary():
    with connection.cursor() as cursor:
        cursor.execute('''
            WITH clock AS (SELECT now() AS current_time, now() - interval '30 days' AS cutoff),
            resolutions AS (
                SELECT ticket_id, occurred_at AS resolved_time FROM public.microscope_ticket_event
                WHERE new_status = 'RESOLVED' AND old_status IS DISTINCT FROM 'RESOLVED'
                UNION ALL
                SELECT t.ticket_id, t.resolved_at FROM public.microscope_ticket t
                WHERE t.resolved_at IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM public.microscope_ticket_event e WHERE e.ticket_id = t.ticket_id AND e.new_status = 'RESOLVED'
                )
            )
            SELECT COUNT(*) FILTER (WHERE t.opened_at <= c.current_time),
                   COUNT(*) FILTER (WHERE t.status IN ('OPEN','IN_PROGRESS','WAITING')),
                   (SELECT COUNT(DISTINCT r.ticket_id) FROM resolutions r WHERE r.resolved_time > c.cutoff AND r.resolved_time <= c.current_time)
            FROM clock c LEFT JOIN public.microscope_ticket t ON true GROUP BY c.cutoff, c.current_time
        ''')
        total, active, resolved = cursor.fetchone()
    return {'total': total, 'active': active, 'resolved': resolved}


def read_ticket(ticket_id):
    if not 1 <= ticket_id <= 9223372036854775807:
        return None
    with connection.cursor() as cursor:
        cursor.execute('SELECT ticket_id, reporter_name, reporter_identifier, microscope, message, ticket_type, issue_type, priority, status, opened_at, resolved_at, resolution_note, assigned_to, version FROM public.microscope_ticket WHERE ticket_id = %s', [ticket_id])
        row = cursor.fetchone()
        if not row:
            return None
        keys = ('ticket_id', 'reporter_name', 'reporter_identifier', 'microscope', 'message', 'ticket_type', 'issue_type', 'priority', 'status', 'opened_at', 'resolved_at', 'resolution_note', 'assigned_to', 'version')
        result = dict(zip(keys, row))
        result['ticket_id'] = str(result['ticket_id'])
        cursor.execute('SELECT event_type, old_status, new_status, note, actor, occurred_at FROM public.microscope_ticket_event WHERE ticket_id = %s ORDER BY occurred_at DESC, event_id DESC LIMIT 100', [ticket_id])
        result['events'] = [dict(zip(('type', 'old_status', 'new_status', 'note', 'actor', 'occurred_at'), event)) for event in cursor.fetchall()]
        cursor.execute('SELECT image_id, filename FROM public.microscope_ticket_image WHERE ticket_id = %s ORDER BY image_id LIMIT 5', [ticket_id])
        result['images'] = [{'id': str(image[0]), 'filename': image[1]} for image in cursor.fetchall()]
    return result
