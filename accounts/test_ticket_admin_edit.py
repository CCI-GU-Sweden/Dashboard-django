import json
from io import BytesIO
from unittest.mock import patch
from zipfile import ZipFile

from django.test import TestCase
from .models import User
from dashboard_tickets.models import TicketArchive
from dashboard_tickets.data import TicketCreateForm, TicketConflict, TicketAdminEditForm, TicketUpdateForm, read_ticket


class AdminTicketTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin', role=User.Role.ADMIN)
        self.staff = User.objects.create_user(username='staff', role=User.Role.STAFF)
        self.researcher = User.objects.create_user(username='researcher', role=User.Role.RESEARCHER)
        self.payload = {'version': 1, 'reporter_name': 'Reporter', 'reporter_identifier': 'r@example.org', 'microscope': '', 'message': 'Corrected report', 'ticket_type': 'USER_REQUEST', 'resolution_note': ''}

    def post(self, url, payload):
        return self.client.post(url, json.dumps(payload), content_type='application/json')

    def test_admin_edit_rejects_staff_and_researcher_and_conflicts(self):
        for user in (self.staff, self.researcher):
            self.client.force_login(user)
            self.assertEqual(self.post('/api/tickets/1/admin-edit', self.payload).status_code, 403)
            self.assertEqual(self.post('/api/tickets/1/images/2/remove', {'version': 1}).status_code, 403)
        self.client.force_login(self.admin)
        with patch('dashboard_tickets.data.admin_edit_ticket', side_effect=TicketConflict('Stale ticket')):
            response = self.post('/api/tickets/1/admin-edit', self.payload)
            self.assertEqual(response.status_code, 409)
            self.assertEqual(response.json()['error'], 'Stale ticket')

    def test_incident_cannot_be_created_but_can_be_preserved_for_edit(self):
        data = dict(self.payload, ticket_type='INCIDENT', priority='NORMAL', source_event_id='8ff8b72d-3646-4e0d-a16d-296b53d9a275')
        self.assertFalse(TicketCreateForm(data).is_valid())
        self.assertTrue(TicketAdminEditForm(data).is_valid())

    def test_waiting_cannot_be_selected_for_ticket_updates(self):
        update = {'version': 1, 'status': 'WAITING', 'priority': 'NORMAL'}
        self.assertFalse(TicketUpdateForm(update).is_valid())
        self.client.force_login(self.staff)
        self.assertNotContains(self.client.get('/tickets/'), '<option value="WAITING">')
        self.assertNotContains(self.client.get('/tickets/1/'), '<option value="WAITING">')
        with patch('dashboard_tickets.data.connection') as database:
            cursor = database.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = (0,)
            cursor.fetchall.return_value = []
            self.assertEqual(self.client.get('/api/tickets').status_code, 200)
            self.assertEqual(cursor.execute.call_args_list[0].args[1], ['OPEN', 'IN_PROGRESS'])

    def test_history_reads_json_returned_as_text_by_postgres(self):
        with patch('dashboard_tickets.data.connection') as db:
            cursor = db.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = (7, 'Name', 'r@example.org', '', 'New', 'USER_REQUEST', None, 'NORMAL', 'OPEN', None, None, None, None, 2, None)
            cursor.fetchall.side_effect = [[('UPDATED', 'OPEN', 'OPEN', 'Edited', 'Staff', None, json.dumps({'admin_edit': {'message': {'before': 'Old', 'after': 'New'}}}))], []]
            self.assertEqual(read_ticket(7)['events'][0]['admin_edit']['message']['before'], 'Old')

    def test_export_is_staff_only_and_contains_report_history_and_images(self):
        self.client.force_login(self.researcher)
        self.assertEqual(self.client.get('/api/tickets/7/export').status_code, 403)
        self.client.force_login(self.staff)
        ticket = {'ticket_id': '7', 'reporter_name': 'Name', 'reporter_identifier': 'r@example.org', 'microscope': 'id', 'ticket_type': 'USER_REPORT', 'issue_type': 'SOFTWARE', 'priority': 'NORMAL', 'status': 'OPEN', 'assigned_staff': [], 'assigned_to_name': None, 'opened_at': None, 'updated_at': None, 'resolved_at': None, 'message': 'Problem', 'resolution_note': None, 'events': [{'occurred_at': None, 'actor': 'Staff', 'type': 'UPDATED', 'old_status': 'OPEN', 'new_status': 'OPEN', 'note': 'Edited', 'admin_edit': {'message': {'before': 'Old', 'after': 'Problem'}}}]}
        with patch('dashboard_tickets.data.read_ticket', return_value=ticket), patch('dashboard_tickets.views.connection') as db:
            cursor = db.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = ('Microscope A',)
            cursor.fetchall.return_value = [(3, '../image.png', 'png', b'image bytes')]
            response = self.client.get('/api/tickets/7/export')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/zip')
        with ZipFile(BytesIO(response.content)) as archive:
            self.assertEqual(sorted(archive.namelist()), ['images/ticket-image-3.png', 'ticket.txt'])
            report = archive.read('ticket.txt').decode()
            self.assertIn('User issue', report)
            self.assertIn('Before: Old', report)
            self.assertEqual(archive.read('images/ticket-image-3.png'), b'image bytes')
        TicketArchive.objects.create(ticket_id=7, reason='duplicate', archived_by=self.admin)
        self.assertEqual(self.client.get('/api/tickets/7/export').status_code, 404)
