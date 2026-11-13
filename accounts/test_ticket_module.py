from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase

from .models import User


@skipUnless(settings.DASHBOARD_TICKETS_ENABLED, 'Tickets must be enabled')
class TicketOverviewModuleTests(TestCase):
    @patch('dashboard_tickets.data.ticket_summary')
    def test_overview_is_scoped_and_requires_approved_account(self, summary):
        user = User.objects.create_user(username='researcher', role=User.Role.RESEARCHER)
        summary.return_value = {'total': 7, 'active': 3, 'resolved': 4, 'changes': {'total': 7, 'active': None, 'resolved': -1}}
        endpoint = '/api/modules/tickets/overview'
        self.assertEqual(self.client.get(endpoint).status_code, 403)
        self.client.force_login(user)
        response = self.client.get(endpoint)
        self.assertEqual(response.status_code, 200)
        summary.assert_called_once_with(researcher_id=user.pk)
        self.assertEqual(response.json()['metrics'][0]['value'], '7')
        self.assertEqual(response.json()['metrics'][1]['detail'], 'Comparison unavailable')
        self.assertEqual(response.json()['metrics'][2]['detail'], '-1 vs previous 30 days')


@skipUnless(not settings.DASHBOARD_TICKETS_ENABLED, 'Run with DASHBOARD_TICKETS_ENABLED=0')
class TicketsDisabledTests(TestCase):
    def test_disabled_routes_and_administration_preserve_researcher_permission(self):
        admin = User.objects.create_user(username='admin', role=User.Role.ADMIN)
        user = User.objects.create_user(username='researcher', role=User.Role.RESEARCHER, can_create_tickets=True)
        self.client.force_login(admin)
        for path in ('/tickets/', '/api/tickets', '/api/tickets/summary', '/api/modules/tickets/overview'):
            self.assertEqual(self.client.get(path).status_code, 404)
        self.assertNotContains(self.client.get('/'), 'overview-tickets-total')
        self.assertNotContains(self.client.get('/administration/'), 'Manage equipment')
        self.assertEqual(self.client.post(f'/administration/accounts/{user.pk}/', {'role': 'researcher', 'active': 'yes'}).status_code, 302)
        user.refresh_from_db()
        self.assertTrue(user.can_create_tickets)
