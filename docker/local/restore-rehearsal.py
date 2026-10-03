"""Rehearse a local-only restore into a NEW site. Run with the bench Python."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time

import frappe

BENCH = Path("/workspace/frappe-bench")
SOURCE = "crm.localhost"
TARGET = "crm-restore.localhost"
TABLES = ("Lead", "Opportunity", "Customer", "Prospect", "CRM Lead", "CRM Deal", "CRM Organization", "Contact", "Address", "Comment", "Communication", "ToDo", "Event", "File", "CRM ERPNext Sync Link", "CRM ERPNext Customer Link", "CRM ERPNext Prospect Link", "CRM ERPNext Opportunity Link", "CRM ERPNext Contact Link", "CRM ERPNext Address Link")


def connect(site):
    frappe.init(site=site, sites_path=str(BENCH / "sites"))
    frappe.connect()
    frappe.set_user("Administrator")


def snapshot(site):
    connect(site)
    try:
        data = {}
        for doctype in TABLES:
            names = frappe.get_all(doctype, pluck="name", order_by="name", limit_page_length=1001)
            if len(names) > 1000:
                raise RuntimeError("This rehearsal is restricted to the small local fixture inventory")
            records = [frappe.get_doc(doctype, name).as_dict() for name in names]
            payload = json.dumps(records, sort_keys=True, default=str).encode()
            data[doctype] = {"count": len(names), "sha256": hashlib.sha256(payload).hexdigest()}
        return {"records": data, "apps": sorted(frappe.get_installed_apps())}
    finally:
        frappe.destroy()


def files(site):
    result = {}
    base = BENCH / "sites" / site
    for folder in ("public/files", "private/files"):
        for path in sorted((base / folder).rglob("*")):
            if path.is_file():
                result[str(path.relative_to(base))] = hashlib.sha256(path.read_bytes()).hexdigest()
    return result


def main():
    if Path.cwd().resolve() != BENCH or (BENCH / "sites" / TARGET).exists():
        raise RuntimeError("Run in the local bench; the restore destination must not exist")
    os.chdir(BENCH / "sites")
    source_config = json.loads((BENCH / "sites" / SOURCE / "site_config.json").read_text())
    if not source_config.get("mute_emails") or not source_config.get("pause_scheduler"):
        raise RuntimeError("Local source must have mail muted and scheduler paused")
    connect(SOURCE)
    try:
        if frappe.db.get_single_value("CRM ERPNext Sync Settings", "enabled"):
            raise RuntimeError("Disable source sync before the rehearsal")
    finally:
        frappe.destroy()
    evidence = Path("/workspace/dev2-restore-evidence") / time.strftime("%Y%m%d-%H%M%S")
    evidence.mkdir(parents=True, mode=0o700)
    started = time.monotonic()
    before, source_files = snapshot(SOURCE), files(SOURCE)
    def run(args, label):
        with (evidence / (label + ".log")).open("w") as log:
            subprocess.run(["bench", *args], cwd=BENCH, input="y\n", text=True, stdout=log, stderr=subprocess.STDOUT, check=True)
        print(label + " completed", flush=True)
    run(["--site", SOURCE, "backup", "--with-files", "--backup-path-db", str(evidence / "database.sql.gz"), "--backup-path-files", str(evidence / "public.tar"), "--backup-path-private-files", str(evidence / "private.tar"), "--backup-path-conf", str(evidence / "site-config.json")], "backup")
    run(["new-site", TARGET, "--db-root-username", "root", "--db-root-password", "local-dev2-db", "--admin-password", "Local-Dev2-Only-2026", "--mariadb-user-host-login-scope=%"], "new-site")
    config_path = BENCH / "sites" / TARGET / "site_config.json"
    config = json.loads(config_path.read_text())
    config.update({"mute_emails": 1, "pause_scheduler": 1, "developer_mode": 1, "allow_tests": True})
    for key in ("encryption_key", "backup_encryption_key"):
        if key in source_config:
            config[key] = source_config[key]
    config_path.write_text(json.dumps(config, indent=2))
    run(["--site", TARGET, "restore", str(evidence / "database.sql.gz"), "--db-root-username", "root", "--db-root-password", "local-dev2-db", "--with-public-files", str(evidence / "public.tar"), "--with-private-files", str(evidence / "private.tar")], "restore")
    run(["--site", TARGET, "migrate"], "migrate")
    after = snapshot(TARGET)
    target_files = files(TARGET)
    assert before == after, "Restored record snapshots or installed apps differ"
    assert source_files == target_files, "Restored public/private file hashes differ"
    assert source_files, "Seed at least one fixture file before restore validation"
    connect(TARGET)
    try:
        from frappe.utils.password import check_password
        assert check_password("Administrator", "Local-Dev2-Only-2026") == "Administrator"
        assert not frappe.db.get_single_value("CRM ERPNext Sync Settings", "enabled")
        assert frappe.conf.mute_emails and frappe.conf.pause_scheduler
    finally:
        frappe.destroy()
    result = {"source": SOURCE, "destination": TARGET, "duration_seconds": round(time.monotonic() - started, 1), "records": after["records"], "file_count": len(target_files), "public_file_count": sum(name.startswith("public/") for name in target_files), "private_file_count": sum(name.startswith("private/") for name in target_files), "record_hashes_match": True, "file_hashes_match": True, "administrator_password_verified": True, "cloud_staging_verified": False}
    (evidence / "result.json").write_text(json.dumps(result, indent=2))
    for path in evidence.iterdir():
        if path.is_file():
            os.chmod(path, 0o600)
    print(json.dumps({"result": str(evidence / "result.json"), "duration_seconds": result["duration_seconds"], "records_match": True, "files_match": True, "cloud_staging_verified": False}), flush=True)


if __name__ == "__main__":
    main()
