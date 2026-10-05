# dev2 CRM implementation checklist

Status: baseline and initial agent workspace implemented locally; production unchanged.
Branch: dev2. Complete each release gate before enabling it for users.
This complements `.pi/PLAN.md`; existing scripting contracts remain authoritative.

Scope decision (2026-10-04): Finance handles commissions separately. Commission calculations, earnings, attribution for financial calculations, statements, approvals and payouts are excluded from this CRM roadmap. Restricted external-agent access and lead/contact ownership remain in scope.

## 0. Establish a safe baseline

- [ ] Record deployed Frappe/ERPNext versions, installed apps, hosting, and whether CRM shares the ERPNext site.
- [x] Set up compatible sibling frappe/ui, frontend dependencies, and an isolated Frappe test site.
- [ ] Run existing frontend, backend, and browser checks; record failures before changes.
- [ ] Create a staging copy with protected data, backups, and a tested restore procedure.
- [ ] Use additive schema changes, optional feature settings, and small logical commits.
- [ ] Record deployment and rollback steps for each release; preserve upstream integration paths.

Gate: reproducible build and test baseline, staging available, restore verified.

## 1. External commission agents: access before features

Required policy: an external agent uses CRM only and can follow up leads they
created; contacts are visible only if created by them or linked to their permitted
leads. Assignment alone must not broaden this scope. Staff behavior stays intact.

- [x] Add a dedicated Commission Agent role without staff roles and administrator-controlled restricted account creation (validated locally).
- [x] Validate Website Users on local Frappe v16 using a dedicated agent workspace. Exact production patch validation remains a release gate.
- [ ] Update CRM app eligibility, invitations, onboarding, route guards, and navigation for the new role.
- [x] Land agents at /crm-agent (redirect from /crm) and restrict business access outside CRM on the server; retain necessary login/account infrastructure. Validated locally.
- [ ] Define a server-controlled creator identity, distinct from mutable lead_owner; preserve verified source creators during imports.
- [x] Enforce creator-based lead visibility in list queries AND individual-document reads/writes; default deny for agent requests outside scope.
- [x] Apply contact scope as creator OR valid relationship to an accessible lead. Verify actual Contact/Lead relationship schema before implementation.
- [ ] Allow approved follow-up fields, notes, tasks, and appointments; prevent agents changing creators, attribution, permissions, ownership, or arbitrary contact links.
- [x] Treat linked shared contacts as read-only by default; define permitted edits for agent-created contacts to avoid changing another team's shared record.
- [ ] Deny deals, organizations, invoices, quotations, payments, reports, exports, sharing, deletion, bulk imports, administration, and other users' data by default.
- [x] Filter linked contact responses so unrelated links, transactions, and internal activity are not exposed.
- [ ] Audit search/autocomplete, counts, dashboards, custom APIs, raw SQL/get_all, files, timeline, email, notifications, realtime events, calendar and mobile routes.
- [ ] Keep the agent restriction effective when hierarchy settings change; audit additive roles, User Permissions and DocShare for bypasses.
- [x] Add administrator-controlled suspension/reactivation, credential revocation and immutable console audit history; preserve creator scope and read-only converted leads (validated locally).
- [ ] Test agent A versus agent B, staff and admin through both UI and direct APIs, including guessed IDs, forged links, exports, private attachments and role changes.

Gate: agents cannot discover or alter out-of-scope data through any tested access path.

Repository evidence: crm/permissions/org_hierarchy.py currently scopes leads/deals
by sales owner and ToDo assignment; crm/hooks.py has no equivalent Contact hook.
crm/api/__init__.py explicitly admits existing sales/admin roles.
ERPNext CRM Settings can grant Item access to Sales User/Sales Manager.
Reuse the existing permission architecture, but do not treat it as this policy.

## 2. ERPNext data migration and synchronization

- [ ] Inventory source counts, custom fields, statuses, owners, links, notes, emails, files, activities and duplicates.
- [ ] Confirm scope: one-time migration, ongoing one-way sync, or selected two-way fields. Prefer a migration plus clearly owned ongoing integrations.
- [ ] Confirm source-to-target mappings against deployed schemas:

