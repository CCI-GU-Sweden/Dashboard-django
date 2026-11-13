# Dashboard-django

This repository is the core of the CCI Django dashboard. It provides ORCID login, account approval, shared roles, administration and the interface for optional feature modules. Feature code is maintained in separate repositories and installed into the same Django application.

Upload statistics is installed from a pinned commit of [dashboard-upload-stats](https://github.com/CCI-GU-Sweden/dashboard-upload-stats) by `requirements.txt`; installing requirements requires access to GitHub as well as the Python package index. The module is enabled by default; set `DASHBOARD_UPLOADS_ENABLED=0` before starting Django to remove its pages, APIs and overview card. The app reads the existing uploader-owned PostgreSQL `imports` table. With the module enabled, `python manage.py check_upload_schema` checks that the table and required columns are readable without changing data. See the module README for the existing producer and optional baseline setup. Restart all web processes and rebuild/collect static assets when changing the setting.

For local multi-repository work, module checkouts can live under `modules/`, which the core ignores. These checkouts have separate Git histories and are not included in a core clone or container build. To develop the upload module alongside the core, install the checkout into the same virtual environment with `pip install -e ./modules/dashboard-upload-stats --no-deps`; reinstall the pinned requirements to return to the published version. Run its frontend tests from the module repository. Production builds use the pinned package, not the nested checkout.

The [module contract](MODULE_CONTRACT.md) explains how to develop and register a module, enforce permissions, provide overview statistics, and document database and collector setup.

The explicit `setup_upload_schema`, `setup_omero_schema` and `setup_ticket_schema` management commands check their PostgreSQL baselines without creating destination tables by default; pass `--apply` to create missing baselines after collision checks. They require a setup identity able to create a temporary comparison schema and objects in `public`. Existing complete, structurally matching baselines are reused; partial or different schemas stop for operator review. Tickets additionally require the paired Django migrations, restricted helper setup and runtime grants, as documented in the module README. These commands do not run automatically during `migrate`, grant runtime privileges, or erase data. See each module's README and example setup Jobs before use.

OMERO fileset observation is installed from a pinned commit of [dashboard-omero-filesets](https://github.com/CCI-GU-Sweden/dashboard-omero-filesets). Set `DASHBOARD_OMERO_ENABLED=0` before startup to remove its routes and overview card. To keep observation but disable billing, set `DASHBOARD_OMERO_BILLING_ENABLED=0`; this also hides billing-dependent policy management and email drafts. Verified-group memberships and audit events remain in the core. The existing collector and database remain unchanged, and the collector may still require its own billing schema.

Ticket views, routes, interface, data access and ticket-specific models are installed from a pinned commit of [dashboard-tickets](https://github.com/CCI-GU-Sweden/dashboard-tickets). Set `DASHBOARD_TICKETS_ENABLED=0` before startup to disable its routes and overview. The paired core and module migrations transfer model state while preserving the existing `accounts_*` tables and content-type IDs. Historical core migrations still create those five empty tables on a fresh database even if tickets are disabled. Ticket table and helper setup are explicit module commands; see the module README for ordering and required grants.

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

The operational views use the configured PostgreSQL connection and existing collector data. Plan releases, backups, recovery, access controls and security review for each installation; test migrations and module compatibility before deployment.

