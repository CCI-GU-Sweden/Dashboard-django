"""Read-only staff ticket inventory; legacy ownership does not grant access."""
from datetime import date, datetime, time, timedelta
import hashlib
import json
from zoneinfo import ZoneInfo
from io import BytesIO
from pathlib import PureWindowsPath
import warnings
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
    issue_type = forms.ChoiceField(required=False, choices=[('', 'Unspecified')] + [(value, value) for value in ('SOFTWARE', 'HARDWARE', 'CONNECTION', 'ACCESS_PERMISSIONS', 'ACQUISITION_IMAGE_QUALITY', 'OTHER')])
    assigned_to = forms.CharField(max_length=30, required=False, strip=True)


def validate_images(files):
    from PIL import Image, UnidentifiedImageError
    if len(files) > 5:
        raise InvalidTicketFilters('A ticket can contain at most five images.')
    images = []
    for upload in files:
        if not upload.size or upload.size > 5 * 1024 * 1024:
            raise InvalidTicketFilters('Each image must be non-empty and at most 5 MiB.')
        raw = upload.read(5 * 1024 * 1024 + 1)
        if len(raw) != upload.size or len(raw) > 5 * 1024 * 1024:
            raise InvalidTicketFilters('Invalid image size.')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error', Image.DecompressionBombWarning)
                with Image.open(BytesIO(raw), formats=('PNG', 'JPEG')) as image:
                    if image.format not in ('PNG', 'JPEG') or image.width * image.height > 20_000_000 or getattr(image, 'n_frames', 1) != 1:
                        raise ValueError
                    image.load()
                    extension = 'png' if image.format == 'PNG' else 'jpeg'
        except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
            raise InvalidTicketFilters('Upload a valid, single-frame PNG or JPEG image of at most 20 megapixels.') from None
        stem = PureWindowsPath(upload.name.replace('/', '\\')).stem
        stem = ''.join('_' if ord(char) < 32 or ord(char) == 127 else char for char in stem).strip()[:240] or 'image'
        images.append({'filename': f'{stem}.{extension}', 'extension': extension, 'data': raw})
    return images


def add_images(cursor, ticket_id, images):
    metadata = []
    for image in images:
        cursor.execute('''INSERT INTO public.microscope_ticket_image (ticket_id, filename, extension, image_data)
            VALUES (%s, %s, %s, %s) RETURNING image_id''', [ticket_id, image['filename'], image['extension'], image['data']])
        metadata.append({'id': str(cursor.fetchone()[0]), 'filename': image['filename']})
    return metadata


