# Dashboard module contract: version 1

This is the first implementation of the core/module interface. It powers upload statistics, OMERO filesets and tickets. The contract may evolve as further modules are extracted.

Modules are trusted Python packages installed in the dashboard process. They share its Django user, session and configuration; this is not a network API or a security boundary between independently deployed services. The core authenticates users and owns account approval. Each module remains responsible for enforcing its permissions on all of its own pages and APIs.

## Registering a module

An enabled Django app exports a `dashboard.modules.DashboardModule` instance. Add the app to `INSTALLED_APPS` and the dotted path of its descriptor to `DASHBOARD_MODULES` at startup. The core loads descriptors, checks their version and unique URL-safe key, and includes each descriptor's `urlconf`. Changes require a process restart. The upload module is the first example; `DASHBOARD_UPLOADS_ENABLED=0` removes it from both lists.

| Field | Purpose |
| --- | --- |
| `key` | Stable unique URL-safe identifier, used in the overview endpoint. |
| `name`, `eyebrow`, `icon` | Short text displayed by the core on the overview card. |
| `url_name`, `urlconf` | Named module landing page and Django URL configuration. Existing module URLs remain available. |
| `can_view(user)` | Returns whether the user may see this module's card and overview metrics. |
| `get_metrics(user)` | Returns a list of dictionaries with string `label` and `value` fields, already scoped to that user. |
| `contract_version` | Defaults to `1`; incompatible versions are rejected at startup. |
| `overview_template`, `overview_script` | Optional module-owned card and script for richer displays; otherwise the core renders a generic metrics card. |

The core checks that a user is authenticated, active and approved before calling `can_view`. It checks the predicate both when showing the card and when serving metrics. A module must also enforce access for direct requests to its own views. Researcher visibility and group scoping are module responsibilities: never return unscoped statistics just because a user is signed in.

## Overview data

The core renders cards using descriptor metadata without querying their statistics. The browser independently requests `GET /api/modules/<key>/overview` for each visible card. The response is:

```json
{"version": 1, "module": "uploads", "metrics": [{"label": "Files imported", "value": "42"}]}
```

Providers return a short list of display-ready text values; specify units and time windows in the module documentation. Custom cards may consume additional fields such as a metric key and comparison text. No usernames, secrets or sensitive data should be included unless the module explicitly authorizes them. The client inserts values as text, not HTML. An unknown or disabled module returns 404, a denied user receives 403, and a database failure receives 503. A provider may raise `PermissionDenied` when a visible card needs to explain missing scoped access. Each card loads independently and displays an unavailable message on failure. The endpoint reads live data on each request: caching, timeouts and a richer typed metric format are future work.

## Release and testing

The core pins module package commits in `requirements.txt`. A new module should test registration, direct endpoint permissions, scoped data and unavailable data; the core tests the common rendering and disabled-module behavior. Verify `collectstatic` and a fresh container build, since nested local checkouts are excluded from the image. No schema change or deployment happens merely by registering a descriptor; schema ownership and setup remain separate module work.
