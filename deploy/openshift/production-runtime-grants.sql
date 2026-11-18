-- Apply as the migration owner after the ticket baseline and Django migrations.
-- Grant only the additional privileges required by the dashboard.
\set ON_ERROR_STOP on
BEGIN;
GRANT USAGE ON SCHEMA public TO filestats_dashboard;
GRANT SELECT, INSERT ON public.ticket_equipment TO filestats_dashboard;
GRANT UPDATE (name, category, active) ON public.ticket_equipment TO filestats_dashboard;
GRANT SELECT, INSERT ON public.microscope_ticket, public.microscope_ticket_event, public.microscope_ticket_image TO filestats_dashboard;
GRANT UPDATE (status, resolved_at, resolution_note, priority, assigned_to, issue_type, chat_thread_id, chat_url, chat_state, updated_at, updated_by, version, reporter_name, reporter_identifier, microscope, message, ticket_type) ON public.microscope_ticket TO filestats_dashboard;
GRANT USAGE ON SEQUENCE public.microscope_ticket_ticket_id_seq, public.microscope_ticket_event_event_id_seq, public.microscope_ticket_image_image_id_seq TO filestats_dashboard;
GRANT SELECT ON public.auth_group, public.auth_group_permissions, public.auth_permission, public.django_content_type, public.django_migrations, public.socialaccount_socialapp TO filestats_dashboard;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.accounts_user, public.accounts_user_groups, public.accounts_user_user_permissions, public.account_emailaddress, public.account_emailconfirmation, public.django_session, public.socialaccount_socialaccount, public.socialaccount_socialtoken, public.accounts_verifiedomerogroup, public.accounts_ticketresearcherlink, public.accounts_ticketstaffassignment TO filestats_dashboard;
GRANT SELECT, INSERT ON public.accounts_auditevent TO filestats_dashboard;
GRANT SELECT, INSERT, DELETE ON public.accounts_ticketarchive, public.accounts_tickettag, public.accounts_tickettagassignment TO filestats_dashboard;
GRANT UPDATE (name) ON public.accounts_tickettag TO filestats_dashboard;
GRANT USAGE, SELECT ON SEQUENCE public.accounts_user_id_seq, public.accounts_user_groups_id_seq, public.accounts_user_user_permissions_id_seq, public.accounts_auditevent_id_seq, public.account_emailaddress_id_seq, public.account_emailconfirmation_id_seq, public.socialaccount_socialaccount_id_seq, public.socialaccount_socialtoken_id_seq, public.accounts_verifiedomerogroup_id_seq, public.accounts_ticketresearcherlink_id_seq, public.accounts_ticketstaffassignment_id_seq, public.accounts_tickettag_id_seq, public.accounts_tickettagassignment_id_seq TO filestats_dashboard;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO dashboard_backup_reader;
GRANT SELECT ON ALL SEQUENCES IN SCHEMA public TO dashboard_backup_reader;

CREATE OR REPLACE FUNCTION public.dashboard_purge_archived_ticket(p_ticket_id bigint)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
    PERFORM 1 FROM public.microscope_ticket WHERE ticket_id = p_ticket_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Ticket not found'; END IF;
    IF NOT EXISTS (SELECT 1 FROM public.accounts_ticketarchive WHERE ticket_id = p_ticket_id) THEN
        RAISE EXCEPTION 'Ticket is not archived';
    END IF;
    DELETE FROM public.microscope_ticket_image WHERE ticket_id = p_ticket_id;
    DELETE FROM public.microscope_ticket_event WHERE ticket_id = p_ticket_id;
    DELETE FROM public.microscope_ticket WHERE ticket_id = p_ticket_id;
END;
$$;
REVOKE ALL ON FUNCTION public.dashboard_purge_archived_ticket(bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.dashboard_purge_archived_ticket(bigint) TO filestats_dashboard;

CREATE OR REPLACE FUNCTION public.dashboard_remove_ticket_image(p_ticket_id bigint, p_image_id bigint)
RETURNS void LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog AS $$
BEGIN
    PERFORM 1 FROM public.microscope_ticket WHERE ticket_id = p_ticket_id FOR UPDATE;
    IF NOT FOUND THEN RAISE EXCEPTION 'Ticket not found'; END IF;
    IF EXISTS (SELECT 1 FROM public.accounts_ticketarchive WHERE ticket_id = p_ticket_id) THEN
        RAISE EXCEPTION 'Ticket is archived';
    END IF;
    DELETE FROM public.microscope_ticket_image WHERE ticket_id = p_ticket_id AND image_id = p_image_id;
    IF NOT FOUND THEN RAISE EXCEPTION 'Image not found'; END IF;
END;
$$;
REVOKE ALL ON FUNCTION public.dashboard_remove_ticket_image(bigint, bigint) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.dashboard_remove_ticket_image(bigint, bigint) TO filestats_dashboard;
COMMIT;
