from io import StringIO
from unittest.mock import patch, Mock
from urllib.parse import parse_qs, urlparse
from django.core.management import call_command, CommandError
from django.test import Client, TestCase
from django.urls import reverse
from allauth.socialaccount.models import SocialAccount
from .models import AuditEvent, User


class AccessTests(TestCase):
    def setUp(self):
        self.admin = User.objects.create_user(username='admin', role=User.Role.ADMIN)
        self.pending = User.objects.create_user(username='pending')

    def test_pending_cannot_use_administration_or_approve(self):
        self.client.force_login(self.pending)
        self.assertEqual(self.client.get(reverse('administration')).status_code, 403)
        response = self.client.post(reverse('update_account', args=[self.pending.pk]), {'role': 'admin', 'active': 'yes'})
        self.assertEqual(response.status_code, 403)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.role, '')

    def test_approval_and_revocation_are_audited_and_take_effect(self):
        self.client.force_login(self.admin)
        url = reverse('update_account', args=[self.pending.pk])
        self.assertEqual(self.client.post(url, {'role': 'staff', 'active': 'yes'}).status_code, 302)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.role, User.Role.STAFF)
        event = AuditEvent.objects.get()
        self.assertEqual(event.actor, self.admin)
        self.assertEqual(event.before['role'], '')
        self.assertEqual(event.after['role'], 'staff')
        self.client.force_login(self.pending)
        self.assertEqual(self.client.get(reverse('administration')).status_code, 403)
        self.client.force_login(self.admin)
        self.client.post(url, {'role': 'staff', 'active': 'no'})
        self.client.force_login(self.pending)
        self.assertEqual(self.client.get(reverse('administration')).status_code, 302)

    def test_last_admin_protected_and_post_required(self):
        self.client.force_login(self.admin)
        url = reverse('update_account', args=[self.admin.pk])
        self.assertEqual(self.client.get(url).status_code, 405)
        self.assertEqual(self.client.post(url, {'role': 'staff', 'active': 'yes'}).status_code, 400)
        self.assertFalse(AuditEvent.objects.exists())

    def test_role_and_disabled_status_apply_to_existing_session(self):
        other_admin = User.objects.create_user(username='other', role=User.Role.ADMIN)
        other_client = Client()
        other_client.force_login(other_admin)
        self.assertEqual(other_client.get(reverse('administration')).status_code, 200)
        self.client.force_login(self.admin)
        self.client.post(reverse('update_account', args=[other_admin.pk]), {'role': 'staff', 'active': 'yes'})
        self.assertEqual(other_client.get(reverse('administration')).status_code, 403)
        self.client.post(reverse('update_account', args=[other_admin.pk]), {'role': 'staff', 'active': 'no'})
        self.assertEqual(other_client.get(reverse('administration')).status_code, 302)

    def test_account_changes_require_csrf(self):
        client = Client(enforce_csrf_checks=True)
        client.force_login(self.admin)
        response = client.post(reverse('update_account', args=[self.pending.pk]), {'role': 'staff', 'active': 'yes'})
        self.assertEqual(response.status_code, 403)
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.role, '')

    def test_bootstrap_only_existing_identity_and_only_once(self):
        self.admin.role = ''
        self.admin.save()
        SocialAccount.objects.create(user=self.pending, provider='orcid', uid='0000-0001-2345-6789')
        call_command('bootstrap_admin', '0000-0001-2345-6789', stdout=StringIO())
        self.pending.refresh_from_db()
        self.assertEqual(self.pending.role, User.Role.ADMIN)
        self.assertTrue(AuditEvent.objects.filter(action='bootstrap_admin').exists())
        with self.assertRaises(CommandError):
            call_command('bootstrap_admin', '0000-0001-2345-6789', stdout=StringIO())

    def test_health_endpoints(self):
        self.assertEqual(self.client.get(reverse('live')).status_code, 200)
        self.assertEqual(self.client.get(reverse('ready')).status_code, 200)

    def test_orcid_callback_creates_pending_user_and_rejects_bad_state(self):
        response = self.client.post(reverse('orcid_login'))
        self.assertEqual(response.status_code, 302)
        state = parse_qs(urlparse(response.url).query)['state'][0]
        invalid = self.client.get(reverse('orcid_callback'), {'code': 'code', 'state': 'invalid'})
        self.assertNotEqual(invalid.status_code, 302)
        profile = {'orcid-identifier': {'path': '0000-0001-2345-6789'}, 'person': {'name': {'given-names': {'value': 'Researcher'}}}}
        with patch('allauth.socialaccount.providers.orcid.views.OrcidOAuth2Adapter.get_access_token_data', return_value={'access_token': 'temporary', 'orcid': '0000-0001-2345-6789'}), patch('allauth.socialaccount.providers.orcid.views.get_adapter') as adapter:
            adapter.return_value.get_requests_session.return_value.__enter__.return_value.get.return_value = Mock(json=lambda: profile)
            result = self.client.get(reverse('orcid_callback'), {'code': 'code', 'state': state})
        self.assertEqual(result.status_code, 302)
        account = SocialAccount.objects.get(uid='0000-0001-2345-6789')
        self.assertEqual(account.user.role, '')
        self.assertEqual(int(self.client.session['_auth_user_id']), account.user_id)
        self.assertEqual(self.client.get(reverse('administration')).status_code, 403)

    def test_password_and_identity_management_routes_are_unavailable(self):
        for path in ['/accounts/login/', '/accounts/signup/', '/accounts/password/reset/', '/accounts/3rdparty/connections/']:
            self.assertEqual(self.client.get(path).status_code, 404)
