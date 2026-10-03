"""Read-only staging evidence; never claims that an unknown site is isolated."""

import frappe
from frappe.utils.change_log import get_versions

from crm.migration.extensions import SOURCES, field_inventory
from crm.migration.sync import SETTINGS, require_admin


@frappe.whitelist(methods=["GET", "POST"])
def report():
	require_admin()
	settings = frappe.get_single(SETTINGS)
	inventory = []
	if "erpnext" in frappe.get_installed_apps():
		for source, (mapping, target) in SOURCES.items():
			inventory.append(
				{
					"source": source,
					"source_count": frappe.db.count(source),
					"mapped_count": frappe.db.count(mapping),
					"target_doctype": target,
					"custom_fields": field_inventory(source),
				}
			)
	return {
		"site": frappe.local.site,
		"versions": get_versions(),
		"inventory": inventory,
		"observations": {
			"sync_enabled": bool(settings.enabled),
			"automatic_sync": bool(settings.automatic),
			"mail_muted": bool(frappe.conf.get("mute_emails")),
			"scheduler_paused": bool(frappe.conf.get("pause_scheduler")),
		},
		"unverified_gates": [
			"separate_non_production_site",
			"production_version_and_custom_app_match",
			"sanitized_or_restored_representative_data",
			"database_and_public_private_files_restored",
			"outbound_integrations_isolated",
			"sample_reconciliation_and_permissions",
			"scheduler_worker_end_to_end",
			"rollback_rehearsal",
		],
		"ready_for_production": False,
	}
