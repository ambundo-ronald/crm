# Isolated dev2 backend

Local development only. No production URL, backup or credentials are used.
The database is private to this Compose project. HTTP binds to 127.0.0.1:18000.
A named Linux volume holds the bench and dependencies; the checkout is mounted
read-only and copied into the Linux bench by bootstrap.

From the repository root:

```powershell
docker compose -f docker/local/compose.yaml up -d
docker compose -f docker/local/compose.yaml exec -T backend bash -lc "cp /source/crm/docker/local/bootstrap.sh /tmp/dev2-bootstrap.sh && bash /tmp/dev2-bootstrap.sh"
docker compose -f docker/local/compose.yaml exec backend bash -lc "cd /workspace/frappe-bench && bench serve --port 8000"
```

Open http://crm.localhost:18000/crm (or localhost:18000 with the default site).
Local-only login: Administrator / Local-Dev2-Only-2026.
Never use these development passwords or this compose file for deployment.

Bootstrap pins Frappe v16.36.0 and ERPNext v16.37.0, not the unknown production patch versions.
Record resolved revisions after successful setup. Container image digests are pinned in compose.yaml.

Bootstrap copies working-tree changes but does not remove deleted files from the
Linux copy. For deletions, explicitly remove only the corresponding local bench
files. Re-run bootstrap after edits when the backend is stopped.

The scheduler is paused and mail muted. This serve command does not launch
queue workers or realtime; start those separately when testing asynchronous work.
No external integrations are configured.

Stop without deleting data:
```powershell
docker compose -f docker/local/compose.yaml stop
```

Status: local installation, migrations, Linux build and HTTP smoke checks passed. The existing CRM Lead test suite is blocked by missing Payment Gateway in upstream fixture generation (0 tests ran). See docs/dev2-baseline.md for limitations.

Run local HTTP checks: python docker/local/smoke.py

Synthetic sales users: dev2.sales.a@example.invalid and dev2.sales.b@example.invalid.
Their local password is the same development password shown above. These users
currently have Sales User, not the future Commission Agent role.

The running web log is /workspace/dev2-web.log inside the backend container.

The Commission Agent workspace is now available at /crm-agent. See [agent setup and checks](../../docs/commission-agents.md) for synthetic agent accounts and test commands.


## Migration extensions and restore validation

Prospect, additional Address, source-history and custom-field review are available at `/crm/erpnext-sync`. Run `bash /source/crm/docker/local/test-sync.sh` in the backend container for the focused migration suite. Synthetic extension fixtures and browser usage are documented in [staging validation](../../docs/staging-validation.md).

The local restore rehearsal refuses to overwrite an existing `crm-restore.localhost` site. That restored site now exists, with mail muted, scheduler paused and sync disabled. Its temporary HTTP validation server does not remain running. Backups and configuration secrets live only in the Docker volume under `/workspace/dev2-restore-evidence`; never add them to Git.