| ERPNext source | Frappe CRM target | Rule |
| --- | --- | --- |
| Lead | CRM Lead | Map statuses, contact details, source and verified creator |
| Opportunity | CRM Deal | Map stages, amounts, currency, linked leads and contacts |
| Customer / Prospect | CRM Organization where appropriate | Do not assume every individual customer is an organization; retain ERPNext identity |
| Contact / Address | Shared records on same site, mapped records across sites | Reuse existing identities and validate links |
| ToDo / Event / communications / files | Appropriate CRM activity or linked source record | Preserve access rules, timestamps and provenance |

- [ ] For same-site deployment, reuse shared Contact/Address records; explicitly migrate ERPNext Lead/Opportunity because they are different DocTypes from CRM Lead/Deal.
- [ ] For separate sites, use a dedicated restricted integration account with server-stored credentials and authenticated API calls.
- [ ] Store unique source-site + source-DocType + source-name mappings and checkpoints; repeated runs must not create duplicates.
- [ ] Perform a dry run with validation errors and proposed mappings; resolve ambiguous duplicates manually.
- [ ] Import a representative sample into staging in dependency order, suppressing outbound messages and unintended automation during migration.
- [ ] Preserve original creator separately when the integration user technically inserts records; never attribute all imported leads to that user for agent access.
- [ ] Reconcile counts, values, relationships, permissions, attachments and activity history; report exclusions explicitly.
- [ ] Set field ownership: proposed CRM authority for sales pipeline and ERPNext authority for accounting/payment truth. Decide shared contact ownership explicitly.
- [ ] If ongoing sync is needed, add retries, idempotency, conflict handling, loop prevention, monitoring and an exception queue; avoid automatic hard-delete propagation.
- [ ] Back up, execute controlled cutover, reconcile final changes and retain source data until verification. Define batch-specific rollback without deleting unrelated edits.

Gate: sample migration approved, reruns duplicate-free, permissions verified, counts
and links reconciled. Existing ERPNext integration is not assumed to migrate all history.

## 3. My Day and internal calendar

- [x] Audit existing Event capabilities and extend them with personal staff/agent appointment APIs and calendar entry points (local).
- [x] My Day: overdue, today, upcoming and undated tasks; today's appointments; New-status leads; quick completion and permitted record/calendar links for staff and agents (local).
- [ ] Define and add unanswered-message indicators separately; lead status is not an unanswered-message metric.
- [ ] Calendar: day/week/month views; calls, meetings, demos and follow-ups linked to permitted records.
- [ ] Add attendees, responsible salesperson, timezone, location/meeting URL and configurable reminders.
- [ ] Support rescheduling, cancellation, completed/no-show outcomes and next follow-up creation.
- [ ] Add conflict warnings without revealing private event titles or attendees.
- [ ] Ensure reminders, calendar feeds and aggregate counts obey agent restrictions; test timezone/DST handling and repeated reminder jobs.

Gate: staff and agent calendars show only permitted data; reminders do not duplicate.

## 4. Deal health and selling assistance

- [ ] Advisory deal health: stale activity, overdue close dates and missing next actions; configurable thresholds and visible reasons.
- [ ] Duplicate warnings using normalized email/phone and organization matching; no automatic merging and no disclosure of restricted matches.
- [ ] Optional stage playbooks with checklists and suggested next tasks.
- [ ] Account overview combining permitted contacts, deals, tasks and activity; staff only unless a later policy permits agent access.
- [ ] Explainable rule-based lead scoring with audited changes; extend existing scoring/automation capabilities.
- [ ] Manager reporting: conversion, stage aging, workload and forecast definitions with hierarchy-aware permissions.
- [ ] Extend existing workflow automation and domain enrichment with scoped routing/reminders, audit logs and user-controlled activation.

Gate: advice does not silently change records; aggregates and duplicate warnings do not leak data.

## 5. External appointments and booking

