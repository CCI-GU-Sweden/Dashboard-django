from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, connection, transaction
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .models import AuditEvent, User, VerifiedOmeroGroup
from .permissions import is_dashboard_admin


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
    from dashboard.modules import can_access_module, registered_modules
    modules = [module for module in registered_modules() if can_access_module(module, request.user)]
    return render(request, 'home.html', {'dashboard_modules': modules})


@login_required
def administration(request):
    if not is_dashboard_admin(request.user):
        return HttpResponseForbidden('Administrator access required.')
    from django.conf import settings
    return render(request, 'administration.html', {'accounts': User.objects.prefetch_related('omero_group_memberships', 'socialaccount_set').order_by('date_joined'), 'events': AuditEvent.objects.select_related('actor', 'target').order_by('-created_at')[:100], 'tickets_enabled': settings.DASHBOARD_TICKETS_ENABLED})


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
        from django.conf import settings
        if settings.DASHBOARD_TICKETS_ENABLED:
            target.can_create_tickets = role == User.Role.RESEARCHER and ticket_permission == 'yes'
        elif role != User.Role.RESEARCHER:
            target.can_create_tickets = False
        target.save(update_fields=['role', 'is_active', 'can_create_tickets'])
        if role != User.Role.RESEARCHER or active == 'no':
            VerifiedOmeroGroup.objects.filter(user=target).delete()
        after = {'role': target.role, 'is_active': target.is_active, 'can_create_tickets': target.can_create_tickets}
        if before != after:
            AuditEvent.objects.create(actor=actor, target=target, action='account_updated', before=before, after=after)
    return redirect('administration')
