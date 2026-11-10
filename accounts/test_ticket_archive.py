import json
from unittest.mock import patch

from django.db import DatabaseError
from django.test import TestCase

from .models import AuditEvent, TicketArchive, TicketResearcherLink, TicketStaffAssignment, User


class TicketArchiveTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin', role=User.Role.ADMIN)
        self.staff = User.objects.create_user(username='staff', role=User.Role.STAFF)
        self.researcher = User.objects.create_user(username='researcher', role=User.Role.RESEARCHER)
        self.lock = patch('accounts.views.lock_ticket_for_archive', return_value=True)
        self.lock.start()
        self.addCleanup(self.lock.stop)

    def post(self, action, data):
        return self.client.post(f'/api/tickets/42/{action}/archive-action', data=json.dumps(data), content_type='application/json')

    def test_staff_archive_requires_reason_and_records_audit(self):
        self.client.force_login(self.staff)
        self.assertEqual(self.post('archive', {'reason': '  '}).status_code, 400)
        self.assertEqual(self.post('archive', {'reason': 'Duplicate'}).status_code, 200)
        archive = TicketArchive.objects.get(pk=42)
        self.assertEqual((archive.reason, archive.archived_by), ('Duplicate', self.staff))
        self.assertTrue(AuditEvent.objects.filter(actor=self.staff, action='ticket_archived').exists())
        self.assertEqual(self.post('archive', {'reason': 'Duplicate'}).status_code, 409)
        self.assertEqual(self.client.get('/api/tickets/archived').status_code, 403)
        self.assertEqual(self.client.get('/api/tickets/42').status_code, 404)
        self.assertEqual(self.client.get('/api/tickets/42/images/1').status_code, 404)

    def test_archive_controls_are_admin_only(self):
        self.client.force_login(self.staff)
        self.assertNotContains(self.client.get('/tickets/'), 'id="show-archive"')
        self.client.force_login(self.admin)
        self.assertContains(self.client.get('/tickets/'), 'id="show-archive"')

    def test_missing_ticket_cannot_be_archived(self):
        self.client.force_login(self.staff)
        with patch('accounts.views.lock_ticket_for_archive', return_value=False):
            self.assertEqual(self.post('archive', {'reason': 'Duplicate'}).status_code, 404)
        self.assertFalse(TicketArchive.objects.exists())

    def test_only_admin_can_restore_or_delete_and_delete_requires_confirmation(self):
        TicketArchive.objects.create(ticket_id=42, reason='Duplicate', archived_by=self.staff)
        self.client.force_login(self.staff)
        self.assertEqual(self.post('restore', {}).status_code, 403)
        self.assertEqual(self.post('delete', {'confirm_ticket_id': '42'}).status_code, 403)
        self.client.force_login(self.researcher)
        self.assertEqual(self.post('archive', {'reason': 'x'}).status_code, 403)
        self.assertEqual(self.post('restore', {}).status_code, 403)
        self.client.force_login(self.admin)
        self.assertEqual(self.post('delete', {}).status_code, 400)
        self.assertEqual(self.post('restore', {}).status_code, 200)
        self.assertFalse(TicketArchive.objects.filter(pk=42).exists())
        self.assertEqual(self.post('delete', {'confirm_ticket_id': '42'}).status_code, 409)
        self.assertTrue(AuditEvent.objects.filter(actor=self.admin, action='ticket_restored').exists())

    def test_delete_removes_dashboard_links_and_audits(self):
        TicketArchive.objects.create(ticket_id=42, reason='Duplicate', archived_by=self.staff)
        TicketResearcherLink.objects.create(ticket_id=42, researcher=self.researcher)
        TicketStaffAssignment.objects.create(ticket_id=42, staff=self.staff)
        self.client.force_login(self.admin)
        with patch('accounts.views.purge_archived_ticket') as purge:
            self.assertEqual(self.post('delete', {'confirm_ticket_id': '42'}).status_code, 200)
            purge.assert_called_once_with(42)
        self.assertFalse(TicketArchive.objects.exists())
        self.assertFalse(TicketResearcherLink.objects.exists())
        self.assertFalse(TicketStaffAssignment.objects.exists())
        self.assertTrue(AuditEvent.objects.filter(action='ticket_deleted').exists())

    def test_failed_delete_preserves_archive_and_links(self):
        TicketArchive.objects.create(ticket_id=42, reason='Duplicate', archived_by=self.staff)
        TicketResearcherLink.objects.create(ticket_id=42, researcher=self.researcher)
        self.client.force_login(self.admin)
        with patch('accounts.views.purge_archived_ticket', side_effect=DatabaseError):
            self.assertEqual(self.post('delete', {'confirm_ticket_id': '42'}).status_code, 503)
        self.assertTrue(TicketArchive.objects.filter(pk=42).exists())
        self.assertTrue(TicketResearcherLink.objects.filter(ticket_id=42).exists())
        self.assertFalse(AuditEvent.objects.filter(action='ticket_deleted').exists())
