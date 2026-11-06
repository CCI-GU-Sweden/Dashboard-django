from io import StringIO
from datetime import datetime, timezone
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

    def test_upload_data_is_only_available_to_staff_and_admin(self):
        endpoint = reverse('uploads_summary')
        with patch('accounts.uploads.upload_summary', return_value={'total_files': 42}) as summary:
            self.assertEqual(self.client.get(endpoint).status_code, 403)
            for role in ('', User.Role.RESEARCHER):
                self.pending.role = role
                self.pending.save(update_fields=['role'])
                self.client.force_login(self.pending)
                self.assertEqual(self.client.get(endpoint).status_code, 403)
                self.assertEqual(self.client.get(reverse('uploads')).status_code, 403)
            summary.assert_not_called()
            for role in (User.Role.STAFF, User.Role.ADMIN):
                self.pending.role = role
                self.pending.save(update_fields=['role'])
                self.assertEqual(self.client.get(endpoint).json(), {'total_files': 42})
                self.assertEqual(self.client.get(reverse('uploads')).status_code, 200)

    def test_researcher_home_does_not_include_operational_views(self):
        self.pending.role = User.Role.RESEARCHER
        self.pending.save(update_fields=['role'])
        self.client.force_login(self.pending)
        response = self.client.get(reverse('home'))
        self.assertContains(response, 'My storage')
        self.assertNotContains(response, 'Uploads')

    def test_upload_invalid_filters_do_not_query_database(self):
        self.client.force_login(self.admin)
        with patch('accounts.uploads.connection') as database:
            for query in ('?period=0', '?period=999999', '?startDate=2026-01-01', '?startDate=2026-03-01&endDate=2026-02-01'):
                self.assertEqual(self.client.get(reverse('uploads_summary') + query).status_code, 400)
            database.cursor.assert_not_called()

    def test_upload_summary_aggregates_without_returning_usernames(self):
        self.client.force_login(self.admin)
        rows = [
            ('Scope A', datetime(2026, 1, 3, tzinfo=timezone.utc), 'private-user', 3, 1024, 120),
            ('Scope A', datetime(2026, 1, 4, tzinfo=timezone.utc), 'private-user', 2, 512, 60),
        ]
        with patch('accounts.uploads.connection') as database:
            database.cursor.return_value.__enter__.return_value.fetchall.return_value = rows
            response = self.client.get(reverse('uploads_summary'), {'startDate': '2026-01-01', 'endDate': '2026-01-31'})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['total_files'], 5)
        self.assertEqual(response.json()['total_size_gb'], 1.5)
        self.assertEqual(response.json()['unique_users'], 1)
        self.assertEqual(response.json()['top_scope_files']['name'], 'Scope A')
        self.assertNotContains(response, 'private-user')

    def test_storage_filesets_are_staff_only_and_do_not_offer_price_sorting(self):
        self.pending.role = User.Role.RESEARCHER
        self.pending.save(update_fields=['role'])
        self.client.force_login(self.pending)
        with patch('accounts.storage.connection') as database:
            self.assertEqual(self.client.get(reverse('storage')).status_code, 403)
            self.assertEqual(self.client.get(reverse('storage_filesets')).status_code, 403)
            database.cursor.assert_not_called()
            self.pending.role = User.Role.STAFF
            self.pending.save(update_fields=['role'])
            self.assertEqual(self.client.get(reverse('storage_filesets'), {'sort': 'daily_charge_sek'}).status_code, 400)
            database.cursor.assert_not_called()
            cursor = database.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = (1,)
            cursor.fetchall.return_value = [(7, 'user', 'group', None, 1000, None, 2, 3, 'First', 'Last')]
            response = self.client.get(reverse('storage_filesets'))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['results'][0]['fileset_id'], '7')
            self.assertNotContains(response, 'daily_charge')

    def test_ticket_inventory_denies_researchers_and_is_read_only(self):
        self.pending.role = User.Role.RESEARCHER
        self.pending.save(update_fields=['role'])
        self.client.force_login(self.pending)
        with patch('accounts.tickets.connection') as database:
            self.assertEqual(self.client.get(reverse('tickets')).status_code, 403)
            self.assertEqual(self.client.get(reverse('ticket_inventory')).status_code, 403)
            database.cursor.assert_not_called()
            self.pending.role = User.Role.STAFF
            self.pending.save(update_fields=['role'])
            self.assertEqual(self.client.post(reverse('ticket_inventory'), data='{}', content_type='application/json').status_code, 400)
            self.assertEqual(self.client.get(reverse('ticket_inventory'), {'status': 'invalid'}).status_code, 400)
            database.cursor.assert_not_called()
            cursor = database.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = (1,)
            cursor.fetchall.return_value = [(1, 'Reporter', 'Scope', 'Issue', 'OPEN', 'NORMAL', None, 'USER_REQUEST', 'OTHER', None, None, None, 'DASHBOARD')]
            response = self.client.get(reverse('ticket_inventory'))
            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.json()['results'][0]['status'], 'OPEN')

    def test_billing_is_admin_only_even_for_direct_api_requests(self):
        with patch('accounts.storage.connection') as database:
            for role in ('', User.Role.RESEARCHER, User.Role.STAFF):
                self.pending.role = role
                self.pending.save(update_fields=['role'])
                self.client.force_login(self.pending)
                self.assertEqual(self.client.get(reverse('billing')).status_code, 403)
                self.assertEqual(self.client.get(reverse('billing_summary')).status_code, 403)
            database.cursor.assert_not_called()
            self.client.force_login(self.admin)
            self.assertEqual(self.client.get(reverse('billing_summary'), {'startDate': '2026-02-02', 'endDate': '2026-02-01'}).status_code, 400)
            database.cursor.assert_not_called()
            database.cursor.return_value.__enter__.return_value.fetchall.return_value = [(1, 'group', 2, 1.25, 3.5)]
            result = self.client.get(reverse('billing_summary'), {'startDate': '2026-02-01', 'endDate': '2026-02-02'})
            self.assertEqual(result.json()['groups'][0]['total_sek'], 3.5)

    def test_ticket_detail_and_attachments_deny_researchers(self):
        self.pending.role = User.Role.RESEARCHER
        self.pending.save(update_fields=['role'])
        self.client.force_login(self.pending)
        with patch('accounts.tickets.connection') as database:
            self.assertEqual(self.client.get(reverse('ticket_detail', args=[1])).status_code, 403)
            self.assertEqual(self.client.get(reverse('ticket_detail_data', args=[1])).status_code, 403)
            self.assertEqual(self.client.get(reverse('ticket_image', args=[1, 1])).status_code, 403)
            database.cursor.assert_not_called()
        self.pending.role = User.Role.STAFF
        self.pending.save(update_fields=['role'])
        with patch('accounts.tickets.connection') as database:
            database.cursor.return_value.__enter__.return_value.fetchone.return_value = None
            self.assertEqual(self.client.get(reverse('ticket_detail_data', args=[1])).status_code, 404)

    def test_ticket_creation_is_staff_only_csrf_protected_and_uses_account_actor(self):
        payload = {'reporter_name': 'Researcher', 'reporter_identifier': 'researcher@example.org', 'microscope': '', 'message': 'Please help', 'ticket_type': 'USER_REQUEST', 'issue_type': '', 'priority': 'NORMAL', 'source_event_id': '8ff8b72d-3646-4e0d-a16d-296b53d9a275'}
        import json
        self.pending.role = User.Role.RESEARCHER
        self.pending.save(update_fields=['role'])
        self.client.force_login(self.pending)
        self.assertEqual(self.client.post(reverse('ticket_inventory'), data=json.dumps(payload), content_type='application/json').status_code, 403)
        self.pending.role = User.Role.STAFF
        self.pending.save(update_fields=['role'])
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.force_login(self.pending)
        self.assertEqual(csrf_client.post(reverse('ticket_inventory'), data=json.dumps(payload), content_type='application/json').status_code, 403)
        with patch('accounts.tickets.connection') as database:
            cursor = database.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = (25, 1)
            result = self.client.post(reverse('ticket_inventory'), data=json.dumps(payload), content_type='application/json')
            self.assertEqual(result.status_code, 201)
            self.assertEqual(result.json()['ticket_id'], '25')
            self.assertEqual(cursor.execute.call_args_list[0].args[1][-1], f'dashboard-user:{self.pending.pk}')
            self.assertEqual(cursor.execute.call_args_list[1].args[1][-1], f'dashboard-user:{self.pending.pk}')
        payload['actor_name'] = 'spoofed'
        self.assertEqual(self.client.post(reverse('ticket_inventory'), data=json.dumps(payload), content_type='application/json').status_code, 400)

    def test_ticket_update_checks_role_version_and_reopening_reason(self):
        import json
        payload = {'version': 2, 'status': 'OPEN', 'priority': 'NORMAL', 'change_note': '', 'resolution_note': ''}
        self.pending.role = User.Role.RESEARCHER
        self.pending.save(update_fields=['role'])
        self.client.force_login(self.pending)
        self.assertEqual(self.client.patch(reverse('ticket_detail_data', args=[1]), data=json.dumps(payload), content_type='application/json').status_code, 403)
        self.pending.role = User.Role.STAFF
        self.pending.save(update_fields=['role'])
        with patch('accounts.tickets.connection') as database:
            cursor = database.cursor.return_value.__enter__.return_value
            cursor.fetchone.return_value = ('RESOLVED', 'NORMAL', 'closed', 3)
            self.assertEqual(self.client.patch(reverse('ticket_detail_data', args=[1]), data=json.dumps(payload), content_type='application/json').status_code, 409)
            payload['version'] = 3
            self.assertEqual(self.client.patch(reverse('ticket_detail_data', args=[1]), data=json.dumps(payload), content_type='application/json').status_code, 400)
            payload['change_note'] = 'Needs another look'
            cursor.fetchone.side_effect = [('RESOLVED', 'NORMAL', 'closed', 3), (4,)]
            result = self.client.patch(reverse('ticket_detail_data', args=[1]), data=json.dumps(payload), content_type='application/json')
            self.assertEqual(result.status_code, 200)
            self.assertEqual(result.json()['version'], 4)

    def test_new_fileset_controls_are_validated_and_remain_staff_only(self):
        self.pending.role = User.Role.RESEARCHER
        self.pending.save(update_fields=['role'])
        self.client.force_login(self.pending)
        self.assertEqual(self.client.get(reverse('storage_groups')).status_code, 403)
        self.assertEqual(self.client.get(reverse('fileset_detail', args=[1])).status_code, 403)
        self.pending.role = User.Role.STAFF
        self.pending.save(update_fields=['role'])
        with patch('accounts.storage.connection') as database:
            cursor = database.cursor.return_value.__enter__.return_value
            self.assertEqual(self.client.get(reverse('storage_filesets'), {'size': 'bad'}).status_code, 400)
            database.cursor.assert_not_called()
            cursor.fetchone.return_value = (0,)
            cursor.fetchall.return_value = []
            result = self.client.get(reverse('storage_filesets'), {'group_id': '42', 'imported': '90d', 'size': '100gb', 'sort': 'total_bytes'})
            self.assertEqual(result.status_code, 200)
            self.assertIn('group_id = %s', cursor.execute.call_args_list[0].args[0])
            self.assertIn(42, cursor.execute.call_args_list[0].args[1])