def update_ticket(ticket_id, form, user, images=None):
    from .models import User
    images = images or []
    data = form.cleaned_data
    if not 1 <= ticket_id <= 9223372036854775807:
        return None
    actor = f'dashboard-user:{user.pk}'
    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute('SELECT status, priority, resolution_note, version, assigned_to, issue_type FROM public.microscope_ticket WHERE ticket_id = %s FOR UPDATE', [ticket_id])
            old = cursor.fetchone()
            if not old:
                return None
            if old[3] != data['version']:
                raise TicketConflict('This ticket changed since you opened it. Reload before saving.')
            status, priority = data['status'], data['priority']
            assigned = old[4]
            if 'assigned_to' in form.data:
                selected = data['assigned_to']
                if selected:
                    if not selected.isdecimal() or len(selected) > 19 or int(selected) > 9223372036854775807 or not User.objects.filter(pk=int(selected), is_active=True, role__in=(User.Role.STAFF, User.Role.ADMIN)).exists():
                        raise InvalidTicketFilters('Select an active staff member or administrator.')
                    assigned = f'dashboard-user:{int(selected)}'
                else:
                    assigned = None
            issue = (data['issue_type'] or None) if 'issue_type' in form.data else old[5]
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
            if status == old[0] and priority == old[1] and assigned == old[4] and issue == old[5] and not data['change_note'] and not images:
                return {'ticket_id': str(ticket_id), 'version': old[3]}
            if images:
                cursor.execute('SELECT COUNT(*) FROM public.microscope_ticket_image WHERE ticket_id = %s', [ticket_id])
                if cursor.fetchone()[0] + len(images) > 5:
                    raise InvalidTicketFilters('A ticket can contain at most five images.')
            resolved_at = timezone.now() if closing and status == 'RESOLVED' else None
            cursor.execute('''UPDATE public.microscope_ticket SET status = %s, priority = %s, assigned_to = %s, issue_type = %s,
                resolution_note = %s, resolved_at = CASE WHEN %s THEN %s ELSE resolved_at END,
                updated_at = now(), updated_by = %s, version = version + 1
                WHERE ticket_id = %s RETURNING version''',
                [status, priority, assigned, issue, resolution, closing or reopening, resolved_at, actor, ticket_id])
            version = cursor.fetchone()[0]
            changes = {'status': {'before': old[0], 'after': status}, 'priority': {'before': old[1], 'after': priority}, 'resolution_note': {'before': old[2], 'after': resolution}, 'assigned_to': {'before': old[4], 'after': assigned}, 'issue_type': {'before': old[5], 'after': issue}}
            if images:
                changes['images_added'] = add_images(cursor, ticket_id, images)
            if closing and data['change_note']:
                cursor.execute('''INSERT INTO public.microscope_ticket_event
                    (ticket_id, event_type, old_status, new_status, note, changes, actor)
                    VALUES (%s, 'UPDATED', %s, %s, %s, %s::jsonb, %s)''',
                    [ticket_id, old[0], status, data['change_note'], json.dumps({'update_kind': 'PROGRESS_NOTE'}), actor])
            cursor.execute('''INSERT INTO public.microscope_ticket_event
                (ticket_id, event_type, old_status, new_status, note, changes, actor)
                VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)''',
                [ticket_id, 'STATUS_CHANGED' if status != old[0] else 'UPDATED', old[0], status, (resolution if closing else data['change_note']) or None, json.dumps(changes), actor])
    return {'ticket_id': str(ticket_id), 'version': version}


def create_ticket(form, user, images=None):
    from .models import AuditEvent, TicketResearcherLink, User
    images = images or []
    values = form.cleaned_data
    actor = f'dashboard-user:{user.pk}'
    request_id = str(values['source_event_id'])
    fields = {key: (values[key] or None) for key in ('reporter_name', 'reporter_identifier', 'microscope', 'message', 'ticket_type', 'issue_type', 'priority')}
    hash_payload = {'fields': fields, 'actor': actor}
    if images:
        hash_payload['images'] = [[image['filename'], hashlib.sha256(image['data']).hexdigest()] for image in images]
    request_hash = hashlib.sha256(json.dumps(hash_payload, sort_keys=True, separators=(',', ':')).encode()).hexdigest()
    with transaction.atomic():
        if user.role == User.Role.RESEARCHER:
            locked_user = User.objects.select_for_update().get(pk=user.pk)
            if not locked_user.is_active or locked_user.role != User.Role.RESEARCHER or not locked_user.can_create_tickets:
                raise InvalidTicketFilters('Ticket creation is not enabled for this account.')
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
            metadata = add_images(cursor, inserted[0], images)
            if user.role == User.Role.RESEARCHER:
                TicketResearcherLink.objects.create(ticket_id=inserted[0], researcher=user)
                AuditEvent.objects.create(actor=user, target=user, action='ticket_researcher_linked', before={}, after={'ticket_id': str(inserted[0]), 'researcher_id': user.pk})
            cursor.execute('''INSERT INTO public.microscope_ticket_event
                (ticket_id, event_type, old_status, new_status, note, changes, actor)
                VALUES (%s, 'CREATED', NULL, 'OPEN', NULL, %s::jsonb, %s)''',
                [inserted[0], json.dumps({'request_hash': request_hash, 'initial': fields, 'images_added': metadata}), actor])
    return {'ticket_id': str(inserted[0]), 'version': inserted[1]}, True


