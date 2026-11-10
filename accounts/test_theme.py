from django.test import TestCase
from .models import User


class ThemePageTests(TestCase):
    def test_dashboard_and_allauth_pages_include_theme_control(self):
        self.assertContains(self.client.get('/'), 'id="theme-toggle"')
        user = User.objects.create_user(username='tester', role=User.Role.STAFF)
        self.client.force_login(user)
        response = self.client.get('/accounts/logout/')
        self.assertContains(response, 'id="theme-toggle"')
        self.assertContains(response, 'Sign Out', html=False)
