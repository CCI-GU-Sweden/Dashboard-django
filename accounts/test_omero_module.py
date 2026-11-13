from datetime import date, timedelta
from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase, override_settings
from django.utils import timezone

from .models import User, VerifiedOmeroGroup


@skipUnless(settings.DASHBOARD_OMERO_ENABLED, 'OMERO module must be enabled')
class OmeroModuleTests(TestCase):
    def test_overview_requires_current_verified_groups_and_hides_billing(self):
        admin = User.objects.create_user(username='admin', role=User.Role.ADMIN)
        researcher = User.objects.create_user(username='researcher', role=User.Role.RESEARCHER)
        self.client.force_login(researcher)
        endpoint = '/api/modules/omero/overview'
        with patch('omero_filesets.data.overview_card') as overview:
            self.assertEqual(self.client.get(endpoint).status_code, 403)
            overview.assert_not_called()
            group = VerifiedOmeroGroup.objects.create(user=researcher, group_id=42, verified_by=admin, valid_until=timezone.localdate() + timedelta(days=1))
            overview.return_value = {'snapshot_date': date(2026, 11, 8), 'comparison_date': date(2026, 10, 9), 'metrics': {
                'filesets': {'value': 4, 'change_percent': 100},
                'storage_gb': {'value': 2, 'change_percent': None},
            }}
            response = self.client.get(endpoint)
            self.assertEqual(response.status_code, 200)
            overview.assert_called_once_with(allowed_group=[42], include_billable=False)
            metrics = response.json()['metrics']
            self.assertEqual(metrics[1]['value'], '4')
            self.assertEqual(metrics[1]['detail'], '+100.0% vs 2026-10-09')
            self.assertNotIn('daily_sek', [metric['key'] for metric in metrics])
            group.delete()
            self.assertEqual(self.client.get(endpoint).status_code, 403)


@skipUnless(not settings.DASHBOARD_OMERO_ENABLED, 'Run with DASHBOARD_OMERO_ENABLED=0')
class OmeroDisabledTests(TestCase):
    def test_routes_and_card_are_absent(self):
        user = User.objects.create_user(username='staff', role=User.Role.STAFF)
        self.client.force_login(user)
        page = self.client.get('/')
        self.assertEqual(page.status_code, 200)
        self.assertNotContains(page, 'overview-omero-filesets')
        self.assertNotContains(page, 'js/storage_overview.js')
        for path in ('/storage/', '/storage/billing/', '/api/omero/filesets', '/api/omero/overview-card', '/api/modules/omero/overview'):
            self.assertEqual(self.client.get(path).status_code, 404)


@skipUnless(settings.DASHBOARD_OMERO_ENABLED, 'OMERO module must be enabled')
@override_settings(DASHBOARD_OMERO_BILLING_ENABLED=False)
class OmeroBillingDisabledTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='billing-admin', role=User.Role.ADMIN)
        self.client.force_login(self.admin)

    def test_billing_and_related_routes_and_controls_are_unavailable(self):
        page = self.client.get('/storage/')
        self.assertEqual(page.status_code, 200)
        for text in ('panel-billing', 'panel-policies', 'generate-email', 'Daily billable', 'history-metric'):
            self.assertNotContains(page, text)
        self.assertContains(page, 'panel-health')
        self.assertContains(page, 'Fileset inventory')
        self.assertNotContains(self.client.get('/'), 'overview-omero-billable')
        for path in ('/storage/billing/', '/api/omero/billing', '/api/omero/admin/policies', '/api/omero/groups/42/email-draft'):
            self.assertEqual(self.client.get(path).status_code, 404)
        self.assertEqual(self.client.post('/api/omero/policies', data='{}', content_type='application/json').status_code, 404)

    @patch('omero_filesets.data.connection')
    def test_storage_queries_do_not_read_billing_columns(self, database):
        cursor = database.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [('current', date(2026, 11, 8), 4, 2)]
        response = self.client.get('/api/modules/omero/overview')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('daily_sek', [item['key'] for item in response.json()['metrics']])
        self.assertNotIn('daily_charge_ore', cursor.execute.call_args.args[0])
        cursor.reset_mock()
        cursor.fetchall.return_value = [(date(2026, 11, 8), 2)]
        response = self.client.get('/api/omero/history')
        self.assertEqual(response.status_code, 200)
        self.assertNotIn('billable', response.json()['history'][0])
        self.assertNotIn('billable_bytes', cursor.execute.call_args.args[0])
        self.assertEqual(self.client.get('/api/omero/history?metric=ore').status_code, 400)
        cursor.reset_mock()
        cursor.fetchone.return_value = (4, 2)
        cursor.fetchall.return_value = [(42, 'group', 2)]
        response = self.client.get('/api/omero/overview')
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['groups'][0]['total'], 2)
        for call in cursor.execute.call_args_list:
            self.assertNotIn('billable', call.args[0])
            self.assertNotIn('daily_charge_ore', call.args[0])

    @patch('omero_filesets.data.connection')
    def test_researcher_data_stays_group_scoped_without_billing(self, database):
        user = User.objects.create_user(username='billing-researcher', role=User.Role.RESEARCHER)
        VerifiedOmeroGroup.objects.create(user=user, group_id=42, verified_by=self.admin, valid_until=timezone.localdate() + timedelta(days=1))
        self.client.force_login(user)
        self.assertNotContains(self.client.get('/storage/'), 'panel-billing')
        cursor = database.cursor.return_value.__enter__.return_value
        cursor.fetchall.return_value = [(date(2026, 11, 8), 2)]
        response = self.client.get('/api/omero/history?group_id=999')
        self.assertEqual(response.status_code, 200)
        self.assertIn([42], cursor.execute.call_args.args[1])
        self.assertNotIn('billable', response.json()['history'][0])
        self.assertEqual(self.client.get('/api/omero/billing').status_code, 404)