- [ ] Confirm Google Calendar/Outlook needs and inspect existing framework integrations before adding connectors.
- [ ] Implement explicit user connection, least-privilege scopes, secure tokens, disconnect/revocation and clear sync ownership.
- [ ] Handle external IDs, recurrence, timezone, cancellations, retries, conflicts and sync loops.
- [ ] Add public booking links with availability windows, buffers, timezone selection, anti-abuse controls and atomic slot reservation.
- [ ] Keep private event details and CRM record identifiers out of public availability responses.

Gate: two-way update/cancellation tests pass and concurrent bookings cannot reserve the same exclusive slot.

## 6. AI assistance

- [ ] Choose provider, budget, data retention and approved data scope.
- [ ] Add activity summaries, follow-up drafts and suggested next steps using only records the requester can read.
- [ ] Require human review before sending communications or changing records.
- [ ] Show source references, handle uncertain output and audit usage/costs.

Gate: permission isolation verified and no automatic external messages.

## Release routine

- [ ] Update relevant docs/contracts; add meaningful utility/backend/permission tests for changed behavior.
- [ ] Run relevant lint/build/tests and staff/agent browser smoke tests.
- [ ] Verify migration reversibility and feature-off behavior; pilot with a small group.
- [ ] Record completion evidence here and move completed architectural phase details according to .pi documentation conventions.

## Decisions still needed

- ERPNext/Frappe versions, same or separate sites, hosting restrictions and source data volume.
- One-time migration versus ongoing sync, and which system remains authoritative for each dataset.
- Whether creator access survives reassignment/conversion; shared-contact edit policy.
- Required calendar provider(s) and whether customers need public booking immediately.

## References

- Frappe permission hooks: https://docs.frappe.io/framework/user/en/python-api/hooks
- Local permissions: ../crm/permissions/org_hierarchy.py
- Local ERPNext integration: ../crm/fcrm/doctype/erpnext_crm_settings/erpnext_crm_settings.py
- Existing architecture roadmap: ../.pi/PLAN.md

Baseline work started: see [baseline evidence and staging runbook](dev2-baseline.md). Confirmed target: ERPNext/Frappe v16 on Frappe Cloud, CRM on the same site.

Baseline evidence: locked frontend dependencies installed; 248 tests passed; source ESLint has 0 errors and 11 warnings. Windows production build now passes after build-only proxy and portable-copy fixes. Private Cloud bench exists, but the supposed staging URL is production; separate staging is not verified. Local backend, restore and v16 same-site checks remain open.

Local backend milestone: isolated Docker site installed with Frappe 16.36.0 + ERPNext 16.37.0 + CRM dev2. Linux build and synthetic-user HTTP/lead-isolation checks pass. Full baseline remains open: lead suite fixture error, browser workflows, exact production patch match and restore verification.

Agent workspace milestone: dedicated role, creator-scoped leads, scoped contact projections, personal follow-up tasks and a server request allowlist implemented locally. Nine integration tests, session/token HTTP checks, an Edge browser workflow and staff smoke checks passed. Invitations, suspension audit, appointments and cross-app staging validation remain open. See [agent access and validation](commission-agents.md).

Calendar milestone: private lead-linked agent appointments now support booking, rescheduling, completion/cancellation, site-timezone validation, scoped overlap warnings and day/week/31-day agenda navigation. Thirteen backend tests and local browser/HTTP checks cover the agent workspace. Full calendar phase remains open for reminders, attendees, My Day, no-show outcomes and graphical calendar views. See [calendar usage and limitations](agent-calendar.md).

Staff booking and pre-lead meetings: My calendar is available in staff navigation, with Book appointment on desktop staff lead pages. Both staff and agents can book an unlinked introduction, complete it, and create a lead while retaining the original Event. Conversion checks permissions and serializes retries per Event. Fifteen backend tests, 248 frontend tests and the production build pass; browser workflows cover Administrator, salesperson and agent. See [meeting workflow](agent-calendar.md).

