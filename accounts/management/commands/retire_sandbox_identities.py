from allauth.socialaccount.models import SocialAccount
from django.conf import settings
from django.contrib.sessions.models import Session
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from accounts.models import AuditEvent, User


class Command(BaseCommand):
    help = 'Isolate existing sandbox ORCID accounts before enabling production ORCID.'

    def add_arguments(self, parser):
        parser.add_argument('--confirm-sandbox-cutover', action='store_true')

    @transaction.atomic
    def handle(self, *args, **options):
        if not options['confirm_sandbox_cutover']:
            raise CommandError('Pass --confirm-sandbox-cutover after taking a backup.')
        if settings.SOCIALACCOUNT_PROVIDERS['orcid']['BASE_DOMAIN'] != 'sandbox.orcid.org':
            raise CommandError('This command must run with sandbox ORCID configuration.')
        identities = list(SocialAccount.objects.select_for_update().filter(provider='orcid'))
        if SocialAccount.objects.filter(provider='orcid-sandbox').exists():
            raise CommandError('Sandbox identities have already been isolated; inspect before proceeding.')
        if not identities:
            raise CommandError('No sandbox ORCID identities found; nothing changed.')
        user_ids = {identity.user_id for identity in identities}
        if SocialAccount.objects.filter(user_id__in=user_ids).exclude(provider='orcid').exists():
            raise CommandError('A sandbox account has another login identity; inspect before proceeding.')
        users = list(User.objects.select_for_update().filter(pk__in=user_ids))
        if User.objects.filter(role=User.Role.ADMIN, is_active=True).exclude(pk__in=user_ids).exists():
            raise CommandError('An active administrator is not a sandbox ORCID user; nothing changed.')
        for user in users:
            AuditEvent.objects.create(actor=user, target=user, action='sandbox_identity_retired',
                                      before={'is_active': user.is_active, 'role': user.role},
                                      after={'is_active': False, 'role': user.role})
        User.objects.filter(pk__in=user_ids).update(is_active=False)
        SocialAccount.objects.filter(pk__in=[identity.pk for identity in identities]).update(provider='orcid-sandbox')
        Session.objects.all().delete()
        self.stdout.write(self.style.SUCCESS(f'Isolated {len(identities)} sandbox identities; signed out all sessions.'))
