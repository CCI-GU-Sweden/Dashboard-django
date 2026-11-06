from allauth.account.adapter import DefaultAccountAdapter
from allauth.socialaccount.adapter import DefaultSocialAccountAdapter
from django.core.exceptions import PermissionDenied


class AccountAdapter(DefaultAccountAdapter):
    def is_open_for_signup(self, request):
        # Local password signup is closed; ORCID social signup is separate.
        return False


class SocialAdapter(DefaultSocialAccountAdapter):
    def is_open_for_signup(self, request, sociallogin):
        return sociallogin.account.provider == 'orcid'

    def pre_social_login(self, request, sociallogin):
        # Account linking would allow an identity change without administrator review.
        if sociallogin.state.get('process') == 'connect':
            raise PermissionDenied('Connecting additional identities is disabled.')
