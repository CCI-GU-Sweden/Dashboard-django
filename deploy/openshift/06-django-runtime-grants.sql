-- Apply as the owner of these Django tables after the initial migration.
-- Only Django-owned objects from migration r001 are included; existing CCI tables
-- and future objects are intentionally not covered.
BEGIN;
GRANT USAGE ON SCHEMA public TO filestats_dashboard;
GRANT SELECT ON public.auth_group, public.auth_group_permissions,
    public.auth_permission, public.django_content_type, public.django_migrations,
    public.socialaccount_socialapp TO filestats_dashboard;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.accounts_user,
    public.accounts_user_groups, public.accounts_user_user_permissions,
    public.account_emailaddress, public.account_emailconfirmation,
    public.django_session, public.socialaccount_socialaccount,
    public.socialaccount_socialtoken TO filestats_dashboard;
GRANT SELECT, INSERT ON public.accounts_auditevent TO filestats_dashboard;
GRANT USAGE, SELECT ON SEQUENCE public.accounts_user_id_seq,
    public.accounts_user_groups_id_seq, public.accounts_user_user_permissions_id_seq,
    public.accounts_auditevent_id_seq, public.account_emailaddress_id_seq,
    public.account_emailconfirmation_id_seq, public.socialaccount_socialaccount_id_seq,
    public.socialaccount_socialtoken_id_seq TO filestats_dashboard;
COMMIT;
