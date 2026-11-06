# Django backend, administrator tab and dynamic scaling: proposal

Status: **discussion draft**, updated 6 November 2026. This is a proposed architecture and rollout, not an implementation or a deployment specification. It builds on [ORCID login and dashboard access](ORCID_LOGIN_PROPOSAL.md), whose access rules and unresolved decisions remain applicable. Sections 10–16 add detail for the new project, shared test database, administrator-only changes, modular setup and production deployment.

## 1. Purpose and recommendation

Move the current Express backend to Django while retaining the dashboard's existing frontend and operational features. Add an administrator tab to the dashboard for approving ORCID accounts and managing access. Run the backend as a stateless, horizontally scalable service on the existing Kubernetes/OpenShift platform.

The expected initial audience is five to eight CCI coworkers, using the dashboard several times per week and usually at different times. Researchers may later access the internet-facing site after signing in with ORCID and receiving administrator approval. Actual public demand is unknown. This workload calls for a small, reliable baseline and measured scaling, not a pod per user.

**Recommended initial deployment:** one warm Django replica, CPU-based horizontal autoscaling to a conservative maximum of three replicas, and a five-minute scale-down stabilization window. Measure actual traffic, startup time, database capacity and response times before changing these values. If continuous availability during a pod or node failure matters more than the extra resources, use two minimum replicas on separate nodes where the platform supports it. A single replica can have interruptions during failure or maintenance.

Keep scale-to-zero as a later, optional experiment. It requires an independently running component that can receive a request while Django has no running pod, and the first user must wait for startup. It may save little if the required proxy, metrics infrastructure and database stay running.

## 2. Existing application and migration scope

The current application serves static HTML, JavaScript and styles from the Node container. Express exposes uploads, summary, OMERO storage and billing, ticket, and support-integration APIs against PostgreSQL. Staff access currently uses a shared-password login. The support page uses a separate backend-only service token, and its backend manages chat and webhook calls. Existing SQL migrations and collector-managed tables already contain operational data.

The Django migration should preserve the current observable API contracts, calculations, filters, pagination, CSV exports, file and image handling, error behavior and support integration until deliberately changed. The frontend can continue using its existing views; authentication and the new administrator area need frontend changes. Projects and researcher-specific data views remain separate work described in their respective proposals; moving to Django does not create them automatically.

```text
Browser -> HTTPS OpenShift Route / ingress -> Service -> Django pods
                                                   |      |-> PostgreSQL: accounts, sessions, audit
                                                   |      |-> existing statistics, OMERO and ticket tables
                                                   |      +-> ORCID: authorization-code exchange
Support backend -> service-token integration API --+
ORCID -> registered HTTPS callback ----------------+
```

Static assets may initially be served by the same deployment using a production-suitable static-file server; their packaging and caching must preserve the existing Plotly and DataTables assets. An ingress/static service can be introduced later if useful. Avoid a frontend framework rewrite as a prerequisite.

Suggested Django areas: `accounts` (identity, roles, approval and sessions), `administration` (administrative workflows and audit), `uploads`, `omero`, `tickets`, and `integrations`. Choose supported, maintained Django/Python versions and a maintained ORCID/OIDC client during implementation. A production WSGI server is adequate for the current request/response application. Use a locked dependency set and an OpenShift-compatible image that runs as an arbitrary non-root UID.

## 3. ORCID identity and access

ORCID authenticates the person; the dashboard grants permissions. Use the authorization-code flow, a registered HTTPS callback, server-side client secret, callback validation and the protections supported by the selected ORCID integration. Confirm the available ORCID client, institutional terms and actual protocol features before implementation. Use ORCID sandbox credentials in test and separate production credentials. Do not assume ORCID supplies an email address.

1. A first-time ORCID sign-in creates a local **pending** account. The user may provide contact details and submit an access request; neither sign-in nor possession of an ORCID iD automatically grants access to data.
2. An administrator verifies the request according to a CCI policy and assigns Researcher, Staff or Admin. Pending and disabled accounts cannot access operational data. Role and account status are separate fields.
3. An approved researcher sees only explicitly authorized resources, including only their explicitly linked and verified OMERO group. Verify both the stable group ID and the person's authority to see shared group data; if the link or current authorization cannot be established, storage remains unavailable. Existing free-text reporter names do not grant ticket ownership. Researcher-visible ticket messages and project membership require explicit implementation and authorization.
4. Every request checks current status and role on the server, including lists, aggregates, images, downloads, exports and policy changes. Revocation and role changes take effect for existing sessions. Staff actions are attributed to the signed-in account.

Use shared PostgreSQL-backed server-side sessions with secure, HTTP-only, SameSite cookies over HTTPS and CSRF protection, expiration, logout and revocation. All replicas share the necessary secrets and session store; sessions survive pod replacement without sticky routing. Set trusted proxy, host and HTTPS settings to match the actual OpenShift route, accepting forwarded headers only from trusted infrastructure. Require a documented institutional assurance/MFA solution for privileged access before release; ORCID alone does not establish that requirement. Bootstrap and recover the first administrator through a restricted, audited operational procedure.

## 4. Administrator tab

Add an **Administration** entry to the existing navigation, visible only to admins. Hiding the tab is a usability feature; Django independently rejects unauthorized requests. Pending users receive a separate status page, and researchers and staff cannot call administrator APIs.

The first version should include:

