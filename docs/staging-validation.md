# Migration staging validation

As of 2026-10-04, the user confirms there is no separate Frappe Cloud staging site. Production has not been accessed. Local validation and a local restore do not establish production readiness.

## Read-only evidence report

As Administrator/System Manager, open `/api/method/crm.migration.validation.report` or run:

```bash
bench --site STAGING_SITE execute crm.migration.validation.report
```

The report includes installed app versions, source/mapping counts, custom-field metadata and observed sync/mail/scheduler flags. It deliberately returns `ready_for_production: false` and lists external gates requiring evidence. It cannot determine from a hostname whether the site is production, verify a backup, or establish outbound-integration isolation. Reports contain site/schema information; store them privately outside Git.

## Isolated local restore rehearsal

`docker/local/restore-rehearsal.py` runs only in `/workspace/frappe-bench`, backs up muted, paused `crm.localhost`, and restores into **new** `crm-restore.localhost`. It refuses an existing destination or an enabled source sync. It preserves source configuration secrets privately, restores database/public/private files, runs migrations, compares full business-document hashes and file hashes, and verifies the restored Administrator password. It does not delete a previous site or change the active bench site. A separate explicit cleanup is needed before repeating the same destination.

Prepare the synthetic extension fixtures as below, then run:

```powershell
docker exec -w /workspace/frappe-bench crm-dev2-backend-1 env/bin/python /source/crm/docker/local/restore-rehearsal.py
```

Backups, configuration keys, command logs and result JSON stay under `/workspace/dev2-restore-evidence` inside the local Docker volume. Never commit those files or paste configuration keys into chat. The local credentials in this script are synthetic development credentials only.

## Cloud staging acceptance gates

1. Create a separate non-production site/bench with the exact deployed app versions, custom apps and `dev2` revision. Confirm the destination before restoring anything.
2. Securely back up the database, public/private files and required encryption configuration. Restore a representative or sanitized copy into that staging destination.
3. Isolate outgoing email, webhooks, payment services, calendar connectors, domain enrichment, server scripts and other automation before permitting restored services to run. Mail mute alone does not isolate all integrations.
4. Capture the read-only report and compare versions, source counts, schemas and required fields. Choose real user/status/custom-field mappings. Review Customer/Prospect duplicates explicitly.
5. Run small manual batches with automatic sync off. Reconcile Lead/Organization/Deal identities, amounts, creator scope and all Review/Failed rows. Rerun to verify no duplicates. Test CRM-side edits and source clears.
6. Review Contact and Address links individually. Test agent A, agent B, salesperson and administrator through UI and direct APIs. Verify original private attachments stay protected and history is not disclosed to agents.
7. Preview selected custom-field changes on representative records. Verify existing values, zero/blank behavior, required-field validation, Select options and site-specific hooks before applying.
8. Start staging scheduler/workers only after isolation, then test an automatic cycle, retries, pause/resume and independent cursors. Local development has not established worker end-to-end behavior.
9. Rehearse database/file recovery with the intended app revision. Record backup identifiers, duration, record/file reconciliation and login checks. Keep a rollback plan for writes made after the backup.
10. Obtain deployment approval after the evidence is reviewed. Leave production sync disabled until a controlled pilot is approved.

## Repeatable local application checks

```powershell
docker compose -f docker/local/compose.yaml exec -T backend bash /source/crm/docker/local/test-sync.sh
```

For browser fixtures, copy `docker/local/seed-migration-extensions.py` to the bench as `apps/crm/crm/local_extensions_seed.py`, then execute `bench --site crm.localhost execute crm.local_extensions_seed.run`. The helper refuses any other site or unmuted mail and creates only clearly labelled synthetic records/custom fields/files. After deploying frontend assets, run `node docker/local/migration-extensions-browser.cjs`. It disables global and Prospect sync on completion/failure.


## Recorded local evidence (2026-10-04)

- Source `crm.localhost` restored into new `crm-restore.localhost` in a 76.6-second backup/new-site/restore/migration rehearsal.
- Full document snapshots matched for all 20 selected business/mapping/history tables; installed app lists matched.
- All five public/private files matched SHA-256 hashes (two public, three private).
- Restored Administrator password and HTTP login verified; restored CRM page served successfully.
- Private fixture readable by Administrator and denied to Guest and commission agent; restored agent Lead API remained usable and staging report remained denied.
- Restored site keeps mail muted, scheduler paused and sync disabled. A temporary server on container port 8001 was stopped after HTTP checks; the existing development server was not repointed.
- Evidence: `/workspace/dev2-restore-evidence/20261003-221639/result.json` inside Docker; a non-secret copy is in gitignored `test-results/local-restore-result.json`. Backups/configuration remain inside the Docker volume.
- Application checks: 56 sync backend tests + 18 agent/appointment tests, 253 frontend tests, UI lint/build and the migration-extension browser workflow passed.

Repeat only the HTTP checks against this existing restored site with:

```powershell
docker exec -w /workspace/frappe-bench crm-dev2-backend-1 env/bin/python /source/crm/docker/local/restore-http.py
```

This is a local synthetic-data restore, not a production backup, Cloud restore, production-version match or worker/scheduler acceptance test. Those gates remain open.
