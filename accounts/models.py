from django.contrib.auth.models import AbstractUser
from django.db import models


class User(AbstractUser):
    class Role(models.TextChoices):
        RESEARCHER = 'researcher', 'Researcher'
        STAFF = 'staff', 'Staff'
        ADMIN = 'admin', 'Admin'

    # An empty role is pending. is_active independently controls disabling.
    role = models.CharField(max_length=16, choices=Role.choices, blank=True, default='')
    can_create_tickets = models.BooleanField(default=False)


class AuditEvent(models.Model):
    actor = models.ForeignKey(User, on_delete=models.PROTECT, related_name='audit_actions')
    target = models.ForeignKey(User, on_delete=models.PROTECT, related_name='audit_events')
    action = models.CharField(max_length=40)
    before = models.JSONField(default=dict)
    after = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)


class VerifiedOmeroGroup(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='omero_group_memberships')
    group_id = models.PositiveBigIntegerField()
    valid_until = models.DateField()
    verified_by = models.ForeignKey(User, on_delete=models.PROTECT, related_name='verified_omero_groups')
    verified_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [models.UniqueConstraint(fields=['user', 'group_id'], name='unique_verified_user_group')]


class TicketStaffAssignment(models.Model):
    ticket_id = models.PositiveBigIntegerField(db_index=True)
    staff = models.ForeignKey(User, on_delete=models.PROTECT, related_name='ticket_assignments')

    class Meta:
        constraints = [models.UniqueConstraint(fields=['ticket_id', 'staff'], name='unique_ticket_staff')]


class TicketResearcherLink(models.Model):
    ticket_id = models.PositiveBigIntegerField(unique=True)
    researcher = models.ForeignKey(User, on_delete=models.PROTECT, related_name='linked_tickets')
