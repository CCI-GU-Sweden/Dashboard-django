"""Version 1 interface between the dashboard core and trusted Django modules."""
from dataclasses import dataclass
import re
from typing import Callable

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.utils.module_loading import import_string


@dataclass(frozen=True)
class DashboardModule:
    key: str
    name: str
    eyebrow: str
    icon: str
    url_name: str
    urlconf: str
    can_view: Callable
    get_metrics: Callable
    contract_version: int = 1
    overview_template: str = ''
    overview_script: str = ''


def registered_modules():
    modules = []
    keys = set()
    for dotted_path in settings.DASHBOARD_MODULES:
        module = import_string(dotted_path)
        if not isinstance(module, DashboardModule) or module.contract_version != 1:
            raise ImproperlyConfigured(f'Unsupported dashboard module contract: {dotted_path}')
        if not re.fullmatch(r'[-a-zA-Z0-9_]+', module.key) or module.key in keys:
            raise ImproperlyConfigured(f'Invalid or duplicate dashboard module key: {module.key!r}')
        keys.add(module.key)
        modules.append(module)
    return modules


def can_access_module(module, user):
    return (user.is_authenticated and user.is_active and bool(user.role)
            and module.can_view(user))
