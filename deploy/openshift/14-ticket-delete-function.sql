-- Run as a PostgreSQL administrator after the Django migration. The dashboard
-- runtime must not receive general DELETE privileges on shared legacy tables.
GRANT SELECT, INSERT, DELETE ON public.accounts_ticketarchive TO filestats_dashboard;
GRANT SELECT ON public.accounts_ticketarchive TO dashboard_backup_reader;

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
