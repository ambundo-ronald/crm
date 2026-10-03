#!/usr/bin/env bash
set -euo pipefail
cd /workspace/frappe-bench
tar -C /source/crm -cf - crm/migration crm/tests/test_migration_planner.py crm/tests/test_migration_preview.py | tar -C apps/crm -xf -
cd apps/crm
uvx ruff check --fix crm/migration crm/tests/test_migration_planner.py crm/tests/test_migration_preview.py
uvx ruff format crm/migration crm/tests/test_migration_planner.py crm/tests/test_migration_preview.py
cd /workspace/frappe-bench
env/bin/python -m unittest crm.tests.test_migration_planner
bench --site crm.localhost run-tests --app crm --module crm.tests.test_migration_preview