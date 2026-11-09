# Moving the dashboard to the existing test address

## Test cutover status (2026-11-09)

The test cutover has been applied in `core-omero-test`. The bookmarked Route
remains in place with the IP allowlist and trusted forwarded-header replacement.
`maintenance-nginx` mounts `maintenance-nginx-dashboard-django` and forwards
the dashboard virtual host to `dashboard-django:80`. The old `dashboard-test`
deployment is retained at zero replicas. The shared scheduler now manages
`dashboard-django` and accepts any positive replica count during the working
window. A live scheduler run was verified with two Django replicas; the HPA
minimum was restored to one afterward. The after-hours transition still needs
an end-to-end scheduled test.

The sandbox ORCID identities were renamed to `orcid-sandbox`, their users were
deactivated and all sessions were cleared by the audited identity-cutover Job.
The rows and their audit/group/ticket relationships remain; new real users must
be verified and linked to their own tickets explicitly. The authenticated real
administrator was bootstrapped and confirmed access. Production ORCID values
come from `dashboard-app`, while the existing Django signing key and database
references remain in place. The local database backup was archived and listed
successfully; this is not a full restore test.

The deployed image was built in OpenShift build 20 from Git commit `d6018d5`.
The old deployment still has its original image trigger: ensure it stays scaled
to zero. The temporary gateway canary and one-off test Jobs are separate
resources. The `dashboard-django-config` ConfigMap retains sandbox values for
the one-off isolation Job; explicit web-container environment variables override
the hostnames, ORCID environment and ORCID credentials. Do not remove these
overrides while production identities are in the database.

## Background and production checklist

The following is the cutover rationale and a reusable checklist. The existing
`dashboard-test-core-omero-test.apps.k8s.gu.se` Route currently points to
`maintenance-nginx`, which forwards dashboard requests to the old
the Django Service through the gateway. Keep the old deployment, image and route
configuration available until the new deployment and rollback have been tested.

The live `service-schedule` CronJob controls several applications. It runs every
five minutes in `Europe/Stockholm` and starts Django if it is at zero during
the configured window; it does not reset positive replica counts. It scales
Django to zero outside the window.
The current window is Monday–Friday, 09:00–18:00. The two older
`scale-omero-test-*` CronJobs are suspended. Recheck live configuration before
cutover; do not apply a stale copy over the shared scheduler.

## Build and credentials

Use `CCI-GU-Sweden/Dashboard-django` as the source repository. The existing
`dashboard-django` BuildConfig points there; `dashboard-test` still builds the
old Express repository and its image trigger can replace its image. Do not copy
the Django repository over `Dashboard`, replace the old build's source, or
delete either deployment to transfer data. The Django application already uses
the shared PostgreSQL database, so switching the gateway does not require a
copy of the ticket or OMERO data.

The BuildConfig tracks `main` and has an OpenShift GitHub webhook trigger using
the `dashboard-django-github-webhook` Secret. To complete the integration, copy
the GitHub webhook URL from **Builds → BuildConfigs → dashboard-django** into
the repository's **Settings → Webhooks**, choose `application/json` and push
events. The URL contains a secret: do not paste it into chat or a repository.
GitHub must be able to reach the cluster API and pass its TLS checks. Confirm
the webhook delivery and a subsequent build from the intended commit; the
OpenShift trigger alone does not create a GitHub webhook.

For `core-omero-test`, the GitHub webhook was added on 2026-11-09 and GitHub
reported a successful delivery. Its URL is a credential: do not publish it.

Each successful push produces a candidate image. Verify its source revision and
retain the digest. Do not enable an automatic deployment trigger because database
migrations, compatibility and release checks must happen before an image serves
users. Manual promotion of a tested immutable digest is the release gate.
Previous binary builds may contain local changes and are not evidence that a
particular Git revision was built.

The production-ORCID Secret `dashboard-app` has `ORCID_CLIENT_ID` and
`ORCID_CLIENT_SECRET`. Django expects `DJANGO_SECRET_KEY`, not
`DASHBOARD_SECRET_KEY`; the latter being empty is harmless only if it is not
used. The existing `dashboard-django-app` Secret has a `DJANGO_SECRET_KEY`.
Reference that existing key explicitly via `secretKeyRef` and reference the two
production ORCID values from `dashboard-app` via separate `secretKeyRef`
entries; do not use `envFrom` with both Secrets because duplicate names may
override each other. Never display, commit or copy the key into documentation.
Keep the existing signing key stable during the test cutover; rotating it logs
out sessions and affects signed data. Use a separately generated signing key
and independently managed credentials for a separate production deployment.