def list_equipment(include_inactive=False):
    with connection.cursor() as cursor:
        cursor.execute('SELECT equipment_id, name, category, active FROM public.ticket_equipment' + ('' if include_inactive else ' WHERE active = true') + ' ORDER BY category, name, equipment_id')
        return [{'id': row[0], 'name': row[1], 'category': row[2], 'active': row[3]} for row in cursor.fetchall()]


class EquipmentForm(forms.Form):
    name = forms.CharField(max_length=150, strip=True)
    category = forms.CharField(max_length=100, strip=True)

    def clean(self):
        data = super().clean()
        for key in ('name', 'category'):
            value = data.get(key)
            if value and any(ord(char) < 32 or ord(char) == 127 for char in value):
                self.add_error(key, 'Control characters are not allowed.')
            elif value:
                data[key] = ' '.join(value.split())
        if data.get('category', '').casefold() == 'microscope':
            data['category'] = 'Microscope'
        return data


def save_equipment(form, actor, equipment_id=None, expected=None, active=True):
    import uuid
    from .models import AuditEvent
    with transaction.atomic():
        with connection.cursor() as cursor:
            if equipment_id:
                cursor.execute('SELECT name, category, active FROM public.ticket_equipment WHERE equipment_id = %s FOR UPDATE', [equipment_id])
                row = cursor.fetchone()
                if not row:
                    return None
                before = dict(zip(('name', 'category', 'active'), row))
                if before != expected:
                    raise TicketConflict('This equipment changed since it was opened. Reload and try again.')
                after = {'name': form.cleaned_data['name'], 'category': form.cleaned_data['category'], 'active': active}
                if before != after:
                    cursor.execute('UPDATE public.ticket_equipment SET name = %s, category = %s, active = %s WHERE equipment_id = %s', [after['name'], after['category'], active, equipment_id])
            else:
                equipment_id = 'equipment_' + uuid.uuid4().hex
                before = {}
                after = {'name': form.cleaned_data['name'], 'category': form.cleaned_data['category'], 'active': True}
                cursor.execute('INSERT INTO public.ticket_equipment (equipment_id, name, category, active) VALUES (%s, %s, %s, %s)', [equipment_id, after['name'], after['category'], True])
            if before != after:
                AuditEvent.objects.create(actor=actor, target=actor, action='equipment_updated' if before else 'equipment_created', before={'id': equipment_id, **before}, after={'id': equipment_id, **after})
    return {'id': equipment_id, **after}


def list_tickets(params, researcher_id=None):
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
    if researcher_id is not None:
        conditions.append('ticket_id IN (SELECT ticket_id FROM public.accounts_ticketresearcherlink WHERE researcher_id = %s)')
        values.append(researcher_id)
    if statuses:
        conditions.append('status IN (' + ','.join(['%s'] * len(statuses)) + ')')
        values.extend(statuses)
    if source != 'all':
        conditions.append('source = %s')
        values.append(source)
    for key, column in (('reporter', 'reporter_name'), ('message', 'message')):
        value = params.get(key, '').strip()
        if len(value) > 200:
            raise InvalidTicketFilters
        if value:
            conditions.append(column + ' ILIKE %s')
            values.append(f'%{value}%')
    equipment = params.get('microscope', '').strip()
    if len(equipment) > 150:
        raise InvalidTicketFilters
    if equipment == '__facility__':
        conditions.append('(microscope IS NULL OR microscope = %s)')
        values.append('')
    elif equipment:
        conditions.append('(microscope = %s OR microscope = (SELECT name FROM public.ticket_equipment WHERE equipment_id = %s))')
        values.extend([equipment, equipment])
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
        cursor.execute('SELECT ticket_id, reporter_name, microscope, message, status, priority, opened_at, ticket_type, issue_type, assigned_to, resolved_at, updated_at, source, (SELECT count(*) FROM public.microscope_ticket_image i WHERE i.ticket_id = public.microscope_ticket.ticket_id) FROM public.microscope_ticket' + where + ' ORDER BY ' + sorts[sort] + ' ' + order.upper() + ' NULLS LAST, ticket_id DESC LIMIT %s OFFSET %s', values + [size, (page - 1) * size])
        rows = cursor.fetchall()
    return {'count': count, 'page': page, 'page_size': size, 'results': [
        {'ticket_id': str(row[0]), 'reporter_name': row[1], 'microscope': row[2], 'message': row[3], 'status': row[4], 'priority': row[5], 'opened_at': row[6], 'ticket_type': row[7], 'issue_type': row[8], 'assigned_to': row[9], 'resolved_at': row[10], 'updated_at': row[11], 'source': row[12], 'image_count': row[13]} for row in rows
    ]}


