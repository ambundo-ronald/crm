#!/usr/bin/env bash
set -euo pipefail
cd /workspace/frappe-bench
tar -C /source/crm -cf - crm/api/productivity.py crm/api/agent.py crm/permissions/commission_agent.py crm/tests/test_productivity.py crm/public/js/agent.js crm/www/crm-agent.html | tar -C apps/crm -xf -
uvx ruff check --fix apps/crm/crm/api/productivity.py apps/crm/crm/api/agent.py apps/crm/crm/tests/test_productivity.py
uvx ruff format apps/crm/crm/api/productivity.py apps/crm/crm/api/agent.py apps/crm/crm/tests/test_productivity.py
bench --site crm.localhost clear-cache
bench --site crm.localhost run-tests --app crm --module crm.tests.test_productivity
bench --site crm.localhost run-tests --app crm --module crm.tests.test_commission_agent
bench --site crm.localhost run-tests --app crm --module crm.tests.test_agent_admin
