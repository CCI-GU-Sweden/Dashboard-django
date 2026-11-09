"""Apply migration 0004 and exercise its models inside a rolled-back transaction."""
import os, uuid
from datetime import timedelta
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dashboard.settings')
import django
django.setup()
from django.core.management import call_command
from django.db import transaction
from django.utils import timezone
from accounts.models import TicketStaffAssignment, User, VerifiedOmeroGroup

with transaction.atomic():
    call_command('migrate', 'accounts', '0004', interactive=False, verbosity=0)
    key = uuid.uuid4().hex
    admin = User.objects.create_user(username='migration-admin-' + key, role=User.Role.ADMIN)
    staff = User.objects.create_user(username='migration-staff-' + key, role=User.Role.STAFF)
    researcher = User.objects.create_user(username='migration-researcher-' + key, role=User.Role.RESEARCHER)
    for group in (9000000001, 9000000002):
        VerifiedOmeroGroup.objects.create(user=researcher, group_id=group, verified_by=admin, valid_until=timezone.localdate() + timedelta(days=1))
    for person in (admin, staff):
        TicketStaffAssignment.objects.create(ticket_id=9000000001, staff=person)
    assert VerifiedOmeroGroup.objects.filter(user=researcher).count() == 2
    assert TicketStaffAssignment.objects.filter(ticket_id=9000000001).count() == 2
    transaction.set_rollback(True)
print('Migration and multiple-group/staff model checks passed; transaction rolled back.')
