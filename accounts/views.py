from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, IntegrityError, connection, transaction
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .models import AuditEvent, TicketResearcherLink, User, VerifiedOmeroGroup


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
        group = VerifiedOmeroGroup.objects.filter(user=user, valid_until__gte=timezone.localdate()).first()
        if group:
            return True, group.group_id
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
                FROM public.omero_fileset WHERE fileset_id = %s''' + (' AND group_id = %s' if group is not None else ''), [fileset_id] + ([group] if group is not None else []))
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
    if not is_dashboard_admin(request.user):
        return JsonResponse({'error': 'Administrator access required.'}, status=403)
    from .storage import InvalidStorageFilters, list_billing
    try:
        return JsonResponse(list_billing(request.GET))
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


@require_http_methods(['GET', 'POST'])
def ticket_inventory(request):
    researcher = researcher_access(request.user)
    if not operational_access(request.user) and not researcher:
        return JsonResponse({'error': 'Staff access required.'}, status=403)
    if researcher and request.method == 'POST' and not request.user.can_create_tickets:
        return JsonResponse({'error': 'Ticket creation is not enabled for this account.'}, status=403)
    from .tickets import InvalidTicketFilters, TicketConflict, TicketCreateForm, create_ticket, list_tickets, validate_images
    try:
        if request.method == 'POST':
            import json
            images = []
            if request.content_type == 'multipart/form-data':
                if set(request.FILES) - {'images'}:
                    return JsonResponse({'error': 'Invalid ticket files.'}, status=400)
                data = request.POST.dict()
                data.pop('csrfmiddlewaretoken', None)
                images = validate_images(request.FILES.getlist('images'))
            else:
                try:
                    data = json.loads(request.body)
                except (ValueError, UnicodeDecodeError):
                    return JsonResponse({'error': 'Invalid ticket data.'}, status=400)
            allowed = set(TicketCreateForm.base_fields)
            if not isinstance(data, dict) or set(data) - allowed:
                return JsonResponse({'error': 'Invalid ticket data.'}, status=400)
            if researcher and data.get('ticket_type') not in ('USER_REQUEST', 'USER_REPORT'):
                return JsonResponse({'error': 'Choose a researcher ticket type.'}, status=400)
            form = TicketCreateForm(data)
            if not form.is_valid():
                return JsonResponse({'error': 'Check the ticket fields.', 'fields': form.errors.get_json_data()}, status=400)
            result, created = create_ticket(form, request.user, images)
            return JsonResponse(result, status=201 if created else 200)
        result = list_tickets(request.GET, researcher_id=request.user.pk if researcher else None)
        if researcher:
            fields = ('ticket_id', 'microscope', 'message', 'status', 'opened_at', 'updated_at', 'resolved_at', 'ticket_type')
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
    from .tickets import InvalidTicketFilters, TicketConflict, TicketUpdateForm, read_ticket, update_ticket, validate_images
    try:
        if request.method in ('PATCH', 'POST'):
            import json
            images = []
            if request.method == 'POST' and request.content_type == 'multipart/form-data':
                if set(request.FILES) - {'images'}:
                    return JsonResponse({'error': 'Invalid ticket files.'}, status=400)
                payload = request.POST.dict()
                payload.pop('csrfmiddlewaretoken', None)
                images = validate_images(request.FILES.getlist('images'))
            else:
                try:
                    payload = json.loads(request.body)
                except (ValueError, UnicodeDecodeError):
                    return JsonResponse({'error': 'Invalid ticket data.'}, status=400)
            if not isinstance(payload, dict) or set(payload) - set(TicketUpdateForm.base_fields):
                return JsonResponse({'error': 'Invalid ticket data.'}, status=400)
            form = TicketUpdateForm(payload)
            if not form.is_valid():
                return JsonResponse({'error': 'Check the ticket fields.', 'fields': form.errors.get_json_data()}, status=400)
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


def is_dashboard_admin(user):
    return user.is_authenticated and user.is_active and user.role == User.Role.ADMIN


@login_required
def administration(request):
    if not is_dashboard_admin(request.user):
        return HttpResponseForbidden('Administrator access required.')
    return render(request, 'administration.html', {'accounts': User.objects.select_related('verified_omero_group').prefetch_related('socialaccount_set').order_by('date_joined'), 'events': AuditEvent.objects.select_related('actor', 'target').order_by('-created_at')[:100]})


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
    if group_id:
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
        existing = VerifiedOmeroGroup.objects.filter(user=target).first()
        before = {'group_id': existing.group_id, 'valid_until': existing.valid_until.isoformat()} if existing else {}
        if group_id:
            VerifiedOmeroGroup.objects.update_or_create(user=target, defaults={'group_id': int(group_id), 'valid_until': end, 'verified_by': request.user})
            after = {'group_id': int(group_id), 'valid_until': end.isoformat()}
        else:
            VerifiedOmeroGroup.objects.filter(user=target).delete()
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