Lead activity integration completed locally: permission-filtered appointment cards show existing linked Events and meetings converted to leads, with current timing/status and no duplicate cards. Eighteen backend tests, 248 frontend tests, production build and staff/agent browser checks pass.

Calendar design milestone: staff My Calendar now has a Google Calendar-inspired month grid, day/week time columns, mini calendar, Today/navigation controls, Schedule view, status colours/filters, search and event-detail dialogs. Booking, conversion and lead activity workflows remain covered. 253 frontend tests and production build pass; desktop/mobile calendar and existing workflow browser checks pass. Drag-and-drop, reminders and provider sync remain open.

Milestone checkpoint (2026-10-03): local setup, agent access, appointments, lead activity and staff calendar design are committed on dev2. Latest validation: 18 focused backend tests, 253 frontend tests, build and browser workflows pass. Separate staging, restore verification and the broader Lead fixture blocker remain open. Next: ERPNext mapping and a read-only migration preview; no production import is authorized or configured.

Migration preview milestone (2026-10-03): same-site Lead mapping and administrative read-only preview implemented and tested locally. Nine planner tests and three integration tests pass, including write-rejecting SQL verification. Local inventory/report generated; production inventory, persisted source mapping, actual importer, Opportunity/history migration and ongoing sync remain open. See [migration mapping and preview](erpnext-migration.md).


### 2026-10-03: opt-in ERPNext Lead sync

- Added same-site Lead sync with administrator controls at `/crm/erpnext-sync`, manual batches and optional scheduled reconciliation.
- Added unique source/destination mappings, original-creator preservation, field snapshots, conflict review, per-record failure rollback, persisted batch cursor and administrator run history.
- CRM status/assignment remain CRM-owned after initial import. Shared contacts are not relinked; agent visibility continues to use the verified creator.
- Sync is disabled by default. Local scheduler remains paused; production remains untouched.
- Remaining: Opportunity/Deal and relationship/history mapping, large-inventory optimization, run retention, successful-batch undo, real-data staging and deployment/restore validation.
- Details and local checks: [ERPNext sync](erpnext-sync.md).


### 2026-10-03: opt-in Opportunity -> Deal sync

- Added a separate opt-in for open, lead-based ERPNext Opportunities in the CRM base currency.
- Reuses imported Lead identities, supports multiple Opportunities per Lead, persists independent checkpoints, and exposes native Deal links in run history.
- Protects CRM Deal stage/assignment and reviews amount/date conflicts, existing manual Deals, unsupported currencies/products/lifecycle, changed relationships and outbound customer-creation hooks.
- Remaining: Customer/Prospect organization mappings, contact/address relationships, foreign-currency policy, closed-opportunity/history migration, deployment and restore validation.
- Sync and automatic scheduling remain disabled locally; production is untouched. See [ERPNext sync](erpnext-sync.md).

- Fixed creator-preserving inserts to retain the administrator login session. Validation: 25 sync backend tests, 253 frontend tests, build/lint and the expanded browser smoke passed.


### 2026-10-03: Customer Organizations and reviewed shared Contacts

- Added opt-in Company/Partnership Customer -> Organization sync, independent checkpoints, creator provenance, duplicate review and field-conflict protection.
- Open Customer Opportunities now reuse mapped Organizations without creating synthetic Leads.
- Added individual shared Contact link review, explicit agent-access warnings, stale-review protection, audit history and removal of workflow-created links. Contacts are reused, not copied; batch sync never grants Contact access automatically.
- Validation: 36 sync backend tests, 18 agent/appointment regression tests, 253 frontend tests, UI lint/build and Customer/Contact browser workflow passed.
- Local sync remains disabled and the scheduler paused. Production remains untouched.
- Remaining migration work: Individual Customer/Prospect and Address mappings, currency/lifecycle policies, history/custom fields, large-inventory optimization, retention/undo and separate staging/restore validation. Reminders and external calendar integration remain separate roadmap items.
- Usage and access implications: [ERPNext sync](erpnext-sync.md).


### 2026-10-03: opt-in Customer primary Address reuse

