# Modular dashboard: proposal

Status: **discussion draft**, 11 November 2026. This document describes a proposed architecture and migration, not an implemented deployment. It complements [the Django backend proposal](DJANGO_BACKEND_PROPOSAL.md) and [the ORCID login proposal](ORCID_LOGIN_PROPOSAL.md).

## 1. Purpose

Split the dashboard into independently maintained modules so that an institution can install only the features it needs, and so future contributors can add features without modifying every existing module. For example, an installation could run the core and OMERO fileset observation without upload statistics or tickets.

The initial target is four repositories, packaged as a single Django deployment with a shared interface and login. Separate repositories do not require separate web services or databases.

## 2. Proposed repositories

| Repository | Responsibility |
| --- | --- |
| **Dashboard-django** (core) | Django project, authentication, users, shared roles and administration, navigation, base templates, audit interface and deployment composition. |
| **dashboard-upload-stats** | Upload statistics pages, endpoints, data access and the collector deployment or CronJob needed by this module. |
| **dashboard-omero-filesets** | OMERO fileset observation, storage overview, history, group information and the collector deployment or CronJob. Billing and storage policy remain here initially. |
| **dashboard-tickets** | Ticket pages, endpoints, permissions, assignments, tags and ticket data integration, with collector or integration deployment manifests where needed. |

Each feature repository should provide an installable Django app with its own code, URLs, templates, static files, tests, configuration reference and release notes. It should also document its PostgreSQL schema requirements and provide the relevant Kubernetes/OpenShift manifests. A module with no collector should document that fact instead of deploying an unnecessary workload.

The core selects and composes enabled modules. Feature modules depend on a small documented core interface and should not import one another. Each module supplies its navigation entries, URLs, permissions and optional home-page cards through that interface. Disabled modules should expose neither pages nor endpoints, and should not appear in navigation.

An OMERO-only installation still needs the core, PostgreSQL and a compatible fileset data source/collector, but does not need the upload or ticket modules. Future modules should use the same contract.

### Local checkouts

The module repositories can be checked out under an ignored `modules/` directory in the core working tree. Each retains its own Git history, remote, branches and commits; the core's `.gitignore` would keep those checkouts out of its commits. This is a local development layout, not a mechanism for distributing the modules: a fresh core checkout does not include them, and the core's build must explicitly install selected module versions. CI and container builds need the same explicit dependencies. If coordinated version pinning in Git is desired later, submodules are an alternative but add setup and update steps.

