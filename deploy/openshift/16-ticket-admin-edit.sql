-- Apply as PostgreSQL administrator. Adjust the runtime role per environment.
GRANT UPDATE (reporter_name, reporter_identifier, microscope, message, ticket_type) ON public.microscope_ticket TO filestats_dashboard;

-- Keep legacy image DELETE off the runtime role. The application checks the
-- administrator role and writes the audit event in the same transaction.
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
