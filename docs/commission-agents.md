# Commission Agent workspace

Status: implemented and tested locally on dev2. Production deployment remains gated on a separate staging site and the checks below.

## Access policy

Agents use `/crm-agent`. Create a Website User and assign only the Commission Agent role, without staff or ERPNext business roles. The existing staff invitation flow does not onboard agents yet. Do not assign this role to staff: its request restriction applies even when other roles are present (except the literal Administrator account).

Agents can create and follow up leads whose stored `owner` is their user. Assignment and sharing do not expand visibility. Reassignment does not change the creator; converted leads are read-only. Imported creator mapping is still pending.

Contacts are visible when created by the agent or explicitly linked through Contact.links to an agent-owned CRM Lead. Email matches do not grant access. Responses omit other links and internal history. Shared contacts are read-only; the API permits edits to an agent-created contact only while its links remain exclusively agent-owned leads and it has no deal contact reference. The initial UI supports contact creation and viewing.

The workspace supports lead details, New/Contacted/Nurture/Qualified statuses, contact creation, and creating/completing personal follow-up tasks. Custom statuses require mapping. Lists and linked contacts return 25 records; lead detail returns the latest 50 personal follow-ups. Lead-linked appointments and meetings booked before lead creation are now available; see [calendar usage](agent-calendar.md). Reminders and invitations remain CRM tasks. Finance handles commissions separately; commission calculations, earnings statements and payouts are outside this CRM scope.

## Server enforcement

An authentication hook restricts agent HTTP requests after built-in session/token authentication. Only the workspace and explicit agent/login/logout methods are allowed. ERPNext routes, generic document APIs, exports, private files and realtime authentication are denied. Public static assets remain public. Existing staff permissions continue to apply to staff.

Dedicated endpoints check stored ownership, reject unsupported fields and return explicit field projections. Guarded writes use ignore_permissions without granting broad DocType permissions. Test custom authentication hooks, proxies and installed apps on a separate staging site before deployment.

To suspend an account, disable the User and clear its sessions using administrator tools. Audit any remaining roles when removing the agent role or repurposing an account. A dedicated suspension/audit workflow is still pending.

## Local validation

Open http://localhost:18000/crm-agent after starting the local backend.
Synthetic user: dev2.agent.a@example.invalid
Local-only password: Local-Dev2-Only-2026

The local seeding scripts require the isolated crm.localhost site with mail muted. Never deploy these fixture credentials.

Verified locally: 15 backend integration tests; session and API-token denial checks; headless Edge lead/contact/follow-up and appointment booking/rescheduling/completion/navigation workflow; existing staff smoke checks. The broader CRM Lead suite remains blocked by the missing ERPNext Payment Gateway fixture (zero tests ran in that suite).

Run from the repository root with the local backend available:

```powershell
docker compose -f docker/local/compose.yaml exec -T backend bash /source/crm/docker/local/test-agents.sh
python docker/local/agent-smoke.py
node docker/local/agent-browser.cjs
python docker/local/smoke.py
```

See [local setup](../docker/local/README.md) and [implementation checklist](dev2-roadmap.md). Restore testing, production patch matching, cross-app staging checks and deployment approval remain open. No production data was accessed.
