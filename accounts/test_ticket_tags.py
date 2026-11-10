import json
from unittest.mock import patch

from django.test import TestCase

from .models import AuditEvent, TicketArchive, TicketTag, TicketTagAssignment, User
from .tickets import InvalidTicketFilters, parse_ticket_tags


class TicketTagTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin', role=User.Role.ADMIN)
        self.staff = User.objects.create_user(username='staff', role=User.Role.STAFF)
        self.researcher = User.objects.create_user(username='researcher', role=User.Role.RESEARCHER)

    def request_json(self, method, path, data):
        return getattr(self.client, method)(path, data=json.dumps(data), content_type='application/json')

    def test_staff_create_admin_delete_and_researcher_read_only(self):
        self.client.force_login(self.staff)
        response = self.request_json('post', '/api/tickets/tags', {'name': '  Image   quality  '})
        self.assertEqual(response.status_code, 201)
        tag = TicketTag.objects.get()
        self.assertEqual(tag.name, 'Image quality')
        self.assertEqual(self.request_json('post', '/api/tickets/tags', {'name': 'image quality'}).status_code, 409)
        self.assertEqual(self.client.delete(f'/api/tickets/tags/{tag.pk}').status_code, 403)
        self.client.force_login(self.researcher)
        self.assertEqual(self.client.get('/api/tickets/tags').json()['tags'][0]['name'], tag.name)
        self.assertEqual(self.request_json('post', '/api/tickets/tags', {'name': 'other'}).status_code, 403)
        self.assertEqual(self.client.delete(f'/api/tickets/tags/{tag.pk}').status_code, 403)
        TicketTagAssignment.objects.create(ticket_id=1, tag=tag)
        self.client.force_login(self.admin)
        self.assertEqual(self.client.delete(f'/api/tickets/tags/{tag.pk}').status_code, 200)
        self.assertFalse(TicketTagAssignment.objects.exists())
        self.assertEqual(AuditEvent.objects.get(action='ticket_tag_deleted').before['tickets'], 1)

    def test_assignments_conflict_and_archive_are_enforced(self):
        tag = TicketTag.objects.create(name='Software')
        self.client.force_login(self.staff)
        path = '/api/tickets/42/tags'
        with patch('accounts.views.lock_ticket_for_archive', return_value=True):
            self.assertEqual(self.request_json('patch', path, {'tags': [str(tag.pk)], 'expected': []}).status_code, 200)
            self.assertEqual(self.request_json('patch', path, {'tags': [], 'expected': []}).status_code, 409)
            self.assertEqual(self.client.get(path).json()['tags'][0]['name'], 'Software')
            TicketArchive.objects.create(ticket_id=42, reason='Duplicate', archived_by=self.staff)
            self.assertEqual(self.request_json('patch', path, {'tags': [], 'expected': [str(tag.pk)]}).status_code, 404)
            self.assertEqual(self.client.get(path).status_code, 404)
        self.assertTrue(AuditEvent.objects.filter(action='ticket_tags_changed').exists())
        self.client.force_login(self.researcher)
        self.assertEqual(self.client.get(path).status_code, 403)

    def test_tag_validation_and_legacy_user_issue_filter(self):
        self.assertEqual(parse_ticket_tags('["2", "1", "2"]'), [1, 2])
        for value in ('[1]', '["0"]', '["abc"]', '{}'):
            with self.assertRaises(InvalidTicketFilters):
                parse_ticket_tags(value)
        self.client.force_login(self.staff)
        with patch('accounts.tickets.connection') as database:
            cursor = database.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = (0,)
            cursor.fetchall.return_value = []
            self.assertEqual(self.client.get('/api/tickets', {'status': 'all', 'type': 'USER_ISSUE'}).status_code, 200)
            self.assertIn("ticket_type IN ('USER_REQUEST', 'USER_REPORT')", cursor.execute.call_args_list[0].args[0])
