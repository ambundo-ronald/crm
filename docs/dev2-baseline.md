# dev2 baseline and local development

Status: local frontend baseline verified; backend, recovery and deployment gates remain open.

## Deployment target and environment

- User confirmed ERPNext/Frappe v16 on Frappe Cloud, CRM on the same site.
- A private bench exists. The URL previously described as staging is live production.
  No separate staging site has been verified. Do not run tests or migrations there.
- No production site was accessed or changed during this work.
- Exact patch versions and installed app inventory remain pending.
- Starting CRM revision: e9c6f0fac08dd9a63dca2e6b62c70ae1065022f8 on dev2.
- Windows, Node 24.16.0, Yarn 1.22.22, Python 3.11.9.
- Windows has no host Bench command. Docker is now running; the isolated Linux container supplies Bench.
- Required sibling frappe/ui downloaded from develop at
  03f42bbe80f600c22bccc811d7b3f3d943e03f68, matching the current frontend CI approach.
  This is not evidence of backend compatibility with Frappe v16.
- Optional frappe-ui submodule remains uninitialized; npm package used for builds.

## Results

- Locked dependency installation: passed; lockfiles unchanged.
- Frontend tests after fixes: 23 test files, 248 tests passed.
- Full source ESLint baseline: 0 errors, 11 existing warnings.
- Production build after fixes: passed, including PWA generation and HTML copy (25.25 seconds).
- New copy script lint: passed. Source/destination HTML SHA256 hashes match.
- Extra lint of vite.config.js reports its existing optional local frappe-ui import
  as unresolved because the submodule is uninitialized; production npm fallback works.
- Build emits bundle-size and plugin-timing warnings; these remain optimization work.
- Local v16 same-site installation, migrations, Linux build and authenticated API smoke checks: passed. Full browser workflows and restore verification remain unverified. CRM Lead regression suite is blocked in fixture generation (Payment Gateway missing; 0 tests ran).

## Build fixes

Installed frappe-ui/vite/utils.js searches parents until a POSIX root. On Windows
outside a bench, the drive root resolves to itself and the search loops forever.
Vite now enables the upstream proxy plugin only for serve, avoiding unnecessary
discovery during production builds. Development-server behavior is unchanged;
Windows yarn dev outside a bench still requires a separate fix or a Linux bench.
A small Node script replaces the Unix-only cp command for the HTML entry.

From frontend:

- yarn.cmd install --frozen-lockfile
- yarn.cmd test:run
- node node_modules/eslint/bin/eslint.js src --ext .js,.ts,.vue
- yarn.cmd build

On Linux use yarn instead of yarn.cmd. Generated build output is gitignored.
A frontend build alone is not a usable standalone CRM: interactive workflows
require a Frappe backend. Do not proxy local development to the live ERPNext site.

## Next local backend tasks

- [x] Make an isolated Linux Docker environment available.
- [ ] Match the intended v16 patch versions and required apps.
- [x] Create a disposable local site with synthetic records and test users.
- [x] Validate CRM installation, migrations and ERPNext co-installation on the recorded local versions.
- [ ] Run backend and authenticated browser tests before implementing agent permissions.

## Cloud staging and restore checklist

- [ ] Record exact app versions and custom apps.
- [ ] Create a genuinely separate staging site, preferably on a separate private bench.
- [ ] Take database, public-file and private-file backups; securely preserve required keys/configuration outside Git and chat.
- [ ] Restore into staging with matching app versions, never over production.
- [ ] Isolate outgoing mail, webhooks, payment integrations and external automation before activating restored services; restrict access.
- [ ] Verify login, record counts, representative records, private files and ERPNext workflows.
- [ ] Record restore duration and backup/revision identifiers without secrets.

## CI compatibility gap

The server workflow selects v15/v16 for dev2, but ERPNext installation only targets
main/main-hotfix and excludes v16. Existing CI does not establish ERPNext v16
same-site compatibility. Resolve its documented v16 bootstrap limitation and add
explicit coverage before declaring the full baseline complete.

## Release and rollback

Require frontend build/tests, v16 backend tests, permission/browser checks and
same-site ERPNext smoke tests. Restore a backup successfully before declaring
recovery verified. Record deployed app revisions and pre-migration backups.
Schema/data rollback requires matching database/files/app revisions, not only
a Git checkout; account for writes after the backup. Production deployment needs
the user's approval after staging verification.

## References

- [Cloud private benches](https://docs.frappe.io/cloud/benches)
- [Cloud restore](https://docs.frappe.io/cloud/sites/migrate-an-existing-site)
- [Bench restore](https://docs.frappe.io/framework/user/en/bench/reference/restore)

## Local backend provisioning

Docker Desktop started. Isolated crm-dev2 database and Redis are healthy; Bench container uses Python 3.14.7, Node 24.21.0 and Bench 5.31.0. Image digests are pinned in docker/local/compose.yaml. Frappe resolved to v16.36.0 at f3f0c0b13c77a419487150a198fed42964e1919e; its required UI and automation modules exist. Application installation and HTTP validation are still in progress. No production access occurred.

## Local backend validation results

- Local site: http://localhost:18000/crm; development login is in docker/local/README.md.
- ERPNext v16.37.0: af63cde4941570ec7b9e12422c68302762cfcf91.
- Frappe v16.36.0: f3f0c0b13c77a419487150a198fed42964e1919e.
- Installed CRM working-tree code, migrated the fresh site and built Linux assets successfully.
- Synthetic users/leads/contacts created; mail muted and scheduler paused.
- Local smoke passed: login, authenticated CRM HTML, CRM Lead/Contact/Customer APIs.
- Sales user A can list its seeded lead and cannot list or directly read B's seeded lead.
- This verifies existing Sales User behavior, not the planned Commission Agent policy.
- Lead test module failed during setUpClass before tests ran: ERPNext-linked fixture traversal references missing Payment Gateway. Log: /workspace/dev2-lead-tests.log inside backend container.
- Web server remains running. Queue workers and realtime are not started; asynchronous workflows remain unverified.
- Production was never accessed. Separate staging and backup restore remain pending.

Agent milestone: nine focused backend tests, session/API-token isolation checks, a headless Edge lead/contact/follow-up workflow and staff smoke checks passed locally. See [agent validation](commission-agents.md). The broader Lead fixture failure and production/staging release gates remain open.
