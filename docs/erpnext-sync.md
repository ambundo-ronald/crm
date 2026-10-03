# ERPNext CRM data sync

Implemented locally on dev2 (2026-10-03). Production has not been accessed or configured. Sync is disabled by default.

## Using it

Open **ERPNext sync** in the CRM sidebar as Administrator or System Manager, or visit `/crm/erpnext-sync`.

1. Review the source data and the status/user mappings in **CRM ERPNext Sync Settings**. Empty maps use the proposed defaults in [erpnext-migration.md](erpnext-migration.md). User mapping changes can grant agent access, so map actual creators deliberately.
2. Enable Lead sync. Optionally enable **Customer sync** and **Opportunity sync**, then click **Sync now**. Each request processes up to 50 Leads, 50 selected Customers, and 50 selected Opportunities, in that order. **Sync next batch** continues a larger inventory.
3. Expand a run to see Created, Updated, Unchanged, Review, or Failed results and links to destination Leads, Organizations or Deals.
4. Optionally turn on automatic sync. The scheduler processes one batch of each selected source type each `all` cycle, starting another pass after the previous pass completes. Site scheduler and background workers must be running. The local development scheduler remains paused.
5. Disable sync to stop subsequent runs. This does not remove already imported records.

Manual batches run in the request transaction; automatic batches run in the scheduler's background job. A database row lock serializes batches and settings changes until commit. Source mappings, destination changes, logs and the cursor commit together. A failed record rolls back to its savepoint; other records may proceed. Review and failed records are revisited on the next full pass after their underlying problem is resolved. This is periodic reconciliation, not instantaneous event streaming.

## Data ownership

