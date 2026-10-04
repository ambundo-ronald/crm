# Commission Agent workspace

Status: implemented and tested locally on dev2. Production deployment remains gated on a separate staging site and the checks below.

## Access policy

Agents use `/crm-agent`. Administrators create their restricted Website User accounts through **Settings > User Management > Agents**. These accounts receive only the Commission Agent role, without staff or ERPNext business roles. The separate staff invitation flow remains for staff. Do not assign this role to staff: its request restriction applies even when other roles are present (except the literal Administrator account).

Agents can create and follow up leads whose stored `owner` is their user. Assignment and sharing do not expand visibility. Reassignment does not change the creator; converted leads are read-only. ERPNext Lead sync preserves verified source creators; ambiguous creators require review.

Contacts are visible when created by the agent or explicitly linked through Contact.links to an agent-owned CRM Lead. Email matches do not grant access. Responses omit other links and internal history. Shared contacts are read-only; the API permits edits to an agent-created contact only while its links remain exclusively agent-owned leads and it has no deal contact reference. The initial UI supports contact creation and viewing.

The workspace supports lead details, New/Contacted/Nurture/Qualified statuses, contact creation, and creating/completing personal follow-up tasks. Custom statuses require mapping. Lists and linked contacts return 25 records; lead detail returns the latest 50 personal follow-ups. Lead-linked appointments and meetings booked before lead creation are now available; see [calendar usage](agent-calendar.md). Reminders and invitations remain CRM tasks. Finance handles commissions separately; commission calculations, earnings statements and payouts are outside this CRM scope.

## Server enforcement

An authentication hook restricts agent HTTP requests after built-in session/token authentication. Only the workspace and explicit agent/login/logout methods are allowed. ERPNext routes, generic document APIs, exports, private files and realtime authentication are denied. Public static assets remain public. Existing staff permissions continue to apply to staff.

Dedicated endpoints check stored ownership, reject unsupported fields and return explicit field projections. Guarded writes use ignore_permissions without granting broad DocType permissions. Test custom authentication hooks, proxies and installed apps on a separate staging site before deployment.

## Agent administration

Open **Settings > User Management > Agents** as Administrator or a System Manager. Agents are denied even if they have additional administrator roles; sales managers and sales users cannot administer agents here.

1. Enter the agent's first name, optional last name and email, then select **Create agent**. Existing accounts are rejected rather than converted. Creating an account sends no email.
2. Select **Send setup email** and confirm when ready. Frappe generates its expiring password setup link and directs the agent to `/crm-agent` after setup. Passwords and setup links are never displayed to administrators. Email-muted sites block this action. Repeated invitations are rate-limited; delivery depends on the site's outgoing email configuration.
3. Select **Suspend access**, enter a reason and confirm. The account is disabled, sessions and API credentials are revoked, OAuth tokens are revoked, authorization codes are removed and pending setup links are invalidated. Leads, contacts, appointments and ownership are preserved.
4. Select **Reactivate access**, give a reason and confirm. The agent can sign in again using their existing password; old sessions, API tokens and setup links stay invalid. Extra roles, a role profile or an incompatible account type must be reviewed before activation or invitation.
5. **Access history** shows creation, invitation requests, suspension and reactivation, newest first, with the acting administrator and reason. Searches and history are paginated. Concurrent account edits require a refresh before applying an action.

Audit records cannot be edited or deleted through normal document operations. This history covers actions performed through this console, not arbitrary Desk, database or third-party changes. Audit remaining roles before removing the agent role or repurposing any account. Converted leads remain read-only; reassignment alone does not change creator access.

Deployment requires `bench --site <site> migrate` to create the additive CRM Agent Access Log DocType and a frontend build. Roll back application code without deleting audit records or re-enabling suspended users. Separate Cloud staging, cross-app checks and actual outgoing email delivery remain release gates.

## Local validation

Open http://localhost:18000/crm-agent after starting the local backend.
Synthetic user: dev2.agent.a@example.invalid
Local-only password: Local-Dev2-Only-2026

The local seeding scripts require the isolated crm.localhost site with mail muted. Never deploy these fixture credentials.

Verified locally: 26 backend integration tests (18 agent/appointment and 8 administration); session and API-token denial checks; headless Edge lead/contact/follow-up and appointment booking/rescheduling/completion/navigation workflow; existing staff smoke checks. The broader CRM Lead suite remains blocked by the missing ERPNext Payment Gateway fixture (zero tests ran in that suite).

Run from the repository root with the local backend available:

```powershell
docker compose -f docker/local/compose.yaml exec -T backend bash /source/crm/docker/local/test-agents.sh
docker compose -f docker/local/compose.yaml exec -T backend bash /source/crm/docker/local/test-agent-admin.sh
node docker/local/agent-admin-browser.cjs
python docker/local/agent-smoke.py
node docker/local/agent-browser.cjs
python docker/local/smoke.py
```

See [local setup](../docker/local/README.md) and [implementation checklist](dev2-roadmap.md). Restore testing, production patch matching, cross-app staging checks and deployment approval remain open. No production data was accessed.

Administration browser validation: account creation, muted invitations, session/API-token revocation, blocked suspended login, successful reactivation with the same lead, old credentials remaining invalid, preserved administrator session, audit reasons and staff denial. The synthetic browser account is suspended after the check. Invitation generation is tested with mail delivery mocked; no real emails were sent.
