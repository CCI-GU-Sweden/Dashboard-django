from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        RESEARCHER = 'researcher', 'Researcher'
        STAFF = 'staff', 'Staff'
        ADMIN = 'admin', 'Admin'

    # An empty role is pending. is_active independently controls disabling.
    role = models.CharField(max_length=16, choices=Role.choices, blank=True, default='')


class AuditEvent(models.Model):
    actor = models.ForeignKey(User, on_delete=models.PROTECT, related_name='audit_actions')
    target = models.ForeignKey(User, on_delete=models.PROTECT, related_name='audit_events')
    action = models.CharField(max_length=40)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)
