#!/usr/bin/env bash
set -euo pipefail
cd /workspace/frappe-bench
tar -C /source/crm -cf - crm/permissions/commission_agent.py crm/api/agent.py crm/api/appointments.py crm/api/activities.py crm/api/__init__.py crm/hooks.py crm/install.py crm/www/crm_agent.py crm/www/crm-agent.html crm/public/js/agent.js crm/public/css/agent.css crm/tests/test_commission_agent.py | tar -C apps/crm -xf -
bench --site crm.localhost execute crm.permissions.commission_agent.install_role
bench --site crm.localhost clear-cache
bench --site crm.localhost run-tests --app crm --module crm.tests.test_commission_agent