The first upload app extraction is published in [dashboard-upload-stats](https://github.com/CCI-GU-Sweden/dashboard-upload-stats). The core installs a commit-pinned package in its normal build and can disable its routes and overview card. A read-only preflight checks the existing upload table; complete schema setup remains to be implemented.

## 3. Optional billing

Keep billing within the OMERO fileset repository for now, but isolate its views, calculations, templates, permissions, configuration and data requirements from basic fileset observation. `DASHBOARD_OMERO_BILLING_ENABLED=0` disables billing in the dashboard independently of the rest of the module. The collector has its own configuration and may still require billing-related schema.

When disabled, billing navigation, pages, API endpoints and billing-specific dashboard data must be unavailable. When enabled, billing remains subject to explicit server-side authorization. The fileset module should work without billing configuration or billing-only database objects when billing is disabled. Design the boundary so billing could become a separate module later without committing to that split now. Storage policy scope and its relationship to billing should be settled during detailed design.

## 4. Authentication and authorization

The core owns accounts, sessions, login, account approval and shared administration. ORCID remains the main entry point. Keep provider configuration and identity handling open to additional SSO providers later, without making another provider a prerequisite for the first release. Any future account linking must be explicit and verified; matching an email address alone should not merge identities.

Modules define and enforce their own permissions using the core's documented authorization interface. Shared roles can simplify administration, but permissions must be checked on the server for pages, APIs, exports and data access. Enabling a module does not automatically grant users access to its data. Existing account approval and audit requirements continue to apply.

## 5. PostgreSQL, collectors and schema lifecycle

PostgreSQL is the expected database. An installation may initially use one PostgreSQL database for the core and enabled modules; the ownership and permissions of each set of tables must still be explicit. Separate connections or databases can be considered later when required.

Each module documents its data sources, required tables, supported schema versions, database privileges and whether it reads or writes collector-owned data. Where it needs a collector, it provides a versioned Kubernetes/OpenShift **CronJob** for scheduled collection or a **Deployment** for a continuously running collector, as appropriate. Manifests should describe configuration, secrets by reference, service accounts, resources and health or failure monitoring; credentials must not be committed. The deployment composition enables only the workloads for selected modules. Collector access to OMERO or another source remains an installation prerequisite.

Collectors should be maintained with their corresponding modules. The existing [OMERO storage collector](https://github.com/CCI-GU-Sweden/Omero-storage-collector) already provides collector code, schema and Kubernetes manifests; plan its migration into the fileset module without disrupting existing deployments. Its repository also contains ticket schema migrations, so those must be inventoried and assigned to the ticket module during the split. The upload statistics module reads an existing external data source; its README documents the current producer. Decide how to provide a module-owned schema and optional aggregation without disrupting existing writers.

Enabling a module must include a **versioned schema check and setup step** before its web endpoints or collector start. Run this as an explicit, once-per-release migration/setup Job, rather than independently in every web or collector replica. The module supplies SQL migrations or another versioned migration mechanism, including any Django migrations it owns. The check should:

1. Inspect schema version and required objects, including compatibility with existing collector or legacy tables.
2. Create missing module-owned tables and apply compatible, ordered migrations when appropriate.
3. Reuse compatible existing tables and data; report a clear error and stop if ownership, permissions or compatibility cannot be established.
4. Identify obsolete or incompatible objects and propose the necessary migration or removal. **Do not automatically erase tables or data on enablement.** Any destructive reset or removal must be an explicit operator action with a reviewed plan and a verified backup/restore procedure.

Make setup repeatable, coordinate concurrent runs, and fail the release safely on partial or incompatible changes. Use a dedicated migration identity with only the privileges it requires; web and collector identities should have separately scoped runtime privileges. Disabling a module stops its routes and workloads but retains its tables and data unless an operator explicitly chooses a separate removal procedure. Document upgrade, rollback, backup and restore behavior for each module, including collector-owned tables and schema versions.

## 6. Module contract and releases

The initial versioned registration and overview contract is documented in [MODULE_CONTRACT.md](MODULE_CONTRACT.md). It covers module URLs, card metadata, authorization and simple overview statistics; audit events, health reporting and broader configuration remain to be specified. Modules should declare their package and database dependencies. Pin compatible versions in the deployment so each installation can reproduce its build and upgrade deliberately.

Start with deployment-time configuration of enabled modules. A graphical plugin marketplace or runtime installation system is not required. Document how an operator installs a module, configures its collector, runs its setup Job, enables it, upgrades it and disables it.

## 7. Migration from the current project

Upload statistics, OMERO fileset and ticket views, data access and overview integration are packaged separately. Ticket models have moved to the ticket package with state-only migrations that preserve their legacy tables; historical core migrations still create those tables for fresh installations. Verified OMERO memberships remain in the core `accounts` app. Existing collector and ticket tables also have their own lifecycle. The split must preserve current data and working routes while making ownership explicit.

1. **Define boundaries and inventory data.** Agree on the module contract and map tables, collectors, permissions, dependencies and existing deployments. Identify billing-only objects and operations.
2. **Separate apps within the current repository.** Move feature code, templates and static assets behind module boundaries while keeping the existing deployment working. Add conditional routes and navigation.
3. **Pilot with upload statistics.** Package the app, its schema checks and its collector manifest. Test both a full installation and one where it is absent.
4. **Extract OMERO filesets.** Include the collector and independently switchable billing capability. Verify an installation with only core and filesets, both with and without billing.
5. **Extract tickets.** Move ticket features and integration carefully, including ticket-specific models and SQL references to `accounts_*` tables. Test data-preserving migration on a restored database copy.
6. **Publish and operate the four repositories.** Pin compatible releases, document composition and test fresh installations, upgrades, disabling modules and restore procedures.

Django model moves can alter migration state and default table names. Preserve existing tables and relationships through an explicit reviewed migration strategy; do not assume moving Python files preserves the database. Preserve current URLs and API behavior where feasible during transition. No collector-owned tables should be changed without confirming ownership and compatibility.

## 8. Remaining design decisions

- Define the concrete module registration format, permissions interface and version compatibility policy.
- Inventory existing collectors and decide which repository owns each image, manifest and schema, especially where a collector serves more than one module.
- Specify compatible existing PostgreSQL schema versions and how setup verifies them without modifying external owners' tables.
- Decide which storage-policy functions depend on billing and how they behave when billing is disabled.
- Choose the future SSO integration and identity-linking process when a second provider is needed.
