"""Shared access checks for dashboard modules."""
from .models import User


def operational_access(user):
    return user.is_authenticated and user.is_active and user.role in (User.Role.STAFF, User.Role.ADMIN)


def researcher_access(user):
    return user.is_authenticated and user.is_active and user.role == User.Role.RESEARCHER


def is_dashboard_admin(user):
    return user.is_authenticated and user.is_active and user.role == User.Role.ADMIN
