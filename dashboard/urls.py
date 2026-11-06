from django.http import HttpResponseNotFound
from django.urls import include, path, re_path
from accounts import views

urlpatterns = [
    path('', views.home, name='home'),
    path('health/live/', views.live, name='live'),
    path('health/ready/', views.ready, name='ready'),
    path('administration/', views.administration, name='administration'),
    path('administration/accounts/<int:user_id>/', views.update_account, name='update_account'),
    # Accounts are provisioned only through ORCID; do not expose password recovery,
    # local login or self-service identity removal as alternate access paths.
    re_path(r'^accounts/(?:login|signup|password(?:/.*)?|email(?:/.*)?|3rdparty/connections)/?$', lambda request: HttpResponseNotFound()),
    path('accounts/', include('allauth.urls')),
]
