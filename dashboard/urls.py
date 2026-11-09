from django.http import HttpResponseNotFound
from django.urls import include, path, re_path
from accounts import views

urlpatterns = [
    path('', views.home, name='home'),
    path('uploads/', views.uploads, name='uploads'),
    path('api/uploads/summary', views.uploads_summary, name='uploads_summary'),
    path('api/uploads/scopes', views.upload_scopes, name='upload_scopes'),
    path('storage/', views.storage, name='storage'),
    path('storage/billing/', views.billing, name='billing'),
    path('api/omero/billing', views.billing_summary, name='billing_summary'),
    path('api/omero/filesets', views.storage_filesets, name='storage_filesets'),
    path('api/omero/filesets/<int:fileset_id>', views.fileset_detail, name='fileset_detail'),
    path('api/omero/groups', views.storage_groups, name='storage_groups'),
    path('api/omero/groups/<int:group_id>/email-draft', views.storage_email_draft, name='storage_email_draft'),
    path('api/omero/history', views.storage_history, name='storage_history'),
    path('api/omero/overview', views.storage_overview, name='storage_overview'),
    path('api/omero/policies', views.create_storage_policy, name='create_storage_policy'),
    path('api/omero/admin/<str:kind>', views.storage_admin_data, name='storage_admin_data'),
    path('tickets/', views.tickets, name='tickets'),
    path('api/tickets', views.ticket_inventory, name='ticket_inventory'),
    path('api/tickets/summary', views.ticket_summary, name='ticket_summary'),
    path('api/tickets/equipment', views.ticket_equipment, name='ticket_equipment'),
    path('tickets/<int:ticket_id>/', views.ticket_detail, name='ticket_detail'),
    path('api/tickets/<int:ticket_id>', views.ticket_detail_data, name='ticket_detail_data'),
    path('api/tickets/<int:ticket_id>/images/<int:image_id>', views.ticket_image, name='ticket_image'),
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
