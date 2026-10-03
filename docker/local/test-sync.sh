#!/usr/bin/env bash
set -euo pipefail
cd /workspace/frappe-bench
tar -C /source/crm -cf - crm/migration crm/hooks.py crm/install.py crm/fcrm/doctype/crm_erpnext_sync_settings crm/fcrm/doctype/crm_erpnext_sync_link crm/fcrm/doctype/crm_erpnext_sync_run crm/fcrm/doctype/crm_erpnext_opportunity_link crm/tests/test_erpnext_sync.py crm/tests/test_sync_merge.py crm/tests/test_opportunity_sync.py | tar -C apps/crm -xf -
cd apps/crm
uvx ruff check --fix crm/migration crm/tests/test_erpnext_sync.py crm/tests/test_sync_merge.py crm/tests/test_opportunity_sync.py crm/fcrm/doctype/crm_erpnext_sync_* crm/fcrm/doctype/crm_erpnext_opportunity_link
uvx ruff format crm/migration crm/tests/test_erpnext_sync.py crm/tests/test_sync_merge.py crm/tests/test_opportunity_sync.py crm/fcrm/doctype/crm_erpnext_sync_* crm/fcrm/doctype/crm_erpnext_opportunity_link
cd /workspace/frappe-bench
bench --site crm.localhost migrate > /workspace/dev2-sync-migrate.log 2>&1 || { tail -60 /workspace/dev2-sync-migrate.log; exit 1; }
env/bin/python -m unittest crm.tests.test_sync_merge
bench --site crm.localhost run-tests --app crm --module crm.tests.test_erpnext_sync
bench --site crm.localhost run-tests --app crm --module crm.tests.test_opportunity_sync
