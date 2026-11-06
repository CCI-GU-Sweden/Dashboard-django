# ORCID login and dashboard access: proposal

Status: **discussion draft**, 4 November 2026. This describes a possible design; it does not implement authentication, change access, or authorize a database migration.

## Purpose

Let researchers sign in with ORCID to see their own CCI information, while giving staff a complete operational view and administrators control over access and storage billing rates. ORCID establishes who signed in; the dashboard decides what that person may access.

## Roles and access

Each account has one role. A newly registered account starts **Pending**, a temporary role with no operational data access until an administrator approves it. Administrators can assign Researcher, Staff, or Admin; Admin includes Staff capabilities. Role changes take effect immediately, including for existing sessions.

| Capability | Pending | Researcher | Staff | Admin |
| --- | --- | --- | --- | --- |
| Sign in, view own account and approval status | Yes | Yes | Yes | Yes |
| View OMERO storage and filesets | No | Only explicitly linked, authorized OMERO group | All, including fileset sorting | All |
| View projects, once available | No | Projects explicitly linked to them | All | All |
| Create support tickets | No | No | Yes | Yes |
| View tickets | No | Tickets explicitly linked to them | All | All |
| Manage tickets and projects | No | No | Yes | Yes |
| Prepare storage email drafts | No | No | Yes | Yes |
| View permitted operational dashboard statistics | No | Own authorized scope only | Yes | Yes |
| View OMERO Billing, price rankings, Storage Policy and collector Health | No | No | No | Yes |
| View a SEK/day indication in an otherwise authorized storage view | No | Only for their linked, authorized group | Yes | Yes |
| Change billing rates and storage policies | No | No | No | Yes |
| Approve, upgrade, downgrade, disable or delete accounts | No | No | No | Yes |

The researcher landing page could show **My storage**, **My projects**, and **My tickets**, with a clear explanation when a link is missing. Staff retain the current overview and operational tools. Researcher ticket creation should offer only appropriate fields; internal classifications, staff notes, other reporters' details and private attachments must not leak through lists, detail, history, images, exports, search, counts or notifications. Staff can respond using a separate researcher-visible message; existing events should remain internal until explicitly classified. Researcher project visibility similarly requires explicit membership and a distinction between public-to-participants and internal content. Neither visibility model exists yet.

## Sign-in and approval

1. The user chooses **Sign in with ORCID** and authenticates with ORCID. The dashboard receives an authenticated ORCID iD and creates or finds a local account keyed by that stable identifier.
2. A first-time user is Pending. They can supply a contact email and request access; the dashboard confirms receipt without exposing other users or OMERO records. Approval is manual initially, including for staff and administrators. An administrator reviews the request and assigns a role.
3. An approved researcher is linked to an OMERO account as described below. Access to personal storage is unavailable until the link is established. Ticket creation does not depend on the OMERO link.
4. A disabled or deleted dashboard account cannot sign in to the dashboard. This does not alter the person's ORCID or OMERO account. Account recovery and the first administrator must use a documented, restricted bootstrap procedure, not a public signup path.

