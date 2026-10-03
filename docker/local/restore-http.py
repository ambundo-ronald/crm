"""HTTP permission checks using a temporary server for the restored local site."""
import json
import os
from pathlib import Path
import signal
import subprocess
import time

import requests

bench = Path("/workspace/frappe-bench")
site = "crm-restore.localhost"
if Path.cwd().resolve() != bench or not (bench / "sites" / site / "site_config.json").exists():
    raise RuntimeError("Run only inside the local bench after the restore rehearsal")
config = json.loads((bench / "sites" / site / "site_config.json").read_text())
if not config.get("mute_emails") or not config.get("pause_scheduler"):
    raise RuntimeError("Restored site must remain isolated")
base = "http://127.0.0.1:8001"
with open("/workspace/dev2-restore-http.log", "w") as log:
    process = subprocess.Popen(["bench", "--site", site, "serve", "--port", "8001", "--noreload"], stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
    try:
        for _ in range(60):
            if process.poll() is not None:
                raise RuntimeError("Temporary server failed; inspect local restore HTTP log")
            try:
                if requests.get(base + "/api/method/ping", timeout=1).status_code == 200:
                    break
            except requests.RequestException:
                pass
            time.sleep(0.25)
        with requests.Session() as admin, requests.Session() as agent, requests.Session() as guest:
            assert admin.post(base + "/api/method/login", data={"usr": "Administrator", "pwd": "Local-Dev2-Only-2026"}, timeout=20).status_code == 200
            response = admin.get(base + "/api/method/crm.migration.validation.report", timeout=20)
            response.raise_for_status()
            data = response.json()["message"]
            assert data["site"] == site
            assert not data["observations"]["sync_enabled"]
            assert data["observations"]["mail_muted"] and data["observations"]["scheduler_paused"]
            assert admin.get(base + "/crm", timeout=20).status_code == 200
            response = admin.get(base + "/api/resource/File", params={"fields": json.dumps(["file_url", "is_private"]), "filters": json.dumps({"attached_to_doctype": "Prospect", "attached_to_name": "Dev2 Prospect Browser Company", "is_private": 1})}, timeout=20)
            response.raise_for_status()
            file = response.json()["data"][0]
            assert file["is_private"] == 1
            assert admin.get(base + file["file_url"], timeout=20).text == "Synthetic local restore fixture"
            assert guest.get(base + file["file_url"], timeout=20).status_code == 403
            assert agent.post(base + "/api/method/login", data={"usr": "dev2.agent.a@example.invalid", "pwd": "Local-Dev2-Only-2026"}, timeout=20).status_code == 200
            assert agent.get(base + file["file_url"], timeout=20).status_code == 403
            assert agent.get(base + "/api/method/crm.migration.validation.report", timeout=20).status_code == 403
            assert agent.get(base + "/api/method/crm.api.agent.list_leads", timeout=20).status_code == 200
            print("PASS: restored site identity, HTTP login, CRM page, private-file protection and agent isolation")
    finally:
        os.killpg(process.pid, signal.SIGTERM)
        process.wait(timeout=10)
