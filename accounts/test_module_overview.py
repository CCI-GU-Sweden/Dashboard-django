from unittest import skipUnless
from unittest.mock import patch

from django.conf import settings
from django.db import DatabaseError
from django.test import TestCase, override_settings

from dashboard.modules import DashboardModule
from .models import User

example_module = DashboardModule(
    key='example', name='Example', eyebrow='Example module', icon='*',
    url_name='home', urlconf='upload_stats.urls',
    can_view=lambda user: user.role == User.Role.STAFF,
    get_metrics=lambda user: [{'label': 'Count', 'value': '7'}],
)


@override_settings(DASHBOARD_MODULES=['accounts.test_module_overview.example_module'])
class ModuleContractTests(TestCase):
    def test_new_module_supplies_card_and_metrics_without_core_changes(self):
        user = User.objects.create_user(username='module-staff', role=User.Role.STAFF)
        self.client.force_login(user)
        self.assertContains(self.client.get('/'), 'data-module-overview="/api/modules/example/overview"')
        response = self.client.get('/api/modules/example/overview')
        self.assertEqual(response.json()['metrics'], [{'label': 'Count', 'value': '7'}])


@skipUnless(settings.DASHBOARD_UPLOADS_ENABLED, 'Upload module must be enabled')
class ModuleOverviewTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user(username='module-user', role=User.Role.STAFF)
        self.path = '/api/modules/uploads/overview'

    @patch('upload_stats.data.upload_summary')
    def test_permissions_apply_to_the_card_and_the_endpoint(self, summary):
        self.assertEqual(self.client.get(self.path).status_code, 403)
        for role in ('', User.Role.RESEARCHER):
            self.user.role = role
            self.user.save(update_fields=['role'])
            self.client.force_login(self.user)
            self.assertEqual(self.client.get(self.path).status_code, 403)
            self.assertNotContains(self.client.get('/'), 'data-module-overview="/api/modules/uploads/overview"')
        summary.assert_not_called()
        self.user.role = User.Role.STAFF
        self.user.save(update_fields=['role'])
        self.assertContains(self.client.get('/'), 'data-module-overview="/api/modules/uploads/overview"')

    @patch('upload_stats.data.upload_summary')
    def test_core_returns_simple_metrics_and_handles_failure(self, summary):
        self.client.force_login(self.user)
        summary.return_value = {'total_files': 42, 'total_size_gb': 1.5, 'top_scope_files': {'name': 'A', 'count': 9}}
        result = self.client.get(self.path)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json(), {'version': 1, 'module': 'uploads', 'metrics': [
            {'label': 'Files imported', 'value': '42'},
            {'label': 'Total data', 'value': '1.50 GB'},
            {'label': 'Top microscope', 'value': 'A'},
        ]})
        summary.assert_called_once_with({'period': '30'})
        summary.side_effect = DatabaseError
        self.assertEqual(self.client.get(self.path).status_code, 503)
        self.assertEqual(self.client.get('/api/modules/unknown/overview').status_code, 404)
