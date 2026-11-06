from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, connection, transaction
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_GET, require_POST, require_http_methods

from .models import AuditEvent, User


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


@login_required
def storage(request):
    if not operational_access(request.user):
        return HttpResponseForbidden('Staff access required.')
    return render(request, 'storage.html')


@require_GET
def storage_filesets(request):
    if not operational_access(request.user):
        return JsonResponse({'error': 'Staff access required.'}, status=403)
    from .storage import InvalidStorageFilters, list_filesets
    try:
        return JsonResponse(list_filesets(request.GET))
    except InvalidStorageFilters:
        return JsonResponse({'error': 'Invalid fileset filters.'}, status=400)
    except DatabaseError:
        return JsonResponse({'error': 'Storage data is currently unavailable.'}, status=503)


@require_GET
def storage_groups(request):
    if not operational_access(request.user):
        return JsonResponse({'error': 'Staff access required.'}, status=403)
    from .storage import list_groups
    try:
        return JsonResponse({'groups': list_groups()})
    except DatabaseError:
        return JsonResponse({'error': 'Storage data is currently unavailable.'}, status=503)


@require_GET
def fileset_detail(request, fileset_id):
    if not operational_access(request.user):
        return JsonResponse({'error': 'Staff access required.'}, status=403)
    if not 1 <= fileset_id <= 9223372036854775807:
        return JsonResponse({'error': 'Fileset not found.'}, status=404)
    try:
        with connection.cursor() as cursor:
            cursor.execute('''SELECT first_seen_at, last_seen_at, uncontained_image_count,
                missing_since_at, missing_runs, deleted_at,
                COALESCE((SELECT jsonb_agg(entry.value ->> 'name' ORDER BY entry.ordinal)
                    FROM jsonb_array_elements(source_files) WITH ORDINALITY AS entry(value, ordinal)), '[]'::jsonb)
                FROM public.omero_fileset WHERE fileset_id = %s''', [fileset_id])
            row = cursor.fetchone()
        if not row:
            return JsonResponse({'error': 'Fileset not found.'}, status=404)
        return JsonResponse(dict(zip(('first_seen_at', 'last_seen_at', 'uncontained_image_count', 'missing_since_at', 'missing_runs', 'deleted_at', 'source_file_names'), row)))
    except DatabaseError:
        return JsonResponse({'error': 'Fileset details are currently unavailable.'}, status=503)


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
    if not operational_access(request.user):
        return HttpResponseForbidden('Staff access required.')
    return render(request, 'tickets.html')


@require_http_methods(['GET', 'POST'])
def ticket_inventory(request):
    if not operational_access(request.user):
        return JsonResponse({'error': 'Staff access required.'}, status=403)
    from .tickets import InvalidTicketFilters, TicketConflict, TicketCreateForm, create_ticket, list_tickets
    try:
        if request.method == 'POST':
            import json
            try:
                data = json.loads(request.body)
            except (ValueError, UnicodeDecodeError):
                return JsonResponse({'error': 'Invalid ticket data.'}, status=400)
            allowed = set(TicketCreateForm.base_fields)
            if not isinstance(data, dict) or set(data) - allowed:
                return JsonResponse({'error': 'Invalid ticket data.'}, status=400)
            form = TicketCreateForm(data)
            if not form.is_valid():
                return JsonResponse({'error': 'Check the ticket fields.', 'fields': form.errors.get_json_data()}, status=400)
            result, created = create_ticket(form, request.user)
            return JsonResponse(result, status=201 if created else 200)
        return JsonResponse(list_tickets(request.GET))
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
    if not operational_access(request.user):
        return JsonResponse({'error': 'Staff access required.'}, status=403)
    from .tickets import list_equipment
    try:
        return JsonResponse({'equipment': list_equipment()})
    except DatabaseError:
        return JsonResponse({'error': 'Equipment is currently unavailable.'}, status=503)


@require_GET
def ticket_summary(request):
    if not operational_access(request.user):
        return JsonResponse({'error': 'Staff access required.'}, status=403)
    from .tickets import ticket_summary as get_summary
    try:
        return JsonResponse(get_summary())
    except DatabaseError:
        return JsonResponse({'error': 'Tickets are currently unavailable.'}, status=503)


@login_required
def ticket_detail(request, ticket_id):
    if not operational_access(request.user):
        return HttpResponseForbidden('Staff access required.')
    return render(request, 'ticket_detail.html', {'ticket_id': ticket_id})


@require_http_methods(['GET', 'PATCH'])
def ticket_detail_data(request, ticket_id):
    if not operational_access(request.user):
        return JsonResponse({'error': 'Staff access required.'}, status=403)
    from .tickets import InvalidTicketFilters, TicketConflict, TicketUpdateForm, read_ticket, update_ticket
    try:
        if request.method == 'PATCH':
            import json
            try:
                payload = json.loads(request.body)
            except (ValueError, UnicodeDecodeError):
                return JsonResponse({'error': 'Invalid ticket data.'}, status=400)
            if not isinstance(payload, dict) or set(payload) - set(TicketUpdateForm.base_fields):
                return JsonResponse({'error': 'Invalid ticket data.'}, status=400)
            form = TicketUpdateForm(payload)
            if not form.is_valid():
                return JsonResponse({'error': 'Check the ticket fields.', 'fields': form.errors.get_json_data()}, status=400)
            data = update_ticket(ticket_id, form, request.user)
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
    if not operational_access(request.user):
        return HttpResponseForbidden('Staff access required.')
    if not 1 <= ticket_id <= 9223372036854775807 or not 1 <= image_id <= 9223372036854775807:
        return HttpResponse(status=404)
    try:
        with connection.cursor() as cursor:
            cursor.execute('SELECT image_data, extension FROM public.microscope_ticket_image WHERE ticket_id = %s AND image_id = %s', [ticket_id, image_id])
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
    return render(request, 'administration.html', {'accounts': User.objects.prefetch_related('socialaccount_set').order_by('date_joined'), 'events': AuditEvent.objects.select_related('actor', 'target').order_by('-created_at')[:100]})


@login_required
@require_POST
def update_account(request, user_id):
    if not is_dashboard_admin(request.user):
        return HttpResponseForbidden('Administrator access required.')
    role = request.POST.get('role', '')
    active = request.POST.get('active')
    if role not in {'', *User.Role.values} or active not in {'yes', 'no'}:
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
        before = {'role': target.role, 'is_active': target.is_active}
        target.role, target.is_active = role, active == 'yes'
        target.save(update_fields=['role', 'is_active'])
        after = {'role': target.role, 'is_active': target.is_active}
        if before != after:
            AuditEvent.objects.create(actor=actor, target=target, action='account_updated', before=before, after=after)
    return redirect('administration')
