from django.db import DatabaseError
from django.core.exceptions import PermissionDenied
from django.http import JsonResponse
from django.views.decorators.http import require_GET

from .modules import can_access_module, registered_modules


@require_GET
def module_overview(request, module_key):
    module = next((item for item in registered_modules() if item.key == module_key), None)
    if module is None:
        return JsonResponse({'error': 'Module not found.'}, status=404)
    if not can_access_module(module, request.user):
        return JsonResponse({'error': 'Access denied.'}, status=403)
    try:
        metrics = module.get_metrics(request.user)
    except PermissionDenied:
        return JsonResponse({'error': 'Access denied.'}, status=403)
    except DatabaseError:
        return JsonResponse({'error': 'Summary is currently unavailable.'}, status=503)
    return JsonResponse({'version': 1, 'module': module.key, 'metrics': metrics})