def ticket_summary(researcher_id=None):
    with connection.cursor() as cursor:
        restriction = ' WHERE ticket_id IN (SELECT ticket_id FROM public.accounts_ticketresearcherlink WHERE researcher_id = %s)' if researcher_id is not None else ''
        cursor.execute('''
            WITH scoped AS (SELECT * FROM public.microscope_ticket''' + restriction + '''),
            clock AS (SELECT now() AS current_time, now() - interval '30 days' AS cutoff, now() - interval '60 days' AS earlier),
            historical AS (
                SELECT t.*, COALESCE(h.new_status, CASE WHEN t.updated_at <= c.cutoff THEN t.status END) AS previous_status
                FROM scoped t CROSS JOIN clock c LEFT JOIN LATERAL (
                    SELECT e.new_status FROM public.microscope_ticket_event e
                    WHERE e.ticket_id = t.ticket_id AND e.occurred_at <= c.cutoff AND e.new_status IS NOT NULL
                    ORDER BY e.occurred_at DESC, e.event_id DESC LIMIT 1
                ) h ON true
            ),
            resolutions AS (
                SELECT e.ticket_id, e.occurred_at AS resolved_time FROM public.microscope_ticket_event e
                JOIN scoped t ON t.ticket_id = e.ticket_id
                WHERE e.new_status = 'RESOLVED' AND e.old_status IS DISTINCT FROM 'RESOLVED'
                UNION ALL
                SELECT t.ticket_id, t.resolved_at FROM scoped t
                WHERE t.resolved_at IS NOT NULL AND NOT EXISTS (
                    SELECT 1 FROM public.microscope_ticket_event e WHERE e.ticket_id = t.ticket_id AND e.new_status = 'RESOLVED'
                )
            )
            SELECT COUNT(*) FILTER (WHERE t.opened_at <= c.current_time),
                   COUNT(*) FILTER (WHERE t.opened_at <= c.cutoff),
                   COUNT(*) FILTER (WHERE t.status IN ('OPEN','IN_PROGRESS','WAITING')),
                   CASE WHEN COUNT(*) FILTER (WHERE t.opened_at <= c.cutoff AND t.previous_status IS NULL) > 0 THEN NULL
                        ELSE COUNT(*) FILTER (WHERE t.opened_at <= c.cutoff AND t.previous_status IN ('OPEN','IN_PROGRESS','WAITING')) END,
                   (SELECT COUNT(DISTINCT r.ticket_id) FROM resolutions r WHERE r.resolved_time > c.cutoff AND r.resolved_time <= c.current_time),
                   (SELECT COUNT(DISTINCT r.ticket_id) FROM resolutions r WHERE r.resolved_time > c.earlier AND r.resolved_time <= c.cutoff)
            FROM clock c LEFT JOIN historical t ON true GROUP BY c.cutoff, c.current_time, c.earlier
        ''', [researcher_id] if researcher_id is not None else [])
        total, previous_total, active, previous_active, resolved, previous_resolved = cursor.fetchone()
    return {'total': total, 'active': active, 'resolved': resolved,
            'changes': {'total': total - previous_total, 'active': active - previous_active if previous_active is not None else None,
                        'resolved': resolved - previous_resolved}}


