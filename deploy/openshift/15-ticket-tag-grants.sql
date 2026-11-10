-- Test cluster roles. Run after accounts.0006; adjust roles in other environments.
GRANT SELECT, INSERT, DELETE ON public.accounts_tickettag, public.accounts_tickettagassignment TO filestats_dashboard;
-- PostgreSQL requires UPDATE privilege for SELECT FOR UPDATE, used to prevent
-- a tag being deleted while a ticket is being assigned that tag.
GRANT UPDATE (name) ON public.accounts_tickettag TO filestats_dashboard;
GRANT USAGE, SELECT ON SEQUENCE public.accounts_tickettag_id_seq, public.accounts_tickettagassignment_id_seq TO filestats_dashboard;
GRANT SELECT ON public.accounts_tickettag, public.accounts_tickettagassignment TO dashboard_backup_reader;
GRANT SELECT ON SEQUENCE public.accounts_tickettag_id_seq, public.accounts_tickettagassignment_id_seq TO dashboard_backup_reader;
