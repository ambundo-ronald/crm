# ERPNext Lead sync

Implemented locally on dev2 (2026-10-03). Production has not been accessed or configured. Sync is disabled by default.

## Using it

Open **ERPNext sync** in the CRM sidebar as Administrator or System Manager, or visit `/crm/erpnext-sync`.

1. Review the source data and the status/user mappings in **CRM ERPNext Sync Settings**. Empty maps use the proposed defaults in [erpnext-migration.md](erpnext-migration.md). User mapping changes can grant agent access, so map actual creators deliberately.
2. Enable Lead sync, then click **Sync now**. Each request processes up to 50 source leads. **Sync next batch** continues a larger inventory.
3. Expand a run to see Created, Updated, Unchanged, Review, or Failed results and links to destination leads.
4. Optionally turn on automatic sync. The scheduler processes one batch each `all` cycle, starting another pass after the previous pass completes. Site scheduler and background workers must be running. The local development scheduler remains paused.
5. Disable sync to stop subsequent runs. This does not remove already imported records.

Manual batches run in the request transaction; automatic batches run in the scheduler's background job. A database row lock serializes batches and settings changes until commit. Source mappings, destination changes, logs and the cursor commit together. A failed record rolls back to its savepoint; other records may proceed. Review and failed records are revisited on the next full pass after their underlying problem is resolved. This is periodic reconciliation, not instantaneous event streaming.

## Data ownership

- Same-site ERPNext **Lead -> CRM Lead** only. There is no remote API connection or reverse write to ERPNext.
- Stable source identity is stored in **CRM ERPNext Sync Link** with a unique source Link and unique target Link. Email/phone matches flag potential duplicates; they never merge records.
- Source creator is explicitly preserved (or translated by the administrator's user map). Existing destination ownership is never reassigned by sync. Changed creators require review. Provenance includes original creator, creation and last synced source modification time; imported CRM timestamps are current.
- Source status and salesperson populate new leads only. Existing CRM status, salesperson, conversion, follow-ups, appointments and other workflow fields remain under CRM control.
- Names, email, phone/mobile, website, company name, job title and employee count are reconciled with previous source and target snapshots. Explicit source clears propagate. Unchanged source values preserve local CRM edits. If both sides change a field differently, the entire record is held for review; no partial update occurs. Align the conflicting values intentionally, then retry.
- Converted CRM leads, sensitive ERPNext statuses, disabled/unsubscribed leads, invalid identities, incomplete duplicate scans and unmapped mandatory fields require review. Existing synced leads are not automatically archived or consent-updated when the source changes to these states; those Review results need prompt administrator handling.
- ERPNext-created Contacts remain untouched and unlinked to the new CRM Lead. Their existence does not block Lead-only sync. This avoids granting agent visibility through new Contact links. Contact migration remains separate.
- Source and target deletion is not propagated. Link references normally prevent deleting mapped records. A missing destination requires review; sync does not silently recreate it.
- Normal CRM document validations and hooks run, including any installed custom automation. Validate those on a separate staging site before production use.

## Limits and remaining work

This is the first Lead-only sync release. Opportunities/Deals, organizations as separate records, shared contacts/addresses, custom fields, communication history, attachments and tasks/events are not synced. Source company name is copied into the CRM Lead's text organization field only.

Duplicate checking currently scans at most 10,000 source and 10,000 target leads. Larger inventories are held for review. Each batch scans that inventory again; large-site optimization is still needed. Run history is administrator-only and currently retains every run (no retention cleanup yet). Failed rows record the exception class rather than arbitrary validation text; diagnosis may require reproducing the validation failure in development. There is no bulk undo of successful runs, force-overwrite button, or automatic conflict resolution.

Read-only preview is still available as documented in [erpnext-migration.md](erpnext-migration.md). Separate staging, production field mapping, restore checks and wider deployment validation remain outstanding.

## Local checks

```powershell
docker compose -f docker/local/compose.yaml exec -T backend bash /source/crm/docker/local/test-sync.sh
node docker/local/sync-browser.cjs
```

The backend suite tests reruns, updates and clears, local-edit preservation, conflicts, consent, conversion, duplicate detection, contact-link privacy, agent creator access, record rollback/retry, pagination, disabled scheduling and permissions. Browser checks exercise admin controls, run history, repeated sync, mobile layout and salesperson/agent denial. The browser smoke processes the existing local fixture leads and leaves sync disabled.

Validation completed locally: 13 new sync tests, 12 migration-preview tests, 18 existing agent/appointment tests, 253 frontend tests, frontend build, changed-component lint and browser smoke passed. Automatic scheduler execution with live workers has not been exercised end to end; the scheduler entry point and disabled behavior are covered by integration tests.