- Same-site ERPNext **Lead -> CRM Lead**, plus separately opt-in **Opportunity -> CRM Deal**. There is no remote API connection. Lead, Customer and Opportunity source fields are not updated. Individually approved Contact links deliberately update the shared Contact relationship table, as described below.
- Stable source identity is stored in **CRM ERPNext Sync Link** with a unique source Link and unique target Link. Email/phone matches flag potential duplicates; they never merge records.
- Source creator is explicitly preserved (or translated by the administrator's user map). Existing destination ownership is never reassigned by sync. Changed creators require review. Provenance includes original creator, creation and last synced source modification time; imported CRM timestamps are current.
- Source status and salesperson populate new leads only. Existing CRM status, salesperson, conversion, follow-ups, appointments and other workflow fields remain under CRM control.
- Names, email, phone/mobile, website, company name, job title and employee count are reconciled with previous source and target snapshots. Explicit source clears propagate. Unchanged source values preserve local CRM edits. If both sides change a field differently, the entire record is held for review; no partial update occurs. Align the conflicting values intentionally, then retry.
- Converted CRM leads, sensitive ERPNext statuses, disabled/unsubscribed leads, invalid identities, incomplete duplicate scans and unmapped mandatory fields require review. Existing synced leads are not automatically archived or consent-updated when the source changes to these states; those Review results need prompt administrator handling.
- Batch sync never links Contacts automatically. Their existence does not block Lead sync. Administrators can separately review and approve shared Contact relationships; linking an agent-owned CRM Lead grants that agent Contact visibility.
- Source and target deletion is not propagated. Link references normally prevent deleting mapped records. A missing destination requires review; sync does not silently recreate it.
- Normal CRM document validations and hooks run, including any installed custom automation. Validate those on a separate staging site before production use.

## Limits and remaining work

Open Lead-based and mapped business-Customer Opportunities are supported. Prospect and individual-Customer relationships, closed opportunities, product lines, foreign-currency conversion, additional/non-Customer addresses, custom fields, communication history, attachments and tasks/events remain outside the supported sync scope. Lead company name remains a text field; separate Organizations are created only by opt-in business-Customer sync.

Duplicate checking currently scans at most 10,000 source and 10,000 target leads. Larger inventories are held for review. Each batch scans that inventory again; large-site optimization is still needed. Run history is administrator-only and currently retains every run (no retention cleanup yet). Failed rows record the exception class rather than arbitrary validation text; diagnosis may require reproducing the validation failure in development. There is no bulk undo of successful runs, force-overwrite button, or automatic conflict resolution.

Read-only preview is still available as documented in [erpnext-migration.md](erpnext-migration.md). Separate staging, production field mapping, restore checks and wider deployment validation remain outstanding.

## Local checks

```powershell
docker compose -f docker/local/compose.yaml exec -T backend bash /source/crm/docker/local/test-sync.sh
# Seed the synthetic Opportunity first as described below.
node docker/local/sync-browser.cjs
```

The backend suite tests reruns, updates and clears, local-edit preservation, conflicts, consent, conversion, duplicate detection, contact-link privacy, agent creator access, record rollback/retry, pagination, disabled scheduling and permissions. Browser checks exercise admin controls, run history, repeated sync, mobile layout and salesperson/agent denial. The browser smoke processes the existing local fixture leads and leaves sync disabled.

Current validation: 36 sync backend tests, 18 agent/appointment regression tests, 253 frontend tests, frontend build, changed-component lint and Customer/Contact browser smoke passed. The 12 migration-preview tests passed in the earlier preview milestone. Automatic scheduler execution with live workers has not been exercised end to end; the scheduler entry point and disabled behavior are covered by integration tests.


## Opportunity -> Deal mapping (2026-10-03)

Opportunity sync is **off by default**, including upgrades. Select it explicitly on the sync page or in CRM ERPNext Sync Settings. The global Lead sync switch still controls whether any sync runs; disabling the global switch stops all batch sync. Automatic batches include opportunities only while both settings are enabled.

| ERPNext Opportunity | CRM Deal / policy |
| --- | --- |
| name | Unique persistent CRM ERPNext Opportunity Link; never matched by email |
| opportunity_from = Lead, party_name | Reuse the previously synced CRM Lead through its source mapping |
| opportunity_from = Customer, party_name | Reuse an eligible business Customer's mapped CRM Organization; do not create a synthetic Lead |
| owner | Preserve enabled source creator, applying the existing explicit user map |
| opportunity_owner | Initial deal_owner; requires enabled non-agent System User |
| Open / Replied / Quotation | Initial Qualification / Qualification / Proposal/Quotation; optional opportunity_status_map JSON override restricted to Open/Ongoing target status types |
| opportunity_amount | deal_value, with three-way comparison and conflict protection |
| expected_closing | expected_closure_date, including explicit clears; conflict protection |
| currency | Must equal CRM base currency (FCRM Settings, fallback USD); exchange rate stays 1 |
| linked CRM Lead display fields | Initial lead_name, organization_name, first_name, last_name; no organization or contact creation |

CRM retains ongoing control of Deal stage, salesperson, probability, next step, contacts and workflow. ERPNext sales_stage/probability/title are not mapped to those CRM fields. Initial ERPNext creator and timestamps are retained in the mapping; CRM document timestamps reflect actual import time. Both sides changing amount or closing date differently holds the whole Deal update for review.

Distinct opportunities for the same lead create distinct Deals. A pre-existing manual Deal linked to that CRM Lead is a review candidate, not a match to adopt. The duplicate check does not infer identity for unlinked Deals. Missing lead mappings are reviewed and retried on a later pass; source leads are processed first in each batch. Independent Lead and Opportunity cursors persist across batches. If one source type completes before the other, it begins a new pass on the next batch.

Unmapped/ineligible Customer and Prospect relationships, product lines, unsupported currencies, terminal ERPNext statuses, terminal CRM Deals, converted CRM leads on initial import, invalid owners, changed relationships and source-lead consent restrictions require review. Unsupported cases do not create partial Deals. A changed source relationship or creator never silently reassigns an existing Deal. Existing mappings can continue normal updates after their linked CRM Lead is converted; conversion itself remains a CRM action.

The existing outbound ERPNext customer-creation integration is checked before saving: if the proposed/current Deal status would trigger it, the row is held for review. Custom CRM hooks still run; staging must validate any site-specific automation. Commission Agents receive no Deal or sync access through this feature, even when their creator identity is preserved.

The browser smoke requires one synthetic Opportunity. Copy `docker/local/seed-opportunity-sync.py` into the local bench as `apps/crm/crm/local_opportunity_seed.py`, then execute `bench --site crm.localhost execute crm.local_opportunity_seed.run`. The helper refuses sites other than muted `crm.localhost`, creates no production connection, and uses an explicit synthetic exchange rate solely to avoid external lookup while preparing the fixture. It does not enable sync. Run `node docker/local/sync-browser.cjs` after deploying the built assets; this checks both opt-in controls and the native Deal link and disables both options afterward.

Eleven Opportunity integration tests cover idempotency, amount/date updates and clears, conflicting CRM edits, multiple opportunities per lead, manual-Deal duplicate review, excluded lifecycle/party/currency/products, changed relationships, outbound-customer automation, record rollback/retry, permissions/agent creator preservation, and independent checkpoints. The existing Lead-sync suite plus a new login-session regression test (14 tests total) and 253 frontend tests also pass, along with UI lint and the frontend build.

Browser verification passed for agent-owned imports, repeat sync without losing the administrator session, native Deal links, mobile layout and salesperson/agent denial. Both sync options were disabled afterward. The source-creator context now preserves the caller's session ID, session data and request arguments on success and failure.


## Customer -> Organization and reviewed shared Contacts (2026-10-03)

Customer sync is separately opt-in and off by default. Company and Partnership Customers map to CRM Organizations using only customer_name and website. Individual, disabled and frozen Customers require review. Unique source mappings preserve creator provenance; three-way comparisons protect CRM edits and propagate explicit source clears. Normalized identical names in either source Customers or destination Organizations require review, never automatic merging or adoption. Inventories above 10,000 records are held for review. Financial, tax, address, territory and industry fields are not copied.

Customers run before Opportunities, with an independent persisted cursor. A Customer-based Opportunity requires an existing eligible Customer mapping and links its Deal directly to that Organization. No fake Lead is created. The existing currency, lifecycle, duplicate and outbound-hook safeguards still apply.

On the sync page, choose **Review contact links** after syncing source records. CRM and ERPNext already share the same Contact documents on this site: this workflow reuses identities rather than copying names, email addresses or phone numbers. Review the existing relationships and destination owner, then approve each proposed CRM Lead or Organization link separately. The agent-access action explicitly says **Link and grant lead owner access**. A stale review is rejected if the Contact, source, destination or relevant ownership changes.

Shared Contacts remain read-only for commission agents. An Organization link alone does not grant agent Lead access. Contact ownership and other existing relationships can independently grant access; removing one link does not revoke those other paths. Staff changes to a shared Contact's details naturally affect that same identity in both applications.

**Show managed links** lists relationships added through this workflow and lets an administrator remove the exact recorded CRM link. Existing ERPNext links and pre-existing CRM links are preserved. Removal remains available after the ERPNext source relationship is removed. Source unlinking or lifecycle changes do not automatically revoke an approved CRM relationship: administrators must review and remove it explicitly. A changed recorded child row is held for review rather than deleted. Approvals/removals have an audit record and appear in sync run history. There is no automatic Contact-link scheduler.

Local browser verification covered Customer opt-in, native Organization links, explicit shared-Contact approval, access for the owning agent only, reversal, and mobile layout. It left global and Customer sync disabled. For repeat checks, seed the synthetic Opportunity fixture first, then copy `docker/local/seed-customer-contacts.py` into the local bench as `apps/crm/crm/local_relationship_seed.py` and execute `bench --site crm.localhost execute crm.local_relationship_seed.run`. The seed refuses any site other than muted `crm.localhost`. After deploying built assets, run `node docker/local/customer-contact-browser.cjs`.


## Optional Customer primary Address reuse

**Enable primary Address sync** is a separate, default-off control on the sync page. It runs only when global sync and Customer sync are enabled. The Customer's `customer_primary_address` must identify an enabled shared Address with an existing Dynamic Link to that exact Customer. Missing, disabled or unrelated addresses hold the entire Customer row for review.

The Organization's `address` points to that existing record. No Address is copied, modified, deleted or given additional Dynamic Links. Address details therefore remain shared: authorized staff editing the Address will change the same record ERPNext uses. Commission agents gain no Address or Organization access.

The first opt-in refuses to overwrite an existing different CRM address, including when the source has no primary address. Later source changes and clears use three-way comparison; conflicting CRM choices hold the entire Customer update. Disabling this option leaves existing references and comparison snapshots intact, so re-enabling it cannot silently overwrite intervening CRM edits. Clearing a source reference clears the Organization reference only when safe; the shared Address remains intact. Additional billing/shipping addresses and Lead/Prospect addresses remain outside this slice.

Validation: 41 sync backend tests (including five primary Address tests), 253 frontend tests, lint and production build passed. Browser smoke verifies the opt-in controls and agent denial alongside Customer/Contact workflows. Automatic worker execution and production staging remain outstanding.
