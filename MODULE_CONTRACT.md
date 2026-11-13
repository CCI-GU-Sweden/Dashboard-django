# Dashboard module contract, version 1

This guide is for contributors integrating a Django app with the dashboard. The core provides ORCID login, user approval, shared roles, administration, audit models, base templates and module overview. A module provides its own pages, URLs, data access, permissions, static files, schema setup and any collector it needs.

Modules are trusted Python packages running **inside the core Django process**, using its configuration, database connection and user/session. They are not standalone services or a security boundary. An installation can select enabled modules, but adding a new module currently requires editing core settings and rebuilding the image; there is no automatic plugin discovery or runtime installation.

Working examples: [upload statistics](https://github.com/CCI-GU-Sweden/dashboard-upload-stats), [OMERO filesets](https://github.com/CCI-GU-Sweden/dashboard-omero-filesets) and [tickets](https://github.com/CCI-GU-Sweden/dashboard-tickets). Upload statistics uses the simplest generic overview card.

## Integrate an app

1. Package the module as an installable Django app, including its templates, static files and migrations in the distribution. Give it a unique Python package name and URL names.
2. Add its package to the core environment. During development, a checkout can live at `modules/my-module/` (ignored by the core Git repository): `pip install -e ./modules/my-module --no-deps`. For a reproducible build, add a compatible pinned release or commit URL to `requirements.txt`. The Docker build does not include local `modules/` checkouts.
3. Add an opt-in or opt-out setting in `dashboard/settings.py`, and when enabled append the app and descriptor. For example:

   ```python
   DASHBOARD_EXAMPLE_ENABLED = os.environ.get('DASHBOARD_EXAMPLE_ENABLED', '0') == '1'
   if DASHBOARD_EXAMPLE_ENABLED:
       INSTALLED_APPS.append('example_app')
       DASHBOARD_MODULES.append('example_app.dashboard_module.module')
   ```

   Set `DASHBOARD_EXAMPLE_ENABLED=1` before starting Django to enable this example. Restart the process after changes. The core automatically includes the descriptor's URL configuration at the root; do not add it a second time. Avoid conflicts with existing routes and URL names.
4. Run the module's database setup and migrations as documented, then start the core and check its pages, API and overview. Build the image and run `collectstatic` before testing packaged static assets.

Enabling a module controls registration, not package installation: the current `requirements.txt` installs all listed packages even if some are disabled. Disabled modules expose no registered routes or card, and disabling does not delete their data or stop separately deployed collectors.

## Descriptor and routes

Export a `DashboardModule` object at the dotted path registered above:

```python
# example_app/dashboard_module.py
from accounts.permissions import operational_access
from dashboard.modules import DashboardModule

def overview_metrics(user):
    # Query only data this user may see; this example uses a fixed value.
    return [{'label': 'Items', 'value': '42'}]

module = DashboardModule(
    key='example', name='Example', eyebrow='My module', icon='◈',
    url_name='example_home', urlconf='example_app.urls',
    can_view=operational_access, get_metrics=overview_metrics,
)
```

`example_app.urls` is a regular Django URL configuration and must define a named landing route `example_home`. Each page and endpoint must check permissions itself. Registering a descriptor only controls the overview card and its overview API; it does not protect the module's other URLs.

| Field | Meaning |
| --- | --- |
| `key` | Unique, stable nonempty string of ASCII letters, digits, hyphens or underscores. Used in the overview URL. |
| `name`, `eyebrow`, `icon` | Display text for the card. |
| `url_name` | Name of the landing URL, resolvable without arguments. |
| `urlconf` | Dotted path of the module's Django URL configuration. |
| `can_view(user)` | Returns whether this user can see the card and request its metrics. |
| `get_metrics(user)` | Returns a JSON-serializable list of display metrics scoped to that user. |
| `contract_version` | Defaults to `1`; other versions are rejected by this core. |
| `overview_template`, `overview_script` | Optional app template and static script paths for a custom card. See the OMERO or ticket module for examples. |

The core rejects duplicate or invalid keys and unsupported descriptors when loading modules. For the generic card, return dictionaries with string `label` and `value`; an empty list shows “No summary available.” Custom cards may use additional fields, but must handle their own rendering and errors. Treat returned text as data, not HTML.

## Authentication and permissions

ORCID remains the configured login provider. The core checks that a user is authenticated, active and has an approved nonempty role before calling `can_view`. Shared helpers in `accounts.permissions` include `operational_access` (staff or admin), `researcher_access` and `is_dashboard_admin`; check their definitions and implement any finer module-specific restrictions yourself. Module views and APIs must enforce permissions independently, including ownership or group scoping for researchers. Do not assume that seeing a card grants access to every record.

The authenticated browser requests `GET /api/modules/<key>/overview` separately for each card. A successful response has the form:

```json
{"version": 1, "module": "example", "metrics": [{"label": "Items", "value": "42"}]}
```

An unknown or disabled key returns 404, an unauthorized user or provider raising `PermissionDenied` returns 403, and a Django `DatabaseError` from the provider returns 503. Other errors are not converted to 503. Metrics are queried on each request, with no shared cache or timeout contract. Do not include sensitive information unless the user is authorized to see it.

## Database and collector responsibilities

PostgreSQL is the expected deployed database. Document the module's tables, schema versions, external data sources, required runtime/collector/setup privileges, configuration and backup/upgrade considerations. Provide ordered Django migrations and/or explicit, repeatable setup commands and Kubernetes/OpenShift Jobs as appropriate. Run setup once per release using a suitable setup identity; registration itself does not run migrations or set up tables.

For a static PostgreSQL baseline, `dashboard.schema_setup.SchemaSetupCommand` provides the conservative collision check used by the existing modules. It requires a packaged `schema/baseline.sql`, declared table names and permission to create a temporary comparison schema. See the existing module commands for working examples. A check without `--apply` still creates and drops temporary comparison objects; it does not create destination tables. `--apply` creates the baseline only if there are no collisions. Partial or different schemas stop for review; this is not a general schema migration engine and does not validate runtime privileges or data. Never erase existing data automatically when enabling or disabling a module.

Keep a collector's code and example CronJob or Deployment with its module when applicable. Document how to configure and grant access to it, and whether an existing external producer must remain in use. Avoid running duplicate collectors on the same data.

## Verification and releases

Test direct page/API authorization, overview registration, scoped metrics, missing or unavailable data, and enabled/disabled behavior. Test schema creation, reuse and collision handling on disposable PostgreSQL where applicable. Check migrations and backwards compatibility against a copy of existing data. Run module frontend tests and the core's Django tests, then verify packaging and `collectstatic` in a fresh image.

Pin compatible module versions in the core and document configuration and release order. A new package version does not update a running dashboard by itself. Future module contributions should state which core revision they were tested against; the contract and shared core APIs may evolve.
