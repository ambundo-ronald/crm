# Restricted Agent access

Status: implemented and validated locally on dev2. Production is unchanged; a separate staging site remains required before release.

## Invite and access

Use **Settings > User Management > Invite User**, enter the email and choose **Agent** under **Invite As**. Manager and Sales User retain their existing behavior. Agent invitations create restricted Website Users and direct them to `/crm`, using the original CRM interface. Existing accounts are rejected rather than silently converted to agents. No separate agent workspace is required; old `/crm-agent` bookmarks redirect to `/crm`.

Agents use Leads, Contacts, Tasks, My Day and My Calendar. They can create leads and contacts, update permitted fields, add follow-up tasks and book personal appointments, including meetings before a lead exists. Their account menu offers Light, Dark, System and logout.

## Access policy

- Leads are scoped to stored `owner`, not mutable sales owner, assignment or sharing. Converted leads are read-only.
- Contacts are visible if created by the agent or explicitly linked to a lead they own. Shared contacts are read-only; unrelated links and internal fields are omitted.
- Tasks must be created by the agent and reference a lead they own. Appointments are personal private Events, unlinked or linked to an owned lead.
- Agents cannot access ERPNext, Desk, deals, organizations, administration, exports, bulk imports, private files, other users' records or unrestricted APIs.

The server applies default-deny request restrictions even when extra staff roles are accidentally added (the literal Administrator account is exempt). Frontend navigation is not the security boundary. Native CRM API requests use a restricted compatibility layer with explicit field projections, scoped queries/counts and validated writes. Staff calls retain their original handlers, including earlier installed-app overrides. If another app replaces the restricted handler, agent requests fail closed.

Agent list customization, custom form scripts, attachments, email activity, sharing and realtime subscriptions are unavailable. Agent activity contains scoped creation, tasks and appointments; it does not expose internal staff history. Guarded operations do not grant broad DocType permissions.

## Administration and existing accounts

**Settings > User Management > Agents** remains an administrator lifecycle console, with **Invite an Agent** linking to the normal invitation screen. It is not a separate interface for agents.

Administrators can suspend/reactivate access and view immutable access history. Suspension revokes sessions, API/OAuth credentials and pending setup links while preserving records and ownership. Reactivation requires a compatible restricted account; revoked credentials stay invalid. Setup email actions require confirmation, working outgoing mail and an unmuted site. Audit history covers these console actions, not arbitrary database or third-party changes.

Run `bench --site <site> migrate` and rebuild frontend assets on deployment. Migration adds the **Agent** role, migrates existing **Commission Agent** memberships and updates their landing route without changing record ownership. Both role names remain recognized by the request guard for compatibility. Review other roles before repurposing an account. Do not delete audit records or automatically reactivate suspended accounts during rollback.

## Local validation

Local site: http://localhost:18000/crm. Synthetic agent: `dev2.agent.a@example.invalid`, password `Local-Dev2-Only-2026`. These fixtures belong only on the isolated, mail-muted `crm.localhost` site and must never be deployed.

After deploying the updated app into the local bench:

```powershell
docker exec -w /workspace/frappe-bench crm-dev2-backend-1 bench --site crm.localhost run-tests --module crm.tests.test_agent_ui
docker exec -w /workspace/frappe-bench crm-dev2-backend-1 bench --site crm.localhost run-tests --module crm.tests.test_agent_admin
docker exec -w /workspace/frappe-bench crm-dev2-backend-1 bench --site crm.localhost run-tests --module crm.tests.test_productivity
node docker/local/agent-native-browser.cjs
```

The native UI suite covers role invitations, legacy-role migration, scoped native APIs, forged writes, extra roles, suspended access, staff delegation and handler replacement. Browser validation covers desktop/mobile lead and contact creation, follow-up tasks, personal calendar/My Day, API isolation, legacy redirects and administrator invitation controls. Older standalone-agent browser scripts describe the retired interface and are superseded by `agent-native-browser.cjs`.

The original CRM Invitation suite cannot initialize because the local ERPNext fixture lacks the Payment Gateway DocType; focused invitation regressions run in `test_agent_ui`. No real invitation email has been sent. Separate Cloud staging, installed-app access auditing, actual email delivery, backup/restore and production patch matching remain release gates. See [roadmap](dev2-roadmap.md) and [local setup](../docker/local/README.md).
