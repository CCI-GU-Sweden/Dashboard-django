-- Apply after migration 0003, as the owner of the new Django table.
-- Links never change or grant ownership of the existing collector ticket table.
GRANT SELECT, INSERT, UPDATE, DELETE ON TABLE public.accounts_ticketresearcherlink TO filestats_dashboard;
GRANT USAGE, SELECT ON SEQUENCE public.accounts_ticketresearcherlink_id_seq TO filestats_dashboard;
