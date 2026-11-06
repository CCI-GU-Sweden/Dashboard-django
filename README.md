# Dashboard-django

This repository contains the Django migration described in [DJANGO_BACKEND_PROPOSAL.md](DJANGO_BACKEND_PROPOSAL.md) and [ORCID_LOGIN_PROPOSAL.md](ORCID_LOGIN_PROPOSAL.md). The existing Express dashboard remains separate. The in-progress Django port has staff-only upload statistics, fileset and ticket inventories, ticket creation and status/priority updates, and admin-only read-only billing. It does not yet reproduce all legacy filters, exports, ticket assignments or image uploads, storage-policy changes, collector health or support integration. Researcher-owned records are not exposed until ownership and visibility are implemented.

## Run locally

Use Python 3.12 or newer. In PowerShell:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DJANGO_DEBUG = '1'
$env:DJANGO_SECRET_KEY = 'local-development-only'
python manage.py migrate
python manage.py test
python manage.py runserver
```

Register an [ORCID sandbox](https://info.orcid.org/documentation/integration-guide/orcid-sandbox/) public API client and set `ORCID_CLIENT_ID` and `ORCID_CLIENT_SECRET` in the environment. Register `http://localhost:8000/accounts/orcid/login/callback/` as its callback, and use the same hostname in the browser. The sandbox is the default; `ORCID_ENVIRONMENT=production` selects production. Use separate credentials and an HTTPS callback for production. Never commit secrets.

After the intended first administrator signs in, an authorized operator can verify the ORCID iD and run `python manage.py bootstrap_admin <orcid-id>`. Run only one bootstrap command at a time. It refuses to run while an active administrator exists. Subsequent approvals and account changes are available in Administration and audited. An empty role represents pending approval; disabled accounts cannot sign in.

Outside local debug mode set `DJANGO_SECRET_KEY`, `DJANGO_ALLOWED_HOSTS` (comma-separated), `DJANGO_CSRF_TRUSTED_ORIGINS` where needed, and PostgreSQL settings `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER` and `PGPASSWORD`. Configure HTTPS and trusted proxy settings for the actual environment. Run `python manage.py check --deploy` before deployment.

The included Dockerfile runs Gunicorn as a non-root user; migrations must run separately, once per release. `deploy/hpa.example.yaml` is a starting HPA for a Deployment named `dashboard-django`, not a complete deployment. Configure CPU requests on the Deployment, cluster metrics, readiness/liveness probes (`/health/ready/` and `/health/live/`), resources, secrets, Service and ingress before use. HTTPS redirects exempt only those probe paths. Set `DJANGO_TRUST_PROXY_HTTPS=1` only when a trusted ingress strips client-supplied `X-Forwarded-Proto` and sets it itself. Test graceful shutdown and scale behavior on the actual platform.

For the OpenShift build, migration, application and autoscaling manifests and a web-console walkthrough, see [deploy/openshift/README.md](deploy/openshift/README.md).

This is an early implementation, not a production release. Institutional administrator MFA/assurance, recovery, production proxy configuration, backups, full data authorization, and security review remain required before public access. The operational views read existing collector and ticket tables using the configured PostgreSQL connection; no Django migration changes those existing tables.