- Added a separate default-off setting to reuse verified Customer primary Addresses on mapped Organizations without copying or changing shared Address records.
- Preserves existing CRM address choices, reviews invalid relationships and conflicting changes, and retains comparison history while disabled.
- Validation: 41 sync backend tests, 253 frontend tests, lint/build and expanded Customer/Contact browser smoke passed. No new agent Address/Organization access.
- Remaining: Prospect/individual relationships, additional Address mappings, history/custom fields, currency/lifecycle policy and separate staging/restore validation. Production unchanged; local sync disabled.


### 2026-10-04: Prospect, additional Address and migration review extensions

- Added default-off Prospect -> Organization batches and Prospect Opportunity relationships, with cross-Customer/Prospect duplicate review.
- Added individual additional Address link review, auditing and exact-link reversal; existing primary Address behavior remains separate.
- Added an administrator-only original-history view for comments, notes, communications, files, tasks and events. It preserves source ownership/privacy and does not copy entries into CRM timelines.
- Added custom-field inventory and per-record preview/apply for explicitly selected compatible scalar fields; field snapshots, stale-review rejection and conflict protection are persisted. No scheduled custom-field sync or automatic schema creation.
- Added read-only staging evidence at `crm.migration.validation.report` and an isolated local restore rehearsal script. User confirmed that separate Cloud staging does not exist; Cloud/production validation is still pending.
- Validation: 56 sync backend tests, 253 frontend tests, frontend lint/build and migration-extension browser workflow passed. See [staging validation](staging-validation.md) for restore evidence and remaining release gates.
- Remaining: production-specific field selection, rich/link/table custom mappings, individual Customers, foreign currency/products/closed lifecycle, broader timeline/history import, representative Cloud staging, scheduler-worker validation and production rollout.


Local restore evidence (2026-10-04): backup/database/public/private files restored into a new isolated local site; all 20 selected document-table hashes and five file hashes match. HTTP login, private-file restrictions and restored agent access pass. Full focused regression result: 74 backend tests and 253 frontend tests pass. Separate Cloud staging still does not exist; production release gates remain open.


### 2026-10-04: external agent administration

- Added administrator-only **Settings > User Management > Agents**: restricted account creation, search, separate password-setup invitations, suspension/reactivation with reasons and newest-first audit history.
- Existing staff accounts cannot be converted here. Extra roles/profile issues block activation and invitation; suspension remains available. State changes reject stale account versions.
- Suspension revokes sessions, API credentials, OAuth tokens and pending setup links while retaining CRM records. Reactivation does not revive old credentials. Disabled-agent checks also apply at the request/API boundary.
- Validation: 26 focused backend tests, 253 frontend tests, lint/build and a browser/HTTP lifecycle check pass locally. Native invitation generation was tested with delivery mocked; local mail stays muted.
- Remaining agent work: representative Cloud staging and cross-app/production-version checks, actual setup-email delivery, broader security review and deployment. Finance continues to handle all commissions outside CRM.
- Usage, audit scope and deployment notes: [agent administration](commission-agents.md#agent-administration).


### 2026-10-05: My Day calendar and productivity

- Added staff **My Day** navigation and a restricted agent **My Day** tab: open appointments today, overdue/today/upcoming/undated tasks and personal New-status leads.
- Added permission-checked task completion with stale-edit protection, linked-record navigation and direct calendar details/booking entry points. Site-timezone day boundaries, bounded lists and visible truncation notices apply.
- Staff tasks use personal assignment/ownership plus native document permissions. Agents retain creator-based lead/task scope, and suspended accounts remain denied.
- Validation: 35 focused backend tests (9 My Day, 18 agent/calendar, 8 administration), 253 frontend tests, lint/build and staff/admin/agent browser workflows pass locally.
- Remaining calendar/productivity work: configurable reminders, attendees/invitations, no-show outcomes and next-action creation, drag-and-drop rescheduling, recurring appointments, Google/Outlook integration and separate Cloud staging validation. Mail and scheduler remain disabled locally; production unchanged.
- Usage and limits: [My Day](agent-calendar.md#my-day).
