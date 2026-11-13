from django.http import HttpResponseNotFound
from django.urls import include, path, re_path
from accounts import views
from .module_views import module_overview
from .modules import registered_modules

urlpatterns = [
    path('', views.home, name='home'),
    path('api/modules/<slug:module_key>/overview', module_overview, name='module_overview'),
    path('health/live/', views.live, name='live'),
    path('health/ready/', views.ready, name='ready'),
    path('administration/', views.administration, name='administration'),
    path('administration/accounts/<int:user_id>/', views.update_account, name='update_account'),
    path('administration/accounts/<int:user_id>/omero/', views.update_omero_group, name='update_omero_group'),
    # Accounts are provisioned only through ORCID; do not expose password recovery,
    # local login or self-service identity removal as alternate access paths.
    re_path(r'^accounts/(?:login|signup|password(?:/.*)?|email(?:/.*)?|3rdparty/connections)/?$', lambda request: HttpResponseNotFound()),
    path('accounts/', include('allauth.urls')),
]

for module in registered_modules():
    urlpatterns += [path('', include(module.urlconf))]
