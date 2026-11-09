-- Apply as the owner of the shared ticket catalogue, after confirming the target database.
-- Equipment IDs remain stable; this role does not need DELETE or permission to change IDs.
GRANT SELECT, INSERT ON TABLE public.ticket_equipment TO filestats_dashboard;
GRANT UPDATE (name, category, active) ON TABLE public.ticket_equipment TO filestats_dashboard;
