#!/usr/bin/env bash
set -euo pipefail
# Trust only the explicit read-only source repository mounted by this stack.
git config --global --add safe.directory /source/crm/.git
cd /workspace
if [ ! -d frappe-bench/apps/frappe ]; then
  bench init --frappe-branch v16.36.0 --skip-assets --skip-redis-config-generation frappe-bench
fi
cd frappe-bench
bench set-config -g db_host db
bench set-config -g redis_cache redis://redis:6379/0
bench set-config -g redis_queue redis://redis:6379/1
bench set-config -g redis_socketio redis://redis:6379/2
if [ ! -d apps/erpnext ]; then
  bench get-app --branch v16.37.0 --skip-assets erpnext
fi
if [ ! -d apps/crm ]; then
  bench get-app --skip-assets file:///source/crm
fi
# Copy current working-tree code; preserve Linux dependencies and git metadata.
tar -C /source/crm --exclude=.git --exclude=node_modules --exclude=frontend/node_modules \
  --exclude=frappe-ui --exclude=crm/public/frontend --exclude=crm/www/crm.html \
  --exclude=frontend/coverage --exclude=playwright-report --exclude=test-results \
  -cf - . | tar -C apps/crm -xf -
bench pip install -e apps/crm
if [ ! -f sites/crm.localhost/site_config.json ]; then
  bench new-site crm.localhost --db-root-username root --db-root-password local-dev2-db \
    --admin-password Local-Dev2-Only-2026 --mariadb-user-host-login-scope='%'
fi
bench --site crm.localhost set-config mute_emails 1
bench --site crm.localhost set-config pause_scheduler 1
bench --site crm.localhost set-config developer_mode 1
bench --site crm.localhost set-config allow_tests true
bench --site crm.localhost install-app erpnext
bench --site crm.localhost install-app crm
bench --site crm.localhost migrate
bench use crm.localhost
bench build
cp /source/crm/docker/local/seed.py apps/crm/crm/local_dev_seed.py
bench --site crm.localhost execute crm.local_dev_seed.run
bench version
echo 'Local setup finished. Start with the command in docker/local/README.md.'
