from unittest import skipUnless

from django.conf import settings
from django.test import TestCase

from .models import User


@skipUnless(not settings.DASHBOARD_UPLOADS_ENABLED, 'Run with DASHBOARD_UPLOADS_ENABLED=0')
class UploadsDisabledTests(TestCase):
    def test_upload_routes_and_home_card_are_absent(self):
        user = User.objects.create_user(username='staff', role=User.Role.STAFF)
        self.client.force_login(user)
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, 'data-module-overview')
        self.assertNotContains(response, 'js/uploads.js')
        for path in ('/uploads/', '/api/uploads/summary', '/api/uploads/scopes', '/api/modules/uploads/overview'):
            self.assertEqual(self.client.get(path).status_code, 404)