def read_researcher_ticket(ticket_id, researcher_id):
    with connection.cursor() as cursor:
        cursor.execute('''SELECT t.ticket_id, t.reporter_name, t.microscope, t.message, t.ticket_type, t.status,
            t.opened_at, t.resolved_at, t.updated_at, t.created_by
            FROM public.microscope_ticket t JOIN public.accounts_ticketresearcherlink l ON l.ticket_id = t.ticket_id
            WHERE t.ticket_id = %s AND l.researcher_id = %s''', [ticket_id, researcher_id])
        row = cursor.fetchone()
        if not row:
            return None
        keys = ('ticket_id', 'reporter_name', 'microscope', 'message', 'ticket_type', 'status', 'opened_at', 'resolved_at', 'updated_at', 'created_by')
        result = dict(zip(keys, row))
        result['ticket_id'] = str(result['ticket_id'])
        result['images'] = []
        if result.pop('created_by') == f'dashboard-user:{researcher_id}':
            cursor.execute('SELECT image_id, filename FROM public.microscope_ticket_image WHERE ticket_id = %s ORDER BY image_id LIMIT 5', [ticket_id])
            result['images'] = [{'id': str(image[0]), 'filename': image[1]} for image in cursor.fetchall()]
        return result


def read_ticket(ticket_id):
    from .models import User
    if not 1 <= ticket_id <= 9223372036854775807:
        return None
    with connection.cursor() as cursor:
        cursor.execute('SELECT ticket_id, reporter_name, reporter_identifier, microscope, message, ticket_type, issue_type, priority, status, opened_at, resolved_at, resolution_note, assigned_to, version, updated_at FROM public.microscope_ticket WHERE ticket_id = %s', [ticket_id])
        row = cursor.fetchone()
        if not row:
            return None
        keys = ('ticket_id', 'reporter_name', 'reporter_identifier', 'microscope', 'message', 'ticket_type', 'issue_type', 'priority', 'status', 'opened_at', 'resolved_at', 'resolution_note', 'assigned_to', 'version', 'updated_at')
        result = dict(zip(keys, row))
        result['ticket_id'] = str(result['ticket_id'])
        cursor.execute('SELECT event_type, old_status, new_status, note, actor, occurred_at FROM public.microscope_ticket_event WHERE ticket_id = %s ORDER BY occurred_at DESC, event_id DESC LIMIT 100', [ticket_id])
        result['events'] = [dict(zip(('type', 'old_status', 'new_status', 'note', 'actor', 'occurred_at'), event)) for event in cursor.fetchall()]
        cursor.execute('SELECT image_id, filename FROM public.microscope_ticket_image WHERE ticket_id = %s ORDER BY image_id LIMIT 5', [ticket_id])
        result['images'] = [{'id': str(image[0]), 'filename': image[1]} for image in cursor.fetchall()]
    identities = [event['actor'] for event in result['events']] + [result['assigned_to']]
    ids = {int(value.split(':', 1)[1]) for value in identities if isinstance(value, str) and value.startswith('dashboard-user:') and value.split(':', 1)[1].isdecimal() and len(value.split(':', 1)[1]) <= 18}
    names = {person.pk: person.get_full_name() or person.username for person in User.objects.filter(pk__in=ids)}
    def display(value):
        if isinstance(value, str) and value.startswith('dashboard-user:') and value.split(':', 1)[1].isdecimal() and len(value.split(':', 1)[1]) <= 18:
            return names.get(int(value.split(':', 1)[1]), 'Former dashboard user')
        return value
    result['assigned_to_name'] = display(result['assigned_to'])
    for event in result['events']:
        event['actor'] = display(event['actor'])
    return result
