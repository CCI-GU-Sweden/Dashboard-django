from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .models import AuditEvent, TicketArchive, TicketResearcherLink, TicketStaffAssignment, TicketTag, TicketTagAssignment, User, VerifiedOmeroGroup


def live(request):
    return HttpResponse('ok', content_type='text/plain')


def ready(request):
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT 1')
    except DatabaseError:
        return HttpResponse('unavailable', status=503, content_type='text/plain')
    return HttpResponse('ok', content_type='text/plain')


def home(request):
    return render(request, 'home.html')


def operational_access(user):
    return user.is_authenticated and user.is_active and user.role in (User.Role.STAFF, User.Role.ADMIN)


def researcher_access(user):
    return user.is_authenticated and user.is_active and user.role == User.Role.RESEARCHER


def storage_scope(user):
    from django.utils import timezone
    if operational_access(user):
        return True, None
    if user.is_authenticated and user.is_active and user.role == User.Role.RESEARCHER:
        groups = list(VerifiedOmeroGroup.objects.filter(user=user, valid_until__gte=timezone.localdate()).values_list('group_id', flat=True))
        if groups:
            return True, groups
    return False, None


@login_required
def uploads(request):
    if not operational_access(request.user):
        return HttpResponseForbidden('Staff access required.')
    return render(request, 'uploads.html')


@require_GET
def uploads_summary(request):
    if not operational_access(request.user):
        return JsonResponse({'error': 'Staff access required.'}, status=403)
    from .uploads import InvalidUploadFilters, upload_summary
    try:
        return JsonResponse(upload_summary(request.GET))
    except InvalidUploadFilters as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except DatabaseError:
        return JsonResponse({'error': 'Upload data is currently unavailable.'}, status=503)


@require_GET
def upload_scopes(request):
    if not operational_access(request.user):
        return JsonResponse({'error': 'Staff access required.'}, status=403)
    from .uploads import list_scopes
    try:
        return JsonResponse(list_scopes(), safe=False)
    except DatabaseError:
        return JsonResponse({'error': 'Upload data is currently unavailable.'}, status=503)


@login_required
def storage(request):
    allowed, _ = storage_scope(request.user)
    if not allowed:
        return HttpResponseForbidden('A verified OMERO group is required.')
    return render(request, 'storage.html')


@require_GET
def storage_filesets(request):
    allowed, group = storage_scope(request.user)
    if not allowed:
        return JsonResponse({'error': 'A verified OMERO group is required.'}, status=403)
    from .storage import InvalidStorageFilters, list_filesets
    try:
        return JsonResponse(list_filesets(request.GET, allowed_group=group))
    except InvalidStorageFilters:
        return JsonResponse({'error': 'Invalid fileset filters.'}, status=400)
    except DatabaseError:
        return JsonResponse({'error': 'Storage data is currently unavailable.'}, status=503)


@require_GET
def storage_groups(request):
    allowed, group = storage_scope(request.user)
    if not allowed:
        return JsonResponse({'error': 'A verified OMERO group is required.'}, status=403)
    from .storage import list_groups
    try:
        return JsonResponse({'groups': list_groups(group)})
    except DatabaseError:
        return JsonResponse({'error': 'Storage data is currently unavailable.'}, status=503)


@require_GET
def fileset_detail(request, fileset_id):
    import json
    allowed, group = storage_scope(request.user)
    if not allowed:
        return JsonResponse({'error': 'A verified OMERO group is required.'}, status=403)
    if not 1 <= fileset_id <= 9223372036854775807:
        return JsonResponse({'error': 'Fileset not found.'}, status=404)
    try:
        with connection.cursor() as cursor:
            cursor.execute('''SELECT first_seen_at, last_seen_at, uncontained_image_count,
                missing_since_at, missing_runs, deleted_at,
                COALESCE((SELECT jsonb_agg(entry.value ->> 'name' ORDER BY entry.ordinal)
                    FROM jsonb_array_elements(CASE WHEN jsonb_typeof(source_files) = 'array' THEN source_files ELSE '[]'::jsonb END) WITH ORDINALITY AS entry(value, ordinal)), '[]'::jsonb), locations
                FROM public.omero_fileset WHERE fileset_id = %s''' + (' AND group_id = ANY(%s)' if group is not None else ''), [fileset_id] + ([group] if group is not None else []))
            row = cursor.fetchone()
        if not row:
            return JsonResponse({'error': 'Fileset not found.'}, status=404)
        def array(value):
            if isinstance(value, str):
                try:
                    value = json.loads(value)
                except ValueError:
                    return []
            return value if isinstance(value, list) else []
        result = dict(zip(('first_seen_at', 'last_seen_at', 'uncontained_image_count', 'missing_since_at', 'missing_runs', 'deleted_at'), row[:6]))
        result['source_file_names'] = [name for name in array(row[6]) if isinstance(name, str)]
        keys = ('project_id', 'project_name', 'dataset_id', 'dataset_name')
        result['locations'] = [{key: location.get(key) for key in keys} for location in array(row[7]) if isinstance(location, dict)]
        return JsonResponse(result)
    except DatabaseError:
        return JsonResponse({'error': 'Fileset details are currently unavailable.'}, status=503)


@require_GET
def storage_history(request):
    allowed, group = storage_scope(request.user)
    if not allowed:
        return JsonResponse({'error': 'A verified OMERO group is required.'}, status=403)
    from .storage import history, InvalidStorageFilters
    try:
        return JsonResponse(history(request.GET, group, is_dashboard_admin(request.user)))
    except InvalidStorageFilters:
        return JsonResponse({'error': 'Invalid history filters.'}, status=400)
    except DatabaseError:
        return JsonResponse({'error': 'Storage history is currently unavailable.'}, status=503)


@require_GET
def storage_overview(request):
    if not operational_access(request.user):
        return JsonResponse({'error': 'Staff access required.'}, status=403)
    from .storage import snapshot_overview
    try:
        return JsonResponse(snapshot_overview(is_dashboard_admin(request.user)))
    except DatabaseError:
        return JsonResponse({'error': 'Storage summary is currently unavailable.'}, status=503)


