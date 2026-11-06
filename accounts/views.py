from django.contrib.auth.decorators import login_required
from django.db import DatabaseError, connection, transaction
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

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