Register the exact callback
`https://dashboard-test-core-omero-test.apps.k8s.gu.se/accounts/orcid/login/callback/`
with the production ORCID client. Keep sandbox credentials for rollback in a
separate Secret. Public ORCID client credentials belong to their registering
individual; establish an institutional ownership and recovery process.

## Identity and database safety

Sandbox and production identities use the same `orcid` provider in the current
application. Switching the ORCID server while retaining sandbox social accounts
may authenticate a production user against a sandbox identity with the same
identifier. Never simply switch `ORCID_ENVIRONMENT` on the shared account tables.

Before switching, agree and test an explicit identity isolation procedure:
preserve a recoverable backup, isolate or retire sandbox social identities and
their sessions, prevent sandbox users retaining privileged access in the live
identity namespace, and account for audit history, verified groups and ticket
links. Do not delete users casually: audit and ticket relations protect them.
The first real administrator must first complete a successful production ORCID
login, then an authorized operator verifies the iD and uses a serialized,
audited bootstrap/promotion procedure. The existing `bootstrap_admin` command
only works if no active administrator exists. Do not promote an unauthenticated
identifier or infer an account match from name or email. Test the process and
rollback in isolation before touching the shared database. Production and test
account/session state must be isolated even if both authenticate against the
production ORCID registry.

An existing `postgresbackup` CronJob reports a past successful run, but this is
not proof that the latest backup covers all relevant tables or can be restored.
Verify a current backup, its storage and a restore procedure with the database
owner. Ticket and storage changes are writes to shared operational tables.
Reverting an image or route does not revert database changes; never restore a
shared database blindly over writes made by other applications.

## Gateway and scheduled autoscaling

1. Add the old hostname to Django's allowed hosts and trusted CSRF origins;
   keep the probe hostname and any other deliberately supported host. Enable
   production ORCID only after identity isolation and credentials are ready.
2. Update the dashboard server in `maintenance-nginx` to forward to the Django
   Service and preserve the original Host and trustworthy HTTPS proxy header.
   The currently observed NGINX configuration forwards to `dashboard-test:8080`
   and does not explicitly set these headers. First make the OpenShift router
   replace client-supplied forwarded headers, then explicitly pass the trusted
   scheme and original host through NGINX. Verify the actual proxy chain,
   redirects, CSRF checks, request-size limits, and the maintenance page.
   Merely changing `DASHBOARD_TARGET` in the shared ConfigMap is not sufficient:
   the observed NGINX server configuration has a hard-coded upstream.
3. Modify only the dashboard part of `service-schedule`: outside the window,
   enable its maintenance flag and intentionally scale Django to zero; inside
   the window, bring it back to at least one, wait for readiness, and then
   remove the flag. Do not reset it to one on every run while the HPA manages
   active replicas. Explicitly verify HPA scale-to-zero behavior and restart on
   the cluster, including the transition at both ends of the schedule and a
   weekend; the HPA has a minimum of one and uses CPU, not connected users.
   Preserve the OMERO and Flask portions unchanged. Coordinate concurrent
   scheduler runs and rollouts.
4. Maintain the existing Route TLS and IP allowlist, and test allowed and denied
   networks. Ensure all reachable Routes to the application have equivalent
   restrictions and scheduling behavior; otherwise the separate Django route
   can bypass the maintenance page. Keep a restricted operator recovery path.
5. Test login with the real administrator, pending/approved coworker, ticket
   creation, storage, health probes, scaling and maintenance behavior. Record
   image digest, build revision, secret references, schedule, backup and
   rollback details. Switch traffic only after these checks are ready.

## Rollback and later production

Retain the old Route/gateway/scheduler configuration, old image digest, sandbox
credentials and database backup securely. Roll back the gateway and dashboard
scheduler together, verify maintenance behavior and whether database changes
are compatible. A return to sandbox ORCID also requires restoring or isolating
the appropriate identity namespace; switching credentials alone is unsafe.

For a future production deployment, use an independently reviewed hostname,
callback, Secrets, database and account/session isolation, backup and restore
plan, access policy and resource limits. Verify the image against production
data compatibility and run any migrations once, separately from web startup.
Keep automatic build separate from controlled deployment, and record the exact
Git revision and image digest. Review operational security, monitoring,
administrator recovery and authorization before opening public access.