@require_GET
def storage_overview_card(request):
    allowed, group = storage_scope(request.user)
    if not allowed:
        return JsonResponse({'error': 'A verified OMERO group is required.'}, status=403)
    from .storage import overview_card
    try:
        return JsonResponse(overview_card(allowed_group=group, include_billable=operational_access(request.user)))
    except DatabaseError:
        return JsonResponse({'error': 'Storage summary is currently unavailable.'}, status=503)


@require_GET
def storage_admin_data(request, kind):
    if not is_dashboard_admin(request.user):
        return JsonResponse({'error': 'Administrator access required.'}, status=403)
    if kind not in ('policies', 'health'):
        return JsonResponse({'error': 'Not found.'}, status=404)
    from .storage import admin_table
    try:
        return JsonResponse({'rows': admin_table(kind)})
    except DatabaseError:
        return JsonResponse({'error': 'Storage data is currently unavailable.'}, status=503)


@require_GET
def storage_email_draft(request, group_id):
    if not is_dashboard_admin(request.user):
        return JsonResponse({'error': 'Administrator access required.'}, status=403)
    if not 1 <= group_id <= 9223372036854775807:
        return JsonResponse({'error': 'Group not found.'}, status=404)
    from .storage import email_draft
    try:
        result = email_draft(group_id)
        if not result:
            return JsonResponse({'error': 'No storage snapshot exists for this group.'}, status=404)
        if not result['policy_type']:
            return JsonResponse({'error': 'No storage policy applies to this snapshot.'}, status=409)
        return JsonResponse(result)
    except DatabaseError:
        return JsonResponse({'error': 'Email draft is currently unavailable.'}, status=503)