| Area | Administrator workflow |
| --- | --- |
| Access requests | List pending requests, view authenticated ORCID iD and submitted contact details, approve with a role or reject with an optional recorded reason. Show submission date and review outcome. |
| Accounts | Search accounts; view role, status and relevant timestamps; change role, disable or re-enable access, and revoke sessions. Confirm impactful changes and prevent accidental removal of the last active admin. |
| OMERO links | Find a verified stable OMERO account and authorized group, explicitly link or unlink them, show verification status and conflicts, and record who made the change. Do not expose candidate identities to unapproved users. |
| Equipment | Add, rename, categorize, retire and reactivate equipment. Preserve its stable ID and historical ticket references; record the change and actor. Staff may use the catalogue but cannot change it. See section 12. |
| Storage settings | Review and schedule existing effective-dated billing policy changes, with validation, history and an audit entry. Preserve existing calculation semantics. |
| Audit | Search administrative changes by actor, target, action and date. Record approvals, status and role changes, links and policy changes with time and necessary before/after values; restrict access and avoid storing secrets. |
| Operational status | Show non-sensitive service and collector health, data freshness and useful links to platform monitoring. Do not expose infrastructure secrets or raw errors. |

The tab should use focused workflows and clear success/error messages. Django's built-in admin can be a restricted internal maintenance tool, but must not become an unrestricted shortcut around authorization, business validation or audit rules. Use the same service-layer operations for the dashboard and any enabled maintenance interface, and limit direct model editing. Define who can approve staff/admin accounts, rejection/reapplication, retention, account deletion/anonymization and support contact details before release. Deletion must revoke access without silently deleting tickets, billing history or audit records.

## 5. Data and integration design

- **Existing tables:** inventory schemas, owners, grants, indexes, triggers and external writers. Map existing tables explicitly, using unmanaged Django models or carefully reviewed SQL where appropriate. Do not let Django recreate or alter collector-owned tables by default. Preserve ticket IDs, versions, event history, images, billing values and date semantics. Schema changes require coordination with the collector and support integrations.
- **New Django-owned tables:** add accounts, ORCID identity, access requests, OMERO links, audit records and sessions through reviewed, versioned migrations. Decide whether they live in the existing PostgreSQL database/schema or a separate database based on ownership and backup requirements. If separate, document cross-database consistency; do not assume cross-database transactions or foreign keys. A dedicated migration identity gets DDL rights; the runtime identity gets only the necessary data privileges.
- **Tickets and support:** preserve the separately authenticated `/api/integrations/microscope-tickets` contract, token handling, catalogue, source-event idempotency, receipt and chat callbacks. Preserve image limits and staff ticket version/conflict behavior. Test retries and duplicates across replicas. Keep service credentials distinct from browser sessions and outside client JavaScript.
- **Concurrency:** enforce unique identity/link and idempotency constraints in PostgreSQL; use transactions and locking or version checks for approvals, policy changes and ticket updates. Never rely on in-memory locks or per-pod state. Keep uploads within configured limits and avoid local pod storage for persistent data.
- **Connections:** configure bounded application connections and timeouts. Budget maximum replicas × processes/threads × possible connections per database, plus migration jobs, collectors and other clients; verify against the real PostgreSQL limit. Consider a suitable connection pooler only if needed. Autoscaling the web layer cannot fix a saturated database.

## 6. What connection changes mean for scaling

HTTP is normally a succession of short requests. A browser tab can remain open without a request; a user can disconnect without a reliable close notification; one user can generate many requests. ORCID sessions measure signed-in identities, not current workload. Scaling on the number of logged-in users or TCP connections would therefore be misleading. A completed or dropped request reduces measured **in-flight requests**; a falling request rate and CPU usage reveal reduced demand over time. Requests in progress and queueing are more useful signals than counting people.

### Initial implementation: warm baseline and CPU HPA

Set CPU and memory requests/limits from measurements, expose resource metrics through the cluster's metrics pipeline, and configure an `autoscaling/v2` HPA against the Django Deployment. An initial CPU target of **70% of requested CPU**, minimum **1**, maximum **3**, rapid scale-up and **300 seconds** of scale-down stabilization are starting hypotheses, not capacity guarantees. Kubernetes calculates CPU utilization relative to requests; missing resource requests or metrics can prevent useful decisions. Do not pin a competing controller to the Deployment's replica count.

Example: several researchers load large tables simultaneously, CPU remains above target, and the HPA observes the samples and requests more replicas. The scheduler then starts pods; traffic reaches them only after readiness succeeds. As traffic subsides and CPU remains low, the HPA can reduce replicas after its stabilization and policy rules permit. This is periodic, not instant; short requests may finish before another pod is ready. CPU can also miss database waits or slow requests, so monitor latency, error rate, active requests and database utilization. The [Kubernetes HPA documentation](https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/) explains sampling, scaling behavior and missing-metric handling.

Measure the p95 request latency and errors under representative uploads, billing, ticket and researcher workloads. If slow requests or queued work rise while CPU remains low, add a suitable ingress/custom metric such as in-flight requests or request rate, after confirming the platform can expose it to HPA. Select per-replica targets from load tests and include both CPU and the demand metric where appropriate; HPA uses the largest desired replica count across configured metrics. Exclude health probes and static traffic from the demand signal where supported. Rate limits and overload controls should protect the publicly reachable login and API; use a shared or ingress-level mechanism so limits remain meaningful across replicas.

### Optional: scale to zero and detect the first new request

