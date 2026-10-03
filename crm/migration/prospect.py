"""Opt-in company Prospect mapping; lead/contact relationships remain separate."""

import frappe

from crm.migration.customer import apply_organization, inventory

LINK = "CRM ERPNext Prospect Link"


def apply_prospect(name, user_map, seen=None):
	return apply_organization("Prospect", name, user_map, seen)


def sync_batch(settings):
	from crm.migration.sync import parse_mapping, require_admin

	require_admin()
	rows = frappe.get_all(
		"Prospect",
		filters={"name": [">", settings.prospect_cursor]} if settings.prospect_cursor else {},
		pluck="name",
		order_by="name asc",
		limit_page_length=51,
	)
	seen, user_map, results = inventory("Prospect"), parse_mapping(settings.user_map), []
	for name in rows[:50]:
		frappe.db.savepoint("sync_prospect")
		try:
			result = apply_prospect(name, user_map, seen)
		except Exception as exc:
			frappe.db.rollback(save_point="sync_prospect")
			result = {"status": "Failed", "issues": [type(exc).__name__]}
		results.append(
			{"source": name, "source_doctype": "Prospect", "target_doctype": "CRM Organization", **result}
		)
	return {"results": results, "has_more": len(rows) > 50, "next_after": rows[49] if len(rows) > 50 else ""}