@require_POST
def create_storage_policy(request):
    import json
    import re
    from datetime import date, timedelta
    from django.utils import timezone
    if not is_dashboard_admin(request.user):
        return JsonResponse({'error': 'Administrator access required.'}, status=403)
    try:
        data = json.loads(request.body)
        group = str(data['group_id'])
        policy = data['policy_type']
        effective = date.fromisoformat(data['valid_from'])
        billing_grace = str(data['billing_grace_days'])
        grace = str(data.get('grace_days', ''))
        rate = str(data.get('rate_ore_per_gb_day', ''))
        notes = data.get('notes', '').strip()
        if (not group.isdecimal() or not 1 <= int(group) <= 9223372036854775807 or policy not in ('TEMPORARY', 'AGREEMENT', 'CORE')
            or effective < timezone.localdate() or not billing_grace.isdecimal() or int(billing_grace) > 3650 or len(notes) > 2000
            or (policy == 'TEMPORARY' and (not grace.isdecimal() or int(grace) > 36500))
            or (policy != 'CORE' and not re.fullmatch(r'\d{1,8}(?:\.\d{1,4})?', rate))):
            raise ValueError
        grace = int(grace) if policy == 'TEMPORARY' else (0 if policy == 'AGREEMENT' else None)
        rate = '0' if policy == 'CORE' else rate
    except (ValueError, KeyError, TypeError, AttributeError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid policy values or effective date.'}, status=400)
    try:
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('SELECT pg_advisory_xact_lock(%s)', [int(group)])
                cursor.execute('SELECT policy_id, group_name, valid_from, valid_until FROM public.storage_policy WHERE group_id = %s ORDER BY valid_from FOR UPDATE', [int(group)])
                rows = cursor.fetchall()
                if not rows:
                    return JsonResponse({'error': 'No policy history exists for this group.'}, status=404)
                if any(row[2] == effective for row in rows):
                    return JsonResponse({'error': 'A policy already starts on this date.'}, status=409)
                predecessor = next((row for row in reversed(rows) if row[2] < effective), None)
                successor = next((row for row in rows if row[2] > effective), None)
                if predecessor:
                    cursor.execute('UPDATE public.storage_policy SET valid_until = %s, updated_at = now() WHERE policy_id = %s', [effective - timedelta(days=1), predecessor[0]])
                cursor.execute('''INSERT INTO public.storage_policy (group_id, group_name, policy_type, grace_days, billing_grace_days, rate_ore_per_gb_day, valid_from, valid_until, notes)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) RETURNING policy_id''', [int(group), rows[-1][1], policy, grace, int(billing_grace), rate, effective, successor[2] - timedelta(days=1) if successor else None, notes or None])
                policy_id = cursor.fetchone()[0]
            AuditEvent.objects.create(actor=request.user, target=request.user, action='storage_policy_created', before={'previous_policy_id': predecessor[0] if predecessor else None, 'previous_valid_until': predecessor[3].isoformat() if predecessor and predecessor[3] else None}, after={'policy_id': policy_id, 'group_id': int(group), 'policy_type': policy, 'valid_from': effective.isoformat(), 'grace_days': grace, 'billing_grace_days': int(billing_grace), 'rate': rate, 'notes': notes})
        return JsonResponse({'policy_id': policy_id}, status=201)
    except DatabaseError:
        return JsonResponse({'error': 'Unable to save storage policy.'}, status=503)


@login_required
def billing(request):
    if not is_dashboard_admin(request.user):
        return HttpResponseForbidden('Administrator access required.')
    return render(request, 'billing.html')


@require_GET
def billing_summary(request):
    researcher = researcher_access(request.user)
    if not is_dashboard_admin(request.user) and not researcher:
        return JsonResponse({'error': 'Administrator access required.'}, status=403)
    allowed, groups = storage_scope(request.user)
    if not allowed:
        return JsonResponse({'error': 'A verified OMERO group is required.'}, status=403)
    from .storage import InvalidStorageFilters, list_billing
    try:
        return JsonResponse(list_billing(request.GET, allowed_groups=groups))
    except InvalidStorageFilters:
        return JsonResponse({'error': 'Invalid billing date range.'}, status=400)
    except DatabaseError:
        return JsonResponse({'error': 'Billing data is currently unavailable.'}, status=503)


@login_required
def tickets(request):
    if researcher_access(request.user):
        return render(request, 'researcher_tickets.html')
    if not operational_access(request.user):
        return HttpResponseForbidden('Staff access required.')
    return render(request, 'tickets.html')


def ticket_multipart_data(request):
    from .tickets import InvalidTicketFilters, validate_images
    if set(request.FILES) - {'images'}:
        raise InvalidTicketFilters('Only image attachments are allowed.')
    data = request.POST.copy()
    data.pop('csrfmiddlewaretoken', None)
    if 'images' in data:
        if any(value for value in data.getlist('images')):
            raise InvalidTicketFilters('Images must be uploaded as files.')
        data.pop('images')
    return data.dict(), validate_images(request.FILES.getlist('images'))


def ticket_form_error(form):
    labels = {'reporter_name': 'Reporter name', 'reporter_identifier': 'Contact email',
              'microscope': 'Equipment', 'message': 'Message', 'ticket_type': 'Ticket type',
              'issue_type': 'Issue type', 'priority': 'Priority', 'source_event_id': 'Submission',
              'version': 'Ticket version', 'status': 'Status', 'assigned_to': 'Assigned staff',
              'change_note': 'Progress update', 'resolution_note': 'Closing note', 'tags': 'Tags'}
    fields = form.errors.get_json_data()
    messages = [f"{labels.get(key, 'Ticket')}: {entry['message']}" for key, errors in fields.items() for entry in errors]
    return JsonResponse({'error': ' '.join(messages) or 'Check the ticket fields.', 'fields': fields}, status=400)


@require_http_methods(['GET', 'POST'])
def ticket_inventory(request):
    researcher = researcher_access(request.user)
    if not operational_access(request.user) and not researcher:
        return JsonResponse({'error': 'Staff access required.'}, status=403)
    if researcher and request.method == 'POST' and not request.user.can_create_tickets:
        return JsonResponse({'error': 'Ticket creation is not enabled for this account.'}, status=403)
    from .tickets import InvalidTicketFilters, TicketConflict, TicketCreateForm, create_ticket, list_tickets
    try:
        if request.method == 'POST':
            import json
            images = []
            if request.content_type == 'multipart/form-data':
                data, images = ticket_multipart_data(request)
            else:
                try:
                    data = json.loads(request.body)
                except (ValueError, UnicodeDecodeError):
                    return JsonResponse({'error': 'Invalid ticket data.'}, status=400)
            allowed = set(TicketCreateForm.base_fields)
            if not isinstance(data, dict) or set(data) - allowed:
                return JsonResponse({'error': 'The ticket form contains unexpected fields. Refresh the page and try again.'}, status=400)
            if researcher and data.get('ticket_type') not in ('USER_REQUEST', 'USER_REPORT'):
                return JsonResponse({'error': 'Choose a researcher ticket type.'}, status=400)
            form = TicketCreateForm(data)
            if not form.is_valid():
                return ticket_form_error(form)
            result, created = create_ticket(form, request.user, images)
            return JsonResponse(result, status=201 if created else 200)
        result = list_tickets(request.GET, researcher_id=request.user.pk if researcher else None)
        if researcher:
            fields = ('ticket_id', 'microscope', 'message', 'status', 'opened_at', 'updated_at', 'resolved_at', 'ticket_type', 'tags')
            result['results'] = [{key: item[key] for key in fields} for item in result['results']]
        return JsonResponse(result)
    except InvalidTicketFilters as exc:
        if request.method == 'POST':
            return JsonResponse({'error': str(exc) or 'Invalid ticket data.'}, status=400)
        return JsonResponse({'error': 'Invalid ticket filters.'}, status=400)
    except TicketConflict as exc:
        return JsonResponse({'error': str(exc)}, status=409)
    except DatabaseError:
        return JsonResponse({'error': 'Tickets are currently unavailable.'}, status=503)


@require_http_methods(['GET', 'POST', 'DELETE'])
def ticket_tags(request, tag_id=None):
    import json
    if not operational_access(request.user) and not researcher_access(request.user):
        return JsonResponse({'error': 'Access required.'}, status=403)
    if request.method == 'GET' and tag_id is None:
        return JsonResponse({'tags': [{'id': str(tag.pk), 'name': tag.name} for tag in TicketTag.objects.all()]})
    if request.method == 'POST' and tag_id is None and operational_access(request.user):
        try:
            payload = json.loads(request.body)
            name = payload.get('name') if isinstance(payload, dict) and set(payload) == {'name'} else None
            if not isinstance(name, str):
                raise ValueError
            name = ' '.join(name.split())
            if not name or len(name) > 60 or any(ord(c) < 32 or ord(c) == 127 for c in name):
                raise ValueError
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({'error': 'Enter a tag name of up to 60 characters.'}, status=400)
        try:
            with transaction.atomic():
                tag = TicketTag.objects.create(name=name)
                AuditEvent.objects.create(actor=request.user, target=request.user, action='ticket_tag_created', after={'tag_id': str(tag.pk), 'name': name})
            return JsonResponse({'id': str(tag.pk), 'name': name}, status=201)
        except IntegrityError:
            return JsonResponse({'error': 'A tag with this name already exists.'}, status=409)
        except DatabaseError:
            return JsonResponse({'error': 'Tags are currently unavailable.'}, status=503)
    if request.method == 'DELETE' and tag_id is not None:
        if not is_dashboard_admin(request.user):
            return JsonResponse({'error': 'Administrator access required.'}, status=403)
        try:
            with transaction.atomic():
                tag = TicketTag.objects.select_for_update().filter(pk=tag_id).first()
                if not tag:
                    return JsonResponse({'error': 'Tag not found.'}, status=404)
                name, count = tag.name, tag.assignments.count()
                tag.delete()
                AuditEvent.objects.create(actor=request.user, target=request.user, action='ticket_tag_deleted', before={'tag_id': str(tag_id), 'name': name, 'tickets': count})
            return JsonResponse({'ok': True})
        except DatabaseError:
            return JsonResponse({'error': 'Tags are currently unavailable.'}, status=503)
    return JsonResponse({'error': 'Staff access required.'}, status=403)


@require_http_methods(['GET', 'PATCH'])
def ticket_tag_assignments(request, ticket_id):
    import json
    from .tickets import InvalidTicketFilters, parse_ticket_tags
    if not operational_access(request.user):
        return JsonResponse({'error': 'Staff access required.'}, status=403)
    if not 1 <= ticket_id <= 9223372036854775807:
        return JsonResponse({'error': 'Ticket not found.'}, status=404)
    try:
        if request.method == 'GET':
            if TicketArchive.objects.filter(ticket_id=ticket_id).exists():
                return JsonResponse({'error': 'Ticket not found.'}, status=404)
            return JsonResponse({'tags': [{'id': str(a.tag_id), 'name': a.tag.name} for a in TicketTagAssignment.objects.filter(ticket_id=ticket_id).select_related('tag').order_by('tag__name')]})
        payload = json.loads(request.body)
        if not isinstance(payload, dict) or set(payload) != {'tags', 'expected'}:
            raise ValueError
        ids = parse_ticket_tags(json.dumps(payload['tags']))
        expected = parse_ticket_tags(json.dumps(payload['expected']))
        with transaction.atomic():
            if not lock_ticket_for_archive(ticket_id) or TicketArchive.objects.filter(ticket_id=ticket_id).exists():
                return JsonResponse({'error': 'Ticket not found.'}, status=404)
            current = sorted(TicketTagAssignment.objects.filter(ticket_id=ticket_id).values_list('tag_id', flat=True))
            if current != expected:
                return JsonResponse({'error': 'Tags changed. Reload the ticket and try again.'}, status=409)
            if len(list(TicketTag.objects.select_for_update().filter(pk__in=ids))) != len(ids):
                return JsonResponse({'error': 'A selected tag no longer exists.'}, status=409)
            if current != ids:
                TicketTagAssignment.objects.filter(ticket_id=ticket_id).delete()
                TicketTagAssignment.objects.bulk_create([TicketTagAssignment(ticket_id=ticket_id, tag_id=tag_id) for tag_id in ids])
                AuditEvent.objects.create(actor=request.user, target=request.user, action='ticket_tags_changed', before={'ticket_id': str(ticket_id), 'tags': current}, after={'tags': ids})
        return JsonResponse({'tags': [str(tag_id) for tag_id in ids]})
    except (ValueError, UnicodeDecodeError, InvalidTicketFilters):
        return JsonResponse({'error': 'Select up to 20 valid tags.'}, status=400)
    except DatabaseError:
        return JsonResponse({'error': 'Ticket tags are currently unavailable.'}, status=503)


@require_GET
def ticket_equipment(request):
    if not operational_access(request.user) and not researcher_access(request.user):
        return JsonResponse({'error': 'Staff access required.'}, status=403)
    from .tickets import list_equipment
    try:
        return JsonResponse({'equipment': list_equipment(include_inactive=operational_access(request.user))})
    except DatabaseError:
        return JsonResponse({'error': 'Equipment is currently unavailable.'}, status=503)


@require_http_methods(['GET', 'POST', 'PATCH'])
def manage_ticket_equipment(request, equipment_id=None):
    import json
    import re
    from .tickets import EquipmentForm, TicketConflict, list_equipment, save_equipment
    if not is_dashboard_admin(request.user):
        return JsonResponse({'error': 'Administrator access required.'}, status=403)
    if (request.method == 'PATCH') != (equipment_id is not None):
        return JsonResponse({'error': 'Invalid equipment request.'}, status=400)
    if equipment_id and not re.fullmatch(r'[a-z][a-z0-9_]{0,99}', equipment_id):
        return JsonResponse({'error': 'Invalid equipment ID.'}, status=400)
    try:
        if request.method == 'GET':
            return JsonResponse({'equipment': list_equipment(include_inactive=True)})
        try:
            payload = json.loads(request.body)
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({'error': 'Invalid equipment data.'}, status=400)
        allowed = {'name', 'category'} if request.method == 'POST' else {'name', 'category', 'active', 'expected'}
        if not isinstance(payload, dict) or set(payload) != allowed:
            return JsonResponse({'error': 'Invalid equipment data.'}, status=400)
        if request.method == 'PATCH':
            expected = payload['expected']
            if (not isinstance(payload['active'], bool) or not isinstance(expected, dict)
                    or set(expected) != {'name', 'category', 'active'} or not isinstance(expected['name'], str)
                    or not isinstance(expected['category'], str) or not isinstance(expected['active'], bool)):
                return JsonResponse({'error': 'Invalid equipment data.'}, status=400)
        form = EquipmentForm(payload)
        if not form.is_valid():
            return JsonResponse({'error': 'Enter a valid equipment name and category.'}, status=400)
        result = save_equipment(form, request.user, equipment_id, payload.get('expected'), payload.get('active', True))
        if result is None:
            return JsonResponse({'error': 'Equipment not found.'}, status=404)
        return JsonResponse(result, status=201 if request.method == 'POST' else 200)
    except TicketConflict as exc:
        return JsonResponse({'error': str(exc)}, status=409)
    except IntegrityError:
        return JsonResponse({'error': 'Equipment with this name already exists, including inactive equipment.'}, status=409)
    except DatabaseError:
        return JsonResponse({'error': 'Equipment is currently unavailable.'}, status=503)


@require_GET
def ticket_staff(request):
    if not operational_access(request.user):
        return JsonResponse({'error': 'Staff access required.'}, status=403)
    staff = User.objects.filter(is_active=True, role__in=(User.Role.STAFF, User.Role.ADMIN)).order_by('first_name', 'last_name', 'username')
    return JsonResponse({'staff': [{'id': str(person.pk), 'name': person.get_full_name() or person.username} for person in staff]})


@require_GET
def ticket_researchers(request):
    if not operational_access(request.user):
        return JsonResponse({'error': 'Staff access required.'}, status=403)
    users = User.objects.filter(is_active=True, role=User.Role.RESEARCHER).prefetch_related('socialaccount_set').order_by('first_name', 'last_name', 'username')
    return JsonResponse({'researchers': [{'id': str(person.pk), 'name': person.get_full_name() or person.username,
        'orcid': next((identity.uid for identity in person.socialaccount_set.all() if identity.provider == 'orcid'), '')} for person in users]})


@require_http_methods(['GET', 'PATCH'])
def ticket_researcher_link(request, ticket_id):
    import json
    if not operational_access(request.user):
        return JsonResponse({'error': 'Staff access required.'}, status=403)
    if not 1 <= ticket_id <= 9223372036854775807:
        return JsonResponse({'error': 'Ticket not found.'}, status=404)
    try:
        if TicketArchive.objects.filter(ticket_id=ticket_id).exists():
            return JsonResponse({'error': 'Ticket not found.'}, status=404)
        if request.method == 'GET':
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1 FROM public.microscope_ticket WHERE ticket_id = %s', [ticket_id])
                if not cursor.fetchone():
                    return JsonResponse({'error': 'Ticket not found.'}, status=404)
            link = TicketResearcherLink.objects.filter(ticket_id=ticket_id).first()
            return JsonResponse({'researcher_id': str(link.researcher_id) if link else None})
        try:
            payload = json.loads(request.body)
        except (ValueError, UnicodeDecodeError):
            return JsonResponse({'error': 'Invalid researcher link.'}, status=400)
        if not isinstance(payload, dict) or set(payload) != {'researcher_id', 'expected_researcher_id'}:
            return JsonResponse({'error': 'Invalid researcher link.'}, status=400)
        def valid_id(value):
            return value is None or (isinstance(value, str) and value.isdecimal() and len(value) <= 19 and 1 <= int(value) <= 9223372036854775807)
        chosen, expected = payload['researcher_id'], payload['expected_researcher_id']
        if not valid_id(chosen) or not valid_id(expected):
            return JsonResponse({'error': 'Invalid researcher link.'}, status=400)
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('SELECT ticket_id FROM public.microscope_ticket WHERE ticket_id = %s FOR UPDATE', [ticket_id])
                if not cursor.fetchone():
                    return JsonResponse({'error': 'Ticket not found.'}, status=404)
            if TicketArchive.objects.filter(ticket_id=ticket_id).exists():
                return JsonResponse({'error': 'Ticket is archived.'}, status=409)
            existing = TicketResearcherLink.objects.filter(ticket_id=ticket_id).first()
            previous = str(existing.researcher_id) if existing else None
            if previous != expected:
                return JsonResponse({'error': 'This ticket link changed. Reload its details before saving.'}, status=409)
            target = None
            if chosen:
                target = User.objects.select_for_update().filter(pk=int(chosen), is_active=True, role=User.Role.RESEARCHER).first()
                if not target:
                    return JsonResponse({'error': 'Select an active researcher account.'}, status=400)
                TicketResearcherLink.objects.update_or_create(ticket_id=ticket_id, defaults={'researcher': target})
            elif existing:
                existing.delete()
            if previous != chosen:
                AuditEvent.objects.create(actor=request.user, target=target or request.user, action='ticket_researcher_linked', before={'ticket_id': str(ticket_id), 'researcher_id': previous}, after={'ticket_id': str(ticket_id), 'researcher_id': chosen})
        return JsonResponse({'researcher_id': chosen})
    except DatabaseError:
        return JsonResponse({'error': 'Ticket link is currently unavailable.'}, status=503)


@require_GET
def ticket_summary(request):
    researcher = researcher_access(request.user)
    if not operational_access(request.user) and not researcher:
        return JsonResponse({'error': 'Staff access required.'}, status=403)
    from .tickets import ticket_summary as get_summary
    try:
        return JsonResponse(get_summary(researcher_id=request.user.pk if researcher else None))
    except DatabaseError:
        return JsonResponse({'error': 'Tickets are currently unavailable.'}, status=503)


@login_required
def ticket_detail(request, ticket_id):
    if not operational_access(request.user):
        return HttpResponseForbidden('Staff access required.')
    return render(request, 'ticket_detail.html', {'ticket_id': ticket_id})


@require_http_methods(['GET', 'PATCH', 'POST'])
def ticket_detail_data(request, ticket_id):
    if researcher_access(request.user) and request.method == 'GET':
        from .tickets import read_researcher_ticket
        if not 1 <= ticket_id <= 9223372036854775807:
            return JsonResponse({'error': 'Ticket not found.'}, status=404)
        try:
            result = read_researcher_ticket(ticket_id, request.user.pk)
            return JsonResponse(result) if result else JsonResponse({'error': 'Ticket not found.'}, status=404)
        except DatabaseError:
            return JsonResponse({'error': 'Ticket data is currently unavailable.'}, status=503)
    if not operational_access(request.user):
        return JsonResponse({'error': 'Staff access required.'}, status=403)
    from .tickets import InvalidTicketFilters, TicketConflict, TicketUpdateForm, read_ticket, update_ticket
    try:
        if request.method == 'GET' and not is_dashboard_admin(request.user) and TicketArchive.objects.filter(ticket_id=ticket_id).exists():
            return JsonResponse({'error': 'Ticket not found.'}, status=404)
        if request.method in ('PATCH', 'POST'):
            import json
            images = []
            if request.method == 'POST' and request.content_type == 'multipart/form-data':
                payload, images = ticket_multipart_data(request)
            else:
                try:
                    payload = json.loads(request.body)
                except (ValueError, UnicodeDecodeError):
                    return JsonResponse({'error': 'Invalid ticket data.'}, status=400)
            if not isinstance(payload, dict) or set(payload) - set(TicketUpdateForm.base_fields):
                return JsonResponse({'error': 'The ticket form contains unexpected fields. Refresh the page and try again.'}, status=400)
            form = TicketUpdateForm(payload)
            if not form.is_valid():
                return ticket_form_error(form)
            data = update_ticket(ticket_id, form, request.user, images)
        else:
            data = read_ticket(ticket_id)
        return JsonResponse(data) if data else JsonResponse({'error': 'Ticket not found.'}, status=404)
    except InvalidTicketFilters as exc:
        return JsonResponse({'error': str(exc) or 'Invalid ticket data.'}, status=400)
    except TicketConflict as exc:
        return JsonResponse({'error': str(exc)}, status=409)
    except DatabaseError:
        return JsonResponse({'error': 'Ticket data is currently unavailable.'}, status=503)


@require_GET
def ticket_image(request, ticket_id, image_id):
    researcher = researcher_access(request.user)
    if not operational_access(request.user) and not researcher:
        return HttpResponseForbidden('Staff access required.')
    if not 1 <= ticket_id <= 9223372036854775807 or not 1 <= image_id <= 9223372036854775807:
        return HttpResponse(status=404)
    try:
        if not is_dashboard_admin(request.user) and TicketArchive.objects.filter(ticket_id=ticket_id).exists():
            return HttpResponse(status=404)
        with connection.cursor() as cursor:
            query = 'SELECT image_data, extension FROM public.microscope_ticket_image WHERE ticket_id = %s AND image_id = %s'
            values = [ticket_id, image_id]
            if researcher:
                query += ''' AND EXISTS (SELECT 1 FROM public.microscope_ticket t JOIN public.accounts_ticketresearcherlink l ON l.ticket_id = t.ticket_id
                    WHERE t.ticket_id = %s AND l.researcher_id = %s AND t.created_by = %s)'''
                values += [ticket_id, request.user.pk, f'dashboard-user:{request.user.pk}']
            cursor.execute(query, values)
            row = cursor.fetchone()
    except DatabaseError:
        return HttpResponse('Image unavailable.', status=503)
    if not row or row[1] not in ('png', 'jpg', 'jpeg'):
        return HttpResponse(status=404)
    response = HttpResponse(bytes(row[0]), content_type='image/png' if row[1] == 'png' else 'image/jpeg')
    response['X-Content-Type-Options'] = 'nosniff'
    response['Content-Disposition'] = f'inline; filename="ticket-image-{image_id}.{row[1]}"'
    return response


@require_POST
def ticket_admin_edit(request, ticket_id):
    import json
    from .tickets import InvalidTicketFilters, TicketAdminEditForm, TicketConflict, admin_edit_ticket
    if not is_dashboard_admin(request.user):
        return JsonResponse({'error': 'Administrator access required.'}, status=403)
    if not 1 <= ticket_id <= 9223372036854775807:
        return JsonResponse({'error': 'Ticket not found.'}, status=404)
    try:
        payload = json.loads(request.body)
        if not isinstance(payload, dict) or set(payload) != set(TicketAdminEditForm.base_fields):
            return JsonResponse({'error': 'Invalid ticket details.'}, status=400)
        form = TicketAdminEditForm(payload)
        if not form.is_valid():
            return ticket_form_error(form)
        result = admin_edit_ticket(ticket_id, form, request.user)
        return JsonResponse(result) if result else JsonResponse({'error': 'Ticket not found.'}, status=404)
    except TicketConflict as exc:
        return JsonResponse({'error': str(exc)}, status=409)
    except InvalidTicketFilters as exc:
        return JsonResponse({'error': str(exc)}, status=400)
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid ticket details.'}, status=400)
    except DatabaseError:
        return JsonResponse({'error': 'Ticket data is currently unavailable.'}, status=503)


@require_POST
def ticket_admin_remove_image(request, ticket_id, image_id):
    import json
    if not is_dashboard_admin(request.user):
        return JsonResponse({'error': 'Administrator access required.'}, status=403)
    if not 1 <= ticket_id <= 9223372036854775807 or not 1 <= image_id <= 9223372036854775807:
        return JsonResponse({'error': 'Image not found.'}, status=404)
    try:
        payload = json.loads(request.body)
        version = payload.get('version') if isinstance(payload, dict) and set(payload) == {'version'} else None
        if not isinstance(version, int) or isinstance(version, bool) or not 1 <= version <= 2147483647:
            return JsonResponse({'error': 'Invalid ticket version.'}, status=400)
        with transaction.atomic():
            with connection.cursor() as cursor:
                cursor.execute('SELECT status, version FROM public.microscope_ticket WHERE ticket_id = %s FOR UPDATE', [ticket_id])
                ticket = cursor.fetchone()
                if not ticket or TicketArchive.objects.filter(ticket_id=ticket_id).exists():
                    return JsonResponse({'error': 'Ticket not found.'}, status=404)
                if ticket[1] != version:
                    return JsonResponse({'error': 'This ticket changed. Reload before removing an image.'}, status=409)
                cursor.execute('SELECT filename FROM public.microscope_ticket_image WHERE ticket_id = %s AND image_id = %s', [ticket_id, image_id])
                image = cursor.fetchone()
                if not image:
                    return JsonResponse({'error': 'Image not found.'}, status=404)
                cursor.execute('SELECT public.dashboard_remove_ticket_image(%s, %s)', [ticket_id, image_id])
                cursor.execute('UPDATE public.microscope_ticket SET updated_at=now(), updated_by=%s, version=version+1 WHERE ticket_id=%s RETURNING version', [f'dashboard-user:{request.user.pk}', ticket_id])
                version = cursor.fetchone()[0]
                cursor.execute('''INSERT INTO public.microscope_ticket_event (ticket_id, event_type, old_status, new_status, note, changes, actor)
                    VALUES (%s, 'UPDATED', %s, %s, %s, %s::jsonb, %s)''',
                    [ticket_id, ticket[0], ticket[0], 'Administrator removed an image.', json.dumps({'admin_edit': {'image': {'before': image[0], 'after': None}}}), f'dashboard-user:{request.user.pk}'])
        return JsonResponse({'version': version})
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid request.'}, status=400)
    except DatabaseError:
        return JsonResponse({'error': 'Image could not be removed.'}, status=503)


@require_GET
def ticket_export(request, ticket_id):
    from io import BytesIO
    from zipfile import ZIP_DEFLATED, ZipFile
    from .tickets import read_ticket
    if not operational_access(request.user):
        return HttpResponseForbidden('Staff access required.')
    if not 1 <= ticket_id <= 9223372036854775807:
        return HttpResponse(status=404)
    try:
        if not is_dashboard_admin(request.user) and TicketArchive.objects.filter(ticket_id=ticket_id).exists():
            return HttpResponse(status=404)
        data = read_ticket(ticket_id, all_events=True)
        if not data:
            return HttpResponse(status=404)
        with connection.cursor() as cursor:
            cursor.execute('SELECT name FROM public.ticket_equipment WHERE equipment_id = %s', [data['microscope']])
            equipment_row = cursor.fetchone()
        equipment_name = equipment_row[0] if equipment_row else data['microscope']
        tags = list(TicketTagAssignment.objects.filter(ticket_id=ticket_id).order_by('tag__name').values_list('tag__name', flat=True))
        labels = {'USER_REQUEST': 'User issue', 'USER_REPORT': 'User issue', 'INTERNAL_ISSUE': 'Technical issue', 'INCIDENT': 'Incident (legacy)'}
        def shown(value):
            return str(value) if value is not None and value != '' else '—'
        lines = [f'Ticket #{ticket_id}', '', f'Reporter: {shown(data["reporter_name"])}', f'Contact: {shown(data["reporter_identifier"])}',
                 f'Equipment: {shown(equipment_name)}', f'Type: {labels.get(data["ticket_type"], shown(data["ticket_type"]))}', f'Tags: {", ".join(tags) or "—"}',
                 f'Issue type: {shown(data["issue_type"])}', f'Priority: {shown(data["priority"])}', f'Status: {shown(data["status"])}',
                 f'Assigned staff: {", ".join(person["name"] for person in data["assigned_staff"]) or shown(data["assigned_to_name"])}',
                 f'Opened: {shown(data["opened_at"])}', f'Updated: {shown(data["updated_at"])}', f'Resolved: {shown(data["resolved_at"])}',
                 '', 'Report:', shown(data['message']), '', 'Resolution:', shown(data['resolution_note']), '', 'History (newest first):']
        for event in data['events']:
            lines.append(f'\n{shown(event["occurred_at"])} · {shown(event["actor"])} · {shown(event["type"])}')
            if event['old_status'] != event['new_status']:
                lines.append(f'Status: {shown(event["old_status"])} → {shown(event["new_status"])}')
            if event['note']:
                lines.append(event['note'])
            for key, change in event.get('admin_edit', {}).items():
                lines.extend([f'{key}:', f'  Before: {shown(change.get("before"))}', f'  After: {shown(change.get("after"))}'])
        archive = BytesIO()
        with ZipFile(archive, 'w', ZIP_DEFLATED) as output:
            with connection.cursor() as cursor:
                cursor.execute('SELECT image_id, filename, extension, image_data FROM public.microscope_ticket_image WHERE ticket_id = %s ORDER BY image_id', [ticket_id])
                images = cursor.fetchall()
            lines.extend(['', 'Attachments:'])
            for image_id, filename, extension, image_data in images:
                ext = extension.lower() if extension and extension.lower() in ('png', 'jpg', 'jpeg') else 'bin'
                path = f'images/ticket-image-{image_id}.{ext}'
                lines.append(f'{filename} → {path}')
                output.writestr(path, bytes(image_data))
            if not images:
                lines.append('None')
            output.writestr('ticket.txt', '\n'.join(lines) + '\n')
        response = HttpResponse(archive.getvalue(), content_type='application/zip')
        response['Content-Disposition'] = f'attachment; filename="ticket-{ticket_id}.zip"'
        response['Cache-Control'] = 'private, no-store'
        response['X-Content-Type-Options'] = 'nosniff'
        return response
    except DatabaseError:
        return HttpResponse('Ticket export is currently unavailable.', status=503)


def is_dashboard_admin(user):
    return user.is_authenticated and user.is_active and user.role == User.Role.ADMIN


@require_GET
def archived_tickets(request):
    if not is_dashboard_admin(request.user):
        return JsonResponse({'error': 'Administrator access required.'}, status=403)
    try:
        page = int(request.GET.get('page', '1'))
        if not 1 <= page <= 1000000:
            raise ValueError
    except ValueError:
        return JsonResponse({'error': 'Invalid page.'}, status=400)
    try:
        archives = list(TicketArchive.objects.select_related('archived_by').order_by('-archived_at', '-ticket_id')[(page - 1) * 50:page * 50 + 1])
        more = len(archives) > 50
        archives = archives[:50]
        with connection.cursor() as cursor:
            cursor.execute('SELECT ticket_id, reporter_name, message, status FROM public.microscope_ticket WHERE ticket_id = ANY(%s)', [[a.ticket_id for a in archives]])
            tickets = {row[0]: row[1:] for row in cursor.fetchall()}
        results = []
        for item in archives:
            ticket = tickets.get(item.ticket_id)
            if ticket:
                results.append({'ticket_id': str(item.ticket_id), 'reporter': ticket[0], 'message': ticket[1], 'status': ticket[2], 'reason': item.reason, 'archived_at': item.archived_at, 'archived_by': item.archived_by.get_full_name() or item.archived_by.username})
        return JsonResponse({'results': results, 'page': page, 'has_next': more})
    except DatabaseError:
        return JsonResponse({'error': 'Archived tickets are currently unavailable.'}, status=503)


@require_POST
def ticket_archive_action(request, ticket_id, action):
    import json
    if not operational_access(request.user) or (action != 'archive' and not is_dashboard_admin(request.user)):
        return JsonResponse({'error': 'Administrator access required.' if action != 'archive' else 'Staff access required.'}, status=403)
    if action not in ('archive', 'restore', 'delete') or not 1 <= ticket_id <= 9223372036854775807:
        return JsonResponse({'error': 'Ticket not found.'}, status=404)
    try:
        payload = json.loads(request.body or b'{}')
    except (ValueError, UnicodeDecodeError):
        return JsonResponse({'error': 'Invalid request.'}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({'error': 'Invalid request.'}, status=400)
    reason = payload.get('reason')
    if action == 'archive' and (not isinstance(reason, str) or not reason.strip() or len(reason.strip()) > 1000):
        return JsonResponse({'error': 'Enter a reason of up to 1,000 characters.'}, status=400)
    if action == 'delete' and payload.get('confirm_ticket_id') != str(ticket_id):
        return JsonResponse({'error': 'Enter the ticket number to confirm permanent deletion.'}, status=400)
    try:
        with transaction.atomic():
            if not lock_ticket_for_archive(ticket_id):
                return JsonResponse({'error': 'Ticket not found.'}, status=404)
            archived = TicketArchive.objects.filter(ticket_id=ticket_id).first()
            if action == 'archive':
                if archived:
                    return JsonResponse({'error': 'Ticket is already archived.'}, status=409)
                reason = reason.strip()
                TicketArchive.objects.create(ticket_id=ticket_id, reason=reason, archived_by=request.user)
            else:
                if not archived:
                    return JsonResponse({'error': 'Only archived tickets can be restored or deleted.'}, status=409)
                reason = archived.reason
                if action == 'delete':
                    purge_archived_ticket(ticket_id)
                    TicketResearcherLink.objects.filter(ticket_id=ticket_id).delete()
                    TicketStaffAssignment.objects.filter(ticket_id=ticket_id).delete()
                    TicketTagAssignment.objects.filter(ticket_id=ticket_id).delete()
                archived.delete()
            AuditEvent.objects.create(actor=request.user, target=request.user, action='ticket_' + {'archive': 'archived', 'restore': 'restored', 'delete': 'deleted'}[action], before={'ticket_id': str(ticket_id)}, after={'reason': reason})
        return JsonResponse({'ok': True})
    except DatabaseError:
        return JsonResponse({'error': 'Ticket action is currently unavailable.'}, status=503)


def lock_ticket_for_archive(ticket_id):
    with connection.cursor() as cursor:
        cursor.execute('SELECT ticket_id FROM public.microscope_ticket WHERE ticket_id = %s FOR UPDATE', [ticket_id])
        return bool(cursor.fetchone())


def purge_archived_ticket(ticket_id):
    with connection.cursor() as cursor:
        cursor.execute('SELECT public.dashboard_purge_archived_ticket(%s)', [ticket_id])


@login_required
def administration(request):
    if not is_dashboard_admin(request.user):
        return HttpResponseForbidden('Administrator access required.')
    return render(request, 'administration.html', {'accounts': User.objects.prefetch_related('omero_group_memberships', 'socialaccount_set').order_by('date_joined'), 'events': AuditEvent.objects.select_related('actor', 'target').order_by('-created_at')[:100]})


@login_required
@require_POST
def update_omero_group(request, user_id):
    from datetime import date, timedelta
    from django.utils import timezone
    if not is_dashboard_admin(request.user):
        return HttpResponseForbidden('Administrator access required.')
    if 'group_id' not in request.POST:
        return HttpResponseBadRequest('Select a group or explicitly revoke group access.')
    target = get_object_or_404(User, pk=user_id)
    group_id = request.POST.get('group_id', '').strip()
    until = request.POST.get('valid_until', '')
    revoke = request.POST.get('action') == 'revoke'
    if group_id and not revoke:
        try:
            end = date.fromisoformat(until)
            today = timezone.localdate()
            if not group_id.isdecimal() or not 1 <= int(group_id) <= 9223372036854775807 or not today <= end <= today + timedelta(days=365) or request.POST.get('verified') != 'yes' or target.role != User.Role.RESEARCHER:
                raise ValueError
        except ValueError:
            return HttpResponseBadRequest('Verify a researcher group and enter a valid review date within one year.')
    with transaction.atomic():
        target = User.objects.select_for_update().get(pk=target.pk)
        if group_id and target.role != User.Role.RESEARCHER:
            return HttpResponseBadRequest('Only researchers can have a verified OMERO group.')
        if not group_id or not group_id.isdecimal() or not 1 <= int(group_id) <= 9223372036854775807:
            return HttpResponseBadRequest('Select a valid group.')
        existing = VerifiedOmeroGroup.objects.filter(user=target, group_id=int(group_id)).first()
        before = {'group_id': existing.group_id, 'valid_until': existing.valid_until.isoformat()} if existing else {}
        if not revoke:
            VerifiedOmeroGroup.objects.update_or_create(user=target, group_id=int(group_id), defaults={'valid_until': end, 'verified_by': request.user})
            after = {'group_id': int(group_id), 'valid_until': end.isoformat()}
        else:
            VerifiedOmeroGroup.objects.filter(user=target, group_id=int(group_id)).delete()
            after = {}
        AuditEvent.objects.create(actor=request.user, target=target, action='omero_group_verified', before=before, after=after)
    return redirect('administration')


@login_required
@require_POST
def update_account(request, user_id):
    if not is_dashboard_admin(request.user):
        return HttpResponseForbidden('Administrator access required.')
    role = request.POST.get('role', '')
    active = request.POST.get('active')
    ticket_permission = request.POST.get('can_create_tickets', '')
    if role not in {'', *User.Role.values} or active not in {'yes', 'no'} or ticket_permission not in {'', 'yes'}:
        return HttpResponseBadRequest('Invalid account settings.')
    with transaction.atomic():
        # Serialize concurrent attempts to remove the last admin.
        list(User.objects.select_for_update().filter(role=User.Role.ADMIN, is_active=True).order_by('pk'))
        actor = User.objects.get(pk=request.user.pk)
        if not is_dashboard_admin(actor):
            return HttpResponseForbidden('Administrator access required.')
        target = get_object_or_404(User.objects.select_for_update(), pk=user_id)
        if target.role == User.Role.ADMIN and target.is_active and (role != User.Role.ADMIN or active == 'no') and User.objects.filter(role=User.Role.ADMIN, is_active=True).count() <= 1:
            return HttpResponseBadRequest('The last active administrator cannot be removed.')
        before = {'role': target.role, 'is_active': target.is_active, 'can_create_tickets': target.can_create_tickets}
        target.role, target.is_active = role, active == 'yes'
        target.can_create_tickets = role == User.Role.RESEARCHER and ticket_permission == 'yes'
        target.save(update_fields=['role', 'is_active', 'can_create_tickets'])
        if role != User.Role.RESEARCHER or active == 'no':
            VerifiedOmeroGroup.objects.filter(user=target).delete()
        after = {'role': target.role, 'is_active': target.is_active, 'can_create_tickets': target.can_create_tickets}
        if before != after:
            AuditEvent.objects.create(actor=actor, target=target, action='account_updated', before=before, after=after)
    return redirect('administration')