If the cluster team supports it and cold-start delay is acceptable, evaluate an HTTP-aware scaler such as the [KEDA HTTP add-on](https://keda.sh/http-add-on/0.16/). The ingress must route relevant browser, ORCID callback and support-integration traffic through an independently available interceptor. It records incoming demand even with zero Django pods, triggers scaling and holds the request until a pod is ready or a configured timeout is reached. Its concurrency metric counts requests until completion; request rate smooths activity over a window. See [KEDA scaling metrics](https://keda.sh/http-add-on/0.16/user-guide/configure-scaling/) and verify the installed version and API before writing manifests.

Use a measured idle cooldown, for example 10–15 minutes initially, to avoid repeated cold starts during normal work; tune it against real usage. The first request, login callback, and support integration must tolerate image scheduling/pull, application startup and database connection delays. Establish bounded queues and timeouts, handle failures visibly, and ensure support callers retry safely with their existing idempotency keys. Test behavior when the interceptor, metrics service or database fails. Exclude health checks from idle signals, and ensure all routes actually use the interceptor; otherwise traffic may either keep the service awake or fail at zero. KEDA components remain running and add operational cost. Verify cluster permissions, supported OpenShift versions and network routes with administrators. CPU-only HPA cannot observe demand at zero pods; scale-to-zero requires an external signal and a way to receive the first request.

### Safe pod lifecycle

Provide separate startup, readiness and liveness endpoints. Readiness should indicate whether the pod can accept requests; use a bounded dependency check where useful without turning a transient database outage into restart storms. Liveness checks process health, not normal database availability. During rollout or scale-down, remove terminating pods from service, allow in-flight requests to drain, handle termination signals, and set grace and proxy timeouts based on measured longest requests. Verify the actual ingress and server drain behavior. Use rolling updates, resource requests/limits, centralized logs and appropriate disruption controls. A single replica cannot guarantee uninterrupted availability. Schedule schema migration as a controlled one-off deployment step, not simultaneously in every starting pod.

## 7. Migration and release plan

1. **Agree and inventory.** Confirm access policy, account approval, assurance, data ownership, collector grants, cluster version, operational owners and acceptable availability/cold-start latency. Document all routes and integration consumers; capture representative response fixtures and edge cases. Back up and rehearse restoration on a separate environment.
2. **Prepare Django foundation and administration.** Create the new application, image, OpenShift deployment, settings, health checks and shared sessions, with controlled access to the existing test database. Implement sandbox ORCID sign-in, pending/approval flow, restricted bootstrap, audit, role enforcement and the administrator tab. Keep the existing application available during development.
3. **Port functionality incrementally.** Reproduce uploads, OMERO, summary, tickets and service integration contracts, calculations and authorization. The test database is intended for experiments and contains no sensitive data; compare outputs there and coordinate writes to avoid confusing duplicate tickets or policy changes. Preserve the support backend's retry and callback flows. Establish ownership and permissions for existing tables.
4. **Complete the access model.** Migrate coworkers to individually approved accounts. Researcher features remain unavailable until every relevant data path has explicit ownership and visibility checks.
5. **Pilot and scale test.** Run a staff pilot against test data; exercise concurrent requests, replicas, pod replacement, failure, database connection limits, HPA behavior and support integration. Test actual deployment routing and rollback. Establish monitoring, alerts, backup/restore and on-call ownership.
6. **Cut over.** Schedule a maintenance window if needed; take a verified backup, apply reviewed backward-compatible migrations once, switch traffic at a controlled boundary, and verify login, authorization, data correctness, tickets and integrations. Remove or isolate the shared-password path before researcher access; no legacy route may bypass new checks. Keep rollback procedures and decision authority ready.
7. **Public access after acceptance.** Enable researcher access only for approved accounts after the security and privacy tests below pass and CCI approves the policy. Increase capacity only when observed demand supports it; evaluate scale-to-zero separately.

Rollback must address both application and data: retain a tested compatible old image, use expand/contract schema changes where possible, and document how writes made after cutover are preserved. A database restore can lose later writes and requires an agreed recovery point. Once researcher access exists, do not roll back to a shared-password API reachable by researchers; restrict the old service or route until equivalent authorization exists.

## 8. Acceptance and operations

- **Parity:** compare key results and edge cases for uploads, OMERO billing/filesets/policies, tickets, images, exports and integration callbacks. Verify existing IDs and records remain intact and permissions match table ownership.
- **Security:** test pending, disabled, researcher, staff and admin accounts on every API and direct URL; cross-user IDs, counts, exports, attachments and error messages; CSRF; ORCID callback validation; revocation across replicas; admin-only billing; audit; and last-admin recovery. Verify no researcher can reach the legacy shared-login service.
- **Scaling:** record baseline CPU/memory, p95 latency, errors, startup and readiness times, and DB connections. Generate realistic concurrent traffic; demonstrate scale-up, stable scale-down, session continuity and safe in-flight request handling. Test missing metrics, maximum replica limits, database failure and rolling updates. If zero is adopted, test first request, callback and integration retry at zero and from multiple simultaneous clients.
- **Operations:** alert on availability, elevated errors/latency, failed ORCID callbacks, stalled collector data, database connections, pending approvals and autoscaler/metrics failures. Use structured logs without tokens or unnecessary personal data. Define retention, backup and restore drills, patching, secret rotation and contact ownership. Run Django's [deployment checklist](https://docs.djangoproject.com/en/5.2/howto/deployment/checklist/) and `check --deploy` against production settings.

## 9. Decisions for CCI and the platform team

1. Who are the initial administrators and approvers, what verification and MFA are required, and how is access recovered?
2. What may researchers see, and can the collector provide reliable stable ownership and timely revocation? What are ticket/project visibility rules?
3. Is one warm replica with possible brief interruption acceptable, or are two replicas and node separation required? What response time and cold-start delay are acceptable?
4. Which OpenShift/Kubernetes version, metrics APIs, ingress features and KEDA components are actually available and supported? Who operates them?
5. What are PostgreSQL connection limits, existing grants, migration ownership, backup and recovery objectives, and expected public traffic?
6. How should pending requests be communicated to administrators, and what are retention, privacy, rejection and account-deletion policies?

## 10. New project and OpenShift deployment

### What “new project” means

Create a new application codebase for Django and its frontend/deployment configuration. For OpenShift, a separate **Deployment** and Service are required for the new app; a separate OpenShift **project/namespace** is an optional isolation choice, not a prerequisite. Decide with the platform team whether to put the test deployment in the existing `core-omero-test` namespace or create a new namespace such as `cci-dashboard-django-test`. Existing project creation permissions and institutional naming rules determine whether a new namespace is possible. Production gets its own isolated configuration and credentials.

Using the existing namespace is simpler for access to existing Services and Secrets. A new namespace gives clearer separation of access, quotas, policies and lifecycle, but its Secrets must be provisioned there and network policies, DNS, image-pull permissions and database access must permit cross-namespace communication. A Secret in `core-omero-test` is not automatically available in a new namespace. Do not copy production credentials into test. Neither choice requires a new PostgreSQL server.

### Objects to prepare

| Object | Purpose and implementation choices |
| --- | --- |
| Image and registry | Build an immutable Django image, including locked Python dependencies and versioned static assets. Use the institution's approved registry and an image digest for promotion. Run as a non-root, arbitrary OpenShift UID without requiring privileged SCC access; keep writable paths explicit. |
| Deployment | Runs identical Django pods behind the Service, with measured CPU/memory requests and limits, startup/readiness/liveness probes, graceful termination and rolling updates. Start with one replica. |
| Service | Provides a stable internal address and load-balances ready Django pods. The Deployment uses labels matched by the Service selector. |
| Route | Gives the test deployment its own HTTPS hostname. Restrict test access according to institutional policy, configure TLS and trusted proxy headers, and register the exact callback URL with the ORCID sandbox. A Route existing does not automatically mean it is private. |
| ConfigMap | Holds non-secret values such as environment name, allowed hostnames, feature flags and configuration paths. Inventory the current ticket catalogue mount; equipment now comes from PostgreSQL while staff and legacy aliases may still depend on that ConfigMap. Decide how to port or replace each part. |
| Secret | Holds database credentials, Django secret key, ORCID client secret and the support integration token; avoid source control, logs and image layers. Use the platform's approved secret provisioning and rotation process. Separate test and production values. |
| Job | A controlled one-off migration Job uses a migration-only credential and runs once per release before compatible application pods are rolled out. Runtime pods do not receive DDL credentials. Avoid running migrations in every replica's startup. |
| HPA | Watches the Deployment and adjusts replicas based on available metrics. Start with the bounds and stabilization in section 6 after confirming cluster metrics and quotas. |
| Service account and policies | Use a minimally privileged service account and no Kubernetes API token if the app does not need one. Define required DNS, database, ORCID and ingress connectivity under the cluster's network policy. |

Keep the new application's manifests, Dockerfile, configuration examples and migration scripts versioned in the new repository. Test and production overlays should make image, namespace, hostnames and resource differences explicit. Do not include actual credentials. Image build pipelines, registry access and promotion between namespaces depend on the institution's setup and are decisions for implementation.

### `oc` workflow and route cutover

These are illustrative commands for inspecting resources once the new project exists; substitute the actual namespace and resource names. They are not commands to create or alter anything now:

```powershell
oc project cci-dashboard-django-test
oc get deployment,service,route,hpa
oc get pods
oc rollout status deployment/dashboard-django
oc logs deployment/dashboard-django --tail=100
oc describe hpa dashboard-django
```

Use `oc apply -f <reviewed-manifest>` and the institution's deployment process once the manifests are ready. Access to creating a project may require a request to the platform team; verify it before relying on `oc new-project`. Check the cluster's installed OpenShift version and documentation. See [OpenShift projects](https://docs.redhat.com/en/documentation/openshift_container_platform/4.6/html/applications/projects) and [security context constraints](https://docs.redhat.com/en/documentation/openshift_container_platform/4.20/observability/authentication_and_authorization/index).

During development, the old test Route continues to point to the old Service and the new test Route points to the Django Service. On cutover, the implementation depends on namespace placement:

- **Same namespace:** update the existing Route's backend Service to the Django Service after validating port, TLS, hostname and callback settings.
- **Different namespace:** an OpenShift Route normally targets a Service in its own namespace. Plan an approved host transfer between Routes, an institution-supported gateway, or another supported routing approach with the platform team. Avoid assuming that a Route can directly select a Service in another namespace or that duplicate hostnames will work. Plan the transition, DNS/TLS, callback registration and rollback before cutover.

Validate the actual external hostname and route end to end, including ORCID callback and support backend traffic. Retain the old test deployment briefly for rollback and retire it after the new test service is stable. Production has a separate rollout, route switch and security acceptance gate.

## 11. PostgreSQL connection and ownership

### Existing database and proposed test arrangement

The repository states that OMERO storage and Tickets use the statistics database through `PGHOST`, `PGPORT`, `PGDATABASE`, `PGUSER` and `PGPASSWORD`; Tickets can optionally use `TICKET_PGUSER` and `TICKET_PGPASSWORD`. The documented test database is `omerofilestats`; the documented running test deployment uses `filestats_dashboard` as its database role. These are existing documentation, not a live connection check: confirm the actual host, port, database, role, grants and cluster state before configuring the new deployment. The dashboard's statistics-database credentials are distinct from credentials used by the collector to access the source OMERO database.

Connect the new Django test deployment to the **existing test PostgreSQL database**, which is intended for breaking and contains no sensitive data. This lets both applications see the same ticket, equipment and OMERO snapshot data. They may modify the same records, so announce incompatible experiments, coordinate schema changes with the collector and support backend, and avoid confusing duplicate submissions. A disposable copy can still be useful for destructive migration or rollback rehearsals, but is not a prerequisite for ordinary test work. The test and production database hosts, accounts and secrets must remain distinct.

Inventory each existing data source before finalizing `DATABASES`: uploads and statistics may need separate connections if inspection of actual deployment configuration shows different databases. Django can use database aliases if necessary, but document where each model and transaction belongs. Database hostnames may be Service DNS names or external hosts; verify connectivity, port, DNS, TLS requirements and certificate trust from the new namespace. A Kubernetes namespace, a PostgreSQL database, a schema and a PostgreSQL role are different things.

### Table ownership and migration

| Data | Likely ownership and access to confirm | Proposed treatment |
| --- | --- | --- |
| Upload statistics | Existing upload/collector data and any separate connection | Read using the minimum grants needed; verify exact tables and owners. |
| OMERO storage | Existing `group_storage_snapshot`, `omero_fileset`, `collector_run` and `storage_policy` in the statistics database | Read snapshots and collector data; only the approved policy operation may write policy rows. Preserve the collector's ownership and effective-date semantics. |
| Tickets and equipment | Existing `microscope_ticket`, events, images and `ticket_equipment` | Preserve existing records and integrations. Read and write only the actions required; equipment catalogue changes require dashboard administrator authorization. |
| Django accounts, approval, sessions and audit | New Django-owned tables | Place in an agreed schema or database, with reviewed migrations, clear ownership and backup policy. Keep audit writes transactional with changes where practical. |

Use unmanaged models or reviewed SQL for existing tables until their owners agree otherwise; Django migrations must not silently recreate or modify collector-owned objects. Inventory extensions, sequences, constraints, triggers and grants. Existing migration files are conditional alternatives based on actual schema history: do not blindly re-run `001`, `003` or `004`; inspect first and coordinate with the owner. Existing database migrations identify roles that may differ from the current dashboard login, so grants to `filestats_collector` alone do not establish that the new app can access a table.

### PostgreSQL identities and access layers

Use dedicated, clearly named database identities, separate from people and from ORCID identities. Proposed least-privilege design, subject to the database owner's review:

| Identity | Intended privileges |
| --- | --- |
| Django runtime login | Connect and use required schemas; read operational tables; write permitted ticket/session/account/audit data and only the specific equipment/policy operations the application must support. No schema ownership, superuser, role creation or DDL. |
| Migration login | Controlled deployment-only identity allowed to create and alter Django-owned objects; grants for existing shared objects remain the owner's responsibility. Do not mount it into regular web pods. |
| Collector and support identities | Keep their existing independent privileges; verify new changes do not break them. The support service token is an application credential, not a PostgreSQL user. |

Exact `CONNECT`, schema `USAGE`, table/column and sequence permissions must be derived from implemented queries, identities and ownership. Review direct grants, inherited role memberships and `PUBLIC`; granting broad table `UPDATE` defeats a narrower column restriction. New tables and sequences do not automatically receive the desired privileges unless the relevant owner configures them; PostgreSQL [default privileges](https://www.postgresql.org/docs/current/sql-alterdefaultprivileges.html) affect future objects for the creating role, not existing tables. Provide a reviewed grant script and test both allowed and denied actions; avoid generic `ALL PRIVILEGES`.

**Critical distinction:** dashboard Admin/Staff/Researcher are application roles; PostgreSQL sees the service's database login, not the individual browser user. If all requests share the runtime login and it can update `ticket_equipment`, PostgreSQL does not independently stop a staff request from issuing that update. Django must check the current user's role in every relevant write path and audit the actor. The database grants limit what the service can do overall, not what each person may do. A separate privileged database connection inside the same Django process can reduce accidental privilege use but is not an independent boundary against a compromised process holding both credentials. Stronger database-level isolation requires a separately protected service or a carefully designed database authorization mechanism with a trustworthy identity context; choose only if the security requirements justify the complexity.

For multiple databases or connections, document whether a single transaction covers the equipment/policy change and its audit record. Prefer the same database transaction where possible; otherwise design explicit reliable audit delivery and failure handling, rather than claiming atomicity across databases.

## 12. User permissions and equipment administration

The following is the proposed baseline; CCI should review individual exceptions before implementation. “Read” always means within the user's authorized scope, never a blanket right to all records.

| Action | Pending | Researcher | Staff | Admin |
| --- | --- | --- | --- | --- |
| Sign in and view approval status | Yes | Yes | Yes | Yes |
| Read own authorized storage, tickets and future projects | No | Yes, once explicitly implemented and linked | Operational view | Operational view |
| OMERO filesets and sorting by fileset attributes | No | Linked authorized group only | All groups | All groups |
| View a SEK/day indication in an authorized storage view | No | Linked authorized group only | Yes | Yes |
| View OMERO Billing, sort/rank groups by price, or export billing | No | No | **No** | **Yes** |
| View OMERO Storage Policy or collector Health | No | No | **No** | **Yes** |
| View active equipment for allowed workflows | No | Only where needed for an authorized workflow | Yes | Yes |
| View retired equipment in historical staff ticket records | No | Only if explicitly authorized in their own ticket | Yes | Yes |
| Create/manage operational tickets | No | Only when a researcher workflow is explicitly implemented | Yes | Yes |
| Add, edit, retire or reactivate equipment | No | No | **No** | **Yes** |
| Change storage policy or billing rates | No | No | **No** | **Yes** |
| Approve accounts, change roles/status, manage OMERO links | No | No | **No** | **Yes** |
| Read administrator audit records | No | No | No | Yes, subject to policy |

Define Django permission checks at the service and API level, covering direct requests, bulk operations, built-in admin, management commands and integration endpoints. A support integration token gets only its own documented ticket operations, not administrator rights. Read permissions for researchers must be scoped separately; staff ticket permissions must not imply permission to change the equipment catalogue. Changing a user role or disabling an account must take effect in existing sessions.

### OMERO access and billing visibility

The **Billing**, **Storage Policy** and collector **Health** areas are administrator-only for both reading and writing. Billing includes price-based group sorting/ranking, comparison lists, billing totals and exports; staff cannot obtain those through alternate API sort parameters, downloads or hidden frontend controls. Staff can continue to see all filesets and sort them by permitted fileset attributes. An individual SEK/day indication in an otherwise authorized storage view is acceptable, but it must not create a price-ranked list or expose the admin-only billing area to staff. Other operational overview data remains available to staff within these boundaries.

A researcher sees only the data associated with their explicitly linked, authorized OMERO group, including filesets and any permitted SEK/day indication for that group. A group may contain data shared with other people, so an administrator must verify that the researcher may view the whole group; do not assume ORCID identity, a name, email or OMERO account link alone grants group access. Store the stable group ID and verification details, audit linking/unlinking, define refresh and revocation, and apply group filters on the server to lists, details, search, counts, history, exports and aggregates. Without a verified current link, display an unavailable message and no group data. Label group-level amounts as group indications rather than personal bills.

Review combined summary endpoints and responses so that staff receive allowed storage data without admin-only billing rankings, policies or collector health; researcher responses must contain no other group's information. Server-side allowlists must prevent price sorting or ranking through query parameters, and the frontend must expose only permitted controls. Test direct requests, alternate sort keys, exports and cross-group IDs for each role; verify that unlinking or revoking a group immediately removes access, subject to the agreed authoritative refresh mechanism.

### Equipment workflow

The existing `public.ticket_equipment` contains stable `equipment_id`, `name`, `category` and `active` fields. Existing code uses the active catalogue when creating tickets, and the existing schema is designed to retain inactive entries for history. Inspect the live schema and all references before changing it; some historical ticket references may be stored as text, so do not assume that a foreign key already enforces every relationship.

1. In Administration → Equipment, an admin sees active and retired items and can add an item with a unique name, category and generated stable ID. Confirm validation and how microscope aliases are handled.
2. An admin can change the name/category or retire an item (`active = false`), with a confirmation that it will no longer be selectable for new tickets. An admin can reactivate it later. Prevent duplicates, including retired names, according to the existing case-insensitive uniqueness rule.
3. Existing tickets remain readable and retain their historical association. Define whether ticket displays should show the current name or a snapshot of the name at the time; do not silently rewrite historical data. Do not physically delete catalogue rows through the ordinary UI.
4. Write the equipment change and its audit event together in a transaction where they share a database, recording authenticated actor, action, stable ID, timestamp and necessary before/after values. Reject an unauthorized request before mutation and audit according to the agreed security logging policy.
5. Refresh catalogue reads across all replicas without a restart, or use bounded caching with a documented invalidation/freshness mechanism. Check both the dashboard and support integration immediately reflect the active list; stale cached equipment must not be accepted for a new ticket after retirement. Preserve valid historic IDs and existing aliases.

The current Express equipment write endpoints operate under the existing shared login, which does not distinguish staff from admins. Until Django's checks are implemented and the legacy route is retired or isolated, the old endpoint cannot enforce the proposed admin-only rule. Include tests for direct POST/PATCH requests, integration credentials, deactivated staff, concurrent edits, duplicate names, reactivation, historical tickets and cache behavior across pods.

## 13. Practical test-to-production sequence and open decisions

1. **Create:** new repository and separate Django test Deployment/Service/Route, in the agreed namespace. Establish network access and test-only secrets for the existing test PostgreSQL database.
2. **Foundation:** verify existing schema and grants, create reviewed Django-owned tables, implement ORCID sandbox, roles and administrator workflows, including equipment. Keep the existing dashboard available.
3. **Restore functions:** port all dashboard and support integration features against test data. Compare outputs and coordinate shared writes and schema experiments. Verify the collector and support backend still work.
4. **Exercise failures and scaling:** deliberately restart pods, test database outages, concurrent users, HPA behavior, session continuity, rights and recovery; test can be disrupted. Record measured capacities and connection limits.
5. **Test switch:** reroute the test hostname using the namespace-appropriate method above, verify callbacks and integrations, then retire the old test deployment when satisfied.
6. **Production:** validate production schema and grants separately, rehearse migration and rollback, provision separate secrets, deploy privately, pilot with staff, then switch traffic. Public researcher access follows only after role and data-isolation acceptance and removal/isolation of the old shared login.

Decide whether a separate namespace is desirable; who owns the database and can grant runtime/migration privileges; whether Django-owned tables share the existing database; which equipment categories and aliases are needed; which users may approve other admins; and which cluster resources, route controls and metrics are available. These are design decisions, not actions already performed.

## 14. Modular dashboard and `config.py`

The new project should be easy to configure for the dashboard components an installation needs. Organize the backend and frontend into well-defined modules, with a small mandatory core and optional functional areas. Configuration selects which modules are enabled; deployment tooling prepares their prerequisites. This is a design for the new project, not a script available in the current repository.

| Component | Initial relationship |
| --- | --- |
| Core | Required: application shell, configuration, health endpoints, accounts, ORCID authentication, administrator access, authorization and audit. |
| Uploads | Optional: upload statistics and its database connection. |
| OMERO storage | Optional: storage summaries, filesets, collector information and billing/policy administration; requires its statistics database and grants. |
| Tickets | Optional: ticket workflows, equipment and their tables. The support integration is a separately selectable capability that requires Tickets. |
| Projects | Future optional component; requires its own implemented models, access rules and migration plan. |
| Compute | A placeholder until its actual functionality and dependencies are defined. |

Each module should declare its purpose, dependencies, required settings and Secret **names**, database aliases, permissions, routes, navigation entries, migrations and health/acceptance checks. Prefer a small explicitly maintained module registry over dynamically importing arbitrary paths. The core must remain enabled; dependencies must be validated so, for example, the support integration cannot be enabled while Tickets is disabled. Administration displays relevant settings only for enabled modules. The same authorization and audit rules apply regardless of how a module is enabled.

### Configuration and installation lifecycle

Provide a documented `config.py` as the **single application-facing configuration entry point**, backed by explicit environment variables or a mounted, reviewed non-secret configuration file. For example, an illustrative configuration could describe `ENABLED_MODULES = ["uploads", "omero", "tickets"]` and a separate `ENABLE_SUPPORT_INTEGRATION = True`. Test and production can choose different sets intentionally; parity testing should use the same module set planned for production. `config.py` should read and validate configuration, not contain passwords or silently run shell commands on import.

To make setup easy, provide a separate, explicit and repeatable setup/deployment command that reads the same configuration, checks prerequisites, shows a plan, and prepares or verifies enabled components. Its exact name and options will be defined during implementation. The command should:

1. Validate module names and dependencies, required hostnames, database aliases, compatible schema versions and referenced Secrets; report actionable errors without displaying secret values.
2. Produce or select the versioned OpenShift manifests and migration plan for the chosen environment; use the approved image and dependencies built ahead of time. Do not download Python packages at pod startup.
3. Run approved migrations as a controlled one-off Job using the migration identity, check required external tables and grants, and stop before rollout if a prerequisite fails. Existing collector-owned tables are verified and changed only through separately reviewed migrations.
4. Deploy or update the application and HPA, wait for readiness, and run non-destructive health and enabled-module smoke checks. Do not automatically switch the public production route during initial setup.

Separate a read-only **check/plan** from a deliberate **apply** operation. Ensure retries are safe, record which image/configuration/migration versions were applied, and provide clear failure and resume instructions. Configuration is not permission to delete data or modify a shared database implicitly. New modules are bundled and pinned in the image; selecting a module activates the tested implementation rather than installing unreviewed code from the network. Keep runtime permissions and deployment/migration permissions separate.

### Enabling and disabling modules safely

For an enabled module, register its backend routes, navigation and required permissions consistently. A disabled module must not expose its data or write endpoints through direct URLs, background jobs, integrations or built-in admin; hide its navigation as well. Return a clear unavailable/not-found response without leaking data. Keep the core security system active even when optional modules are disabled.

Enabling a module is a reviewed release: validate dependencies and database permissions, apply its migrations once, deploy the same configuration to every replica and test it. Disabling one removes its interface and stops new operations, but **does not drop tables or delete existing data**. Stop or update dependent integrations explicitly; do not disable Tickets while its support integration is still expected to receive requests. Re-enabling must check schema compatibility and restore access without silently resetting data. Configuration changes should trigger a controlled rollout rather than allowing pods with different module sets to serve simultaneously for an extended period.

Avoid relying on removing a Django app from `INSTALLED_APPS` as a general-purpose switch: migrations, model references and cross-module dependencies can become inconsistent. Prefer keeping bundled Django apps and migration history consistently registered while feature flags control routes, jobs and UI; define migrations and dependencies so fresh installs and upgrades are reproducible. If a truly optional Django app must be excluded, explicitly test its migration graph and every supported enable/disable/upgrade path. Test unknown modules, missing dependencies/secrets, disabled routes, partial rollout, data preservation and re-enabling.

## 15. Easy, repeatable production deployment

The goal is to make production setup a **documented, repeatable promotion of the tested application**, with a short list of environment-specific inputs. It should not require rebuilding the application by hand or rediscovering OpenShift and database settings after every test. Production-specific checks are still necessary because real data, credentials, routes and grants differ from test.

### Deliverables in the new repository

- One immutable image built once, tested in OpenShift and promoted by digest; use environment-specific configuration and Secrets instead of editing source code or rebuilding for production.
- Versioned base manifests plus small test and production overlays, or an institution-approved equivalent such as a Helm chart. Include Deployment, Service, Route, HPA, ConfigMap references, service account and a migration Job; keep PostgreSQL's separate workload out of the dashboard release.
- `config.py`, an example module selection, a setup/verification command and a documented dependency inventory. Keep real secrets in the platform's Secret management, not in the repository or configuration examples.
- A production input sheet: namespace, image digest, hostname/TLS and ORCID callback, enabled modules, PostgreSQL Service/DNS/port/database/CA, existing schema state, Secret names, resource limits, HPA bounds and integration endpoints. Record owners, not passwords.
- Reviewed database migration/grant scripts, prerequisites and a reversible routing plan. Provide an initial-admin bootstrap and recovery runbook. Maintain a checklist of exact acceptance tests, owners and expected results.

### First production release

1. **Finish and freeze test:** exercise the intended production module set, migrations, database permissions, support integration, scaling, callback and recovery. Record the tested image digest and configuration version. Rehearse the complete production sequence against test, including a rollback.
2. **Fill in production inputs once:** use the production overlay and provision the separate production Secrets through the approved process. Confirm database network access, current schema and grants, image pull, route ownership, ORCID production callback and available cluster capacity. Create no new database server unless separately planned.
3. **Check and prepare:** run the setup command's read-only plan, compare it with reviewed manifests, take and verify the agreed production backup, and have the database owner approve applicable migration/grant steps. Apply reviewed changes via the one-off migration Job; verify results and backward compatibility with the old dashboard.
4. **Deploy privately:** deploy the exact tested image with production settings to a separate Service and restricted route. Bootstrap the first admin through the documented procedure; run health, module, database, ORCID and integration checks, and a staff pilot. Keep the existing production route serving the old application until acceptance.
5. **Switch and verify:** switch the production route using the namespace-appropriate method in section 10; verify TLS, login, API, data, equipment, policy permissions and integration callbacks. Keep the previous version available according to the rollback plan and monitor errors, latency and database connections.
6. **Open researcher access:** enable external access only once approved researcher permissions and data isolation have passed acceptance, and the old shared-login API is removed or isolated. Document the public hostname, operational contacts and recovery procedure.

Database backups do not by themselves make rollback automatic: an old image must remain compatible with any migrations, and writes since cutover must be preserved or reconciled. If an incompatible migration is unavoidable, document the maintenance window, data recovery point and explicit rollback decision. Use expand/contract migrations where possible and perform destructive cleanup in a later release. Production deployment should be straightforward and repeatable, but its actual steps and permissions must be validated with the platform and database owners.

For later releases, run the same pipeline: test a new immutable image and migration plan, promote that image, run preflight and compatible migrations, roll out, verify and monitor. Record configuration and enabled modules alongside the release so operators can reproduce it.

## 16. PostgreSQL as a separate Kubernetes workload

The current arrangement—PostgreSQL running as a **separate Kubernetes deployment/workload**, reached by the dashboard over a Service—is a good fit. Django pods can be restarted, upgraded and scaled independently while PostgreSQL keeps its own resources, persistence, maintenance and access controls. Other services such as the collector can continue using the database. Keeping them separate does not require separate clusters or separate namespaces, though either is possible.

This proposal does **not** assume the existing database uses a particular workload controller, storage class, replication system or backup method. Confirm the actual Service, persistent volume, backup/restore process and operator with the platform team. A Kubernetes StatefulSet or a supported PostgreSQL operator may be appropriate when stable storage and identity are needed, but replacing the current deployment is a separate decision; a StatefulSet alone does not provide database replication, high availability or backups. See [Kubernetes StatefulSets](https://kubernetes.io/docs/concepts/workloads/controllers/statefulset/).

Do not horizontally scale PostgreSQL by adding ordinary identical replicas behind a Service as if they were stateless Django pods: database replication and failover need a PostgreSQL-aware design. The dashboard HPA scales only Django. Set a database connection budget for the maximum web replicas, monitor database capacity and availability, retain persistent data across pod replacement, and rehearse restoration. A separate database workload still creates a shared dependency and possible single point of failure unless its own availability design addresses that.

## 17. How demand is detected in practice

The dashboard does not need to detect that each coworker has opened or closed a browser tab. The load balancer sees HTTP requests, the monitoring pipeline samples the work done by Django, and the autoscaler periodically compares the measurements with its targets. This distinction matters for a small team: an open tab may do no work for hours, while one user loading a large report can briefly create substantial work.

| Situation | What the platform observes | Expected response |
| --- | --- | --- |
| One coworker opens the dashboard | Requests arrive at the already-ready Django pod. | The pod serves them immediately; a new replica is not automatically required. |
| Several people request expensive pages together | CPU may remain above the HPA target across samples; response time and in-flight requests may also increase. | The HPA can request more pods, up to the configured maximum. New pods serve traffic only after scheduling, startup and readiness; existing pods handle traffic meanwhile. |
| A browser closes or loses its network connection | Future requests from that browser stop. An outstanding request may end promptly or may continue on the server until it completes or times out; this depends on the server and application. | CPU and traffic measurements eventually fall. After the downscale stabilization and rate rules permit, extra pods can be removed; one warm pod remains in the initial design. |
| A user returns after a quiet period | New requests reach the warm pod. | It serves them immediately, and sustained demand can trigger scaling again. |
| An optional scale-to-zero configuration is idle | No Django pod exists to observe CPU or receive a request. | An always-available HTTP interceptor must detect and temporarily hold a new request while a pod starts, or fail it after a bounded timeout. |

For illustration, if one pod has a CPU request of 500 millicores and averages 350 millicores over the relevant samples, its utilization is 70% of its request. A sustained average around 700 millicores would be 140%; the HPA's basic ratio suggests two replicas at the 70% target, subject to its tolerance, sampling, readiness, policies and maximum. This is a calculation example, not a proposed resource request or a promise of response time. The HPA evaluates periodically, and the actual time to add capacity also includes metrics delay, scheduling, image pull and application startup. Measure these times on the real cluster.

The five-minute downscale window is a **stabilization window**, not a timer that starts precisely when the last user closes the site. The HPA considers previous recommendations in the window, and low demand must persist long enough for its rules to allow a reduction. A period of brief low load does not by itself remove the warm replica. Test the observed timing with representative traffic; tune the window only after comparing responsiveness, pod churn and resource use. See the [Kubernetes HPA behavior documentation](https://kubernetes.io/docs/concepts/workloads/autoscaling/horizontal-pod-autoscale/).

For the initial rollout, record the time from sustained load to a ready additional pod, and from sustained low load to removal of an extra pod. Also monitor p95 latency, errors, CPU, ready replicas, HPA conditions, database connections and query time. Run a separate test where the database is slow: adding Django pods may increase pressure on the same database, so a rising request count or latency alone is not proof that more web replicas will help. Alert when the HPA has reached its maximum or metrics are unavailable, and give the operator a documented way to inspect and adjust the limits.

If scale-to-zero later becomes desirable, verify the cluster version and supported scaling components first. [Kubernetes documentation for v1.37](https://kubernetes.io/blog/2026/09/02/kubernetes-v1-37-hpa-scale-to-zero-beta/) describes HPA scale-to-zero with suitable external or object metrics; an HTTP request still needs a separate buffering layer because a Kubernetes Service does not hold requests while no pods are ready. The [KEDA HTTP add-on](https://keda.sh/http-add-on/1.0/) is one possible implementation to evaluate with the platform team. Compare its always-running overhead and measured cold starts against the cost of keeping the single warm pod before deciding.
