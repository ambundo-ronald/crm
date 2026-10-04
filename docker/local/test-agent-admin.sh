#!/usr/bin/env bash
set -euo pipefail
cd /workspace/frappe-bench
tar -C /source/crm -cf - crm/api/agent_admin.py crm/permissions/commission_agent.py crm/fcrm/doctype/crm_agent_access_log crm/tests/test_agent_admin.py | tar -C apps/crm -xf -
uvx ruff check --fix apps/crm/crm/api/agent_admin.py apps/crm/crm/tests/test_agent_admin.py apps/crm/crm/fcrm/doctype/crm_agent_access_log
uvx ruff format apps/crm/crm/api/agent_admin.py apps/crm/crm/tests/test_agent_admin.py apps/crm/crm/fcrm/doctype/crm_agent_access_log
bench --site crm.localhost migrate > /tmp/agent-admin-migrate.log 2>&1 || { tail -80 /tmp/agent-admin-migrate.log; exit 1; }
bench --site crm.localhost run-tests --app crm --module crm.tests.test_agent_admin
bench --site crm.localhost run-tests --app crm --module crm.tests.test_commission_agent
