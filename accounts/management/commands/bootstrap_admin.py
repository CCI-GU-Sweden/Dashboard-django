from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from allauth.socialaccount.models import SocialAccount
from accounts.models import AuditEvent, User


class Command(BaseCommand):
    help = 'Promote a verified existing ORCID account when no active administrator exists.'

    def add_arguments(self, parser):
        parser.add_argument('orcid_id')

    @transaction.atomic
    def handle(self, *args, **options):
        # The deployment operator must serialize invocations of this command.
        if User.objects.select_for_update().filter(role=User.Role.ADMIN, is_active=True).exists():
            raise CommandError('An active administrator already exists.')
        identity = SocialAccount.objects.select_related('user').filter(provider='orcid', uid=options['orcid_id']).first()
        if not identity or not identity.user.is_active:
            raise CommandError('No active account with that authenticated ORCID iD exists.')
        user = identity.user
        before = {'role': user.role, 'is_active': user.is_active}
        user.role = User.Role.ADMIN
        user.save(update_fields=['role'])
        AuditEvent.objects.create(actor=user, target=user, action='bootstrap_admin', before=before, after={'role': user.role, 'is_active': user.is_active})
        self.stdout.write(self.style.SUCCESS('Administrator bootstrapped.'))