ORCID's [Public API](https://info.orcid.org/what-is-orcid/services/public-api/) supports sign-in and authenticated iDs; confirm its terms and the institution's existing membership before choosing credentials. Use the authorization-code flow with a maintained library, registered HTTPS callback, state and appropriate PKCE/nonce protections, and validate the returned identity. ORCID also documents [OpenID Connect sign-in](https://info.orcid.org/what-is-orcid/services/public-api/orcid-as-a-sign-in-option-to-your-system/). Keep client secrets server-side and use separate sandbox and production clients. Request only the permissions needed for sign-in. ORCID authentication does **not** guarantee that an email address is returned: addresses may be private, and API visibility depends on permissions and record settings ([ORCID API FAQ](https://info.orcid.org/documentation/integration-and-api-faq/)). Do not ask users to make their ORCID email public.

Use a secure, HTTP-only, SameSite session cookie over HTTPS with CSRF protection for state-changing requests, session expiry, logout and server-side revocation. Check the current account status and role on every request. Individual identity and role checks must replace the shared-password authorization on all relevant routes, including image and export endpoints; hiding controls in the frontend is insufficient. Staff attribution should come from the authenticated account rather than a self-reported name. Protect sensitive administration with appropriate institutional MFA/assurance; confirm how that requirement can be met before deployment, since ORCID sign-in alone does not establish the required assurance for every account.

## Linking a researcher to OMERO

Use the stable OMERO account ID, not a name or email, as the stored link. An administrator can select a verified OMERO account and explicitly link or unlink it, with an audit record. Prevent an OMERO account being linked to multiple dashboard users unless an explicit, reviewed policy permits it. A researcher should be able to report an incorrect or missing link to an administrator.

Email matching can suggest a link, but a matching email alone is not sufficient proof of control. A safe optional automatic path would require a uniquely matching, independently verified dashboard email and a trustworthy current OMERO email, with a defined verification and conflict process; otherwise require administrator confirmation. Never link on a user-entered or unverified email, on a name, or on a non-unique match. Do not disclose candidate OMERO accounts to an unverified user. Handle changed emails, disabled accounts and corrections through review; audit every link change.

Researchers should see only the OMERO group explicitly linked to their account, when that link has been verified and remains authorized. A linked group can contain shared data: confirm that the researcher is entitled to see the group's data, and label group-level information as such rather than describing it as their personal bill. Verify which authoritative stable group IDs, membership, fileset associations and revocations the collector can provide, how often data refreshes and who may approve a group link. Store the verified group link separately from the OMERO account link, audit changes, and enforce it in every server-side query. If the link or current authorization cannot be verified, show storage as unavailable rather than exposing a group. Historical snapshots and shared filesets need explicit attribution rules and collection dates.

Staff may view all filesets and sort by fileset attributes. A SEK/day indication may appear in an otherwise authorized storage view, but the Billing area, billing exports and sorting or ranking groups by price are administrator-only, as are the Storage Policy and collector Health areas. Apply those restrictions to API responses and alternative sorts/exports, not just the visible tabs. A researcher may see a SEK/day indication only for their linked, authorized group; it is a group indication, not necessarily an individual charge.

## Data and authorization changes

Candidate additions, to refine after the workflow is agreed:

- Dashboard account: internal ID, unique authenticated ORCID iD, display name, optional verified contact email, role, account status and timestamps. Keep role and status distinct so an account can be disabled without losing its prior role.
- OMERO links: dashboard account ID, stable OMERO account ID and separately verified authorized group ID, verification method, linking administrator and timestamps; enforce the agreed uniqueness and group-access rules.
- Access audit: actor, action, target, timestamp and necessary before/after values for approvals, role/status changes, links and billing-policy changes. Avoid secrets and unnecessary personal data.
- Tickets: an authenticated requester account ID and explicit visibility for messages and attachments. Existing free-text reporter names do not establish ownership; do not automatically expose legacy tickets based on a name or email. Staff can review and link them.
- Projects: explicit participant membership and visibility rules, added alongside the future project implementation. The existing [project proposal](PROJECTS_PROPOSAL.md) is still a discussion draft.

Apply ownership restrictions in server-side queries for every list, detail, count, history, attachment and export; derive the caller from the session, never from a client-provided user ID. Return no information about unauthorized records, including via totals or error messages. Restrict staff and admin actions explicitly, including the existing storage-policy endpoint. Protect audit history, use least-privilege database grants, and define retention and deletion/anonymization rules before deployment. Deleting an account must revoke sessions and access without silently destroying tickets, billing history or audit records; preserve or anonymize records according to an agreed policy. Prevent the last active administrator from being removed or demoted without a recovery process.

## Rollout and validation

1. Agree on access boundaries, identity verification, retention, administrator bootstrap and project/ticket visibility. Inventory every existing route, integration and data field, including the separate support-page service token, before changing authentication.
2. Build the account, audit and approval flow against the ORCID sandbox; migrate staff to individual accounts and establish a verified admin. Support integrations keep their separately scoped service authentication.
3. Add researcher-owned tickets and explicit public replies, then verified OMERO linking and personal storage once ownership data is available. Add participant-scoped projects when the project feature is implemented.
4. Test every role against allowed and denied routes, cross-user IDs, attachments, exports and aggregates; test pending/disabled users, role changes during sessions, link conflicts, missing ownership data, CSRF, callback validation and legacy ticket handling. Verify billing changes are admin-only and audit events identify the actor.
5. Pilot in a separate environment, validate collector freshness and recovery, then phase out the shared password. Until **all** routes enforce the new access rules and the shared login is removed or isolated from researcher access, do not grant researchers access to the operational API. Plan a tested rollback that never reopens unrestricted access to researchers.

## Decisions for CCI

1. Who approves researchers and staff, and what evidence is required? Who are the initial administrators and how is recovery handled?
2. How will CCI verify and maintain the researcher's explicit group link and permission to see shared group data? How should group-level SEK/day indications and historical snapshots be labeled?
3. Can OMERO supply stable account IDs, verified emails, ownership and timely access changes to the collector? Who verifies a manual link?
4. Which ticket messages and attachments are visible to researchers, and should they be able to add replies or close tickets?
5. Who may add project participants, and which project fields or updates are visible to them?
6. What are the retention, deletion and audit requirements, and what assurance or MFA is required for staff and administrators?
