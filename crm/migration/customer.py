"""Same-site business Customer -> Organization mapping; no financial fields."""

import json

import frappe

from crm.migration.sync_merge import merge_changes

LINK = "CRM ERPNext Customer Link"
LIMIT = 10000


def inventory():
	return (
		frappe.get_all("Customer", fields=["name", "customer_name"], limit_page_length=LIMIT + 1),
		frappe.get_all("CRM Organization", fields=["name", "organization_name"], limit_page_length=LIMIT + 1),
	)


def business_customer(source):
	return source.customer_type in ("Company", "Partnership") and not source.disabled and not source.is_frozen


def sync_batch(settings):
	from crm.migration.sync import parse_mapping, require_admin

	require_admin()
	rows = frappe.get_all(
		"Customer",
		filters={"name": [">", settings.customer_cursor]} if settings.customer_cursor else {},
		pluck="name",
		order_by="name asc",
		limit_page_length=51,
	)
	seen = inventory()
	user_map = parse_mapping(settings.user_map)
	results = []
	for name in rows[:50]:
		frappe.db.savepoint("sync_customer")
		try:
			result = apply_customer(
				name, user_map, seen, sync_addresses=bool(settings.sync_customer_addresses)
			)
		except Exception as exc:
			frappe.db.rollback(save_point="sync_customer")
			result = {"status": "Failed", "issues": [type(exc).__name__]}
		results.append(
			{"source": name, "source_doctype": "Customer", "target_doctype": "CRM Organization", **result}
		)
	return {"results": results, "has_more": len(rows) > 50, "next_after": rows[49] if len(rows) > 50 else ""}


def apply_customer(name, user_map, seen=None, *, sync_addresses=False):
	from crm.migration.opportunity import review
	from crm.migration.sync import creator_context, require_admin

	require_admin()
	source = frappe.get_doc("Customer", name, for_update=True)
	if not business_customer(source):
		return review("individual_disabled_or_frozen_customer_requires_review")
	creator = user_map.get(source.owner, source.owner)
	if creator == "Guest" or not frappe.db.get_value("User", creator, "enabled"):
		return review("creator_missing_or_disabled")
	incoming = {"organization_name": (source.customer_name or "").strip(), "website": source.website or ""}
	if sync_addresses:
		address = source.customer_primary_address or ""
		if address:
			if not frappe.db.exists("Address", address):
				return review("customer_primary_address_missing")
			shared = frappe.get_doc("Address", address, for_update=True)
			if shared.disabled or not any(
				row.link_doctype == "Customer" and row.link_name == source.name for row in shared.links
			):
				return review("customer_primary_address_relationship_requires_review")
		incoming["address"] = address
	if not incoming["organization_name"]:
		return review("organization_name_required")
	link_name = frappe.db.get_value(LINK, {"source_name": source.name}, "name")
	link = frappe.get_doc(LINK, link_name) if link_name else None
	sources, targets = seen if seen is not None else inventory()
	if len(sources) > LIMIT or len(targets) > LIMIT:
		return review("organization_duplicate_inventory_incomplete")
	key = incoming["organization_name"].casefold()
	if any(
		row.name != source.name and (row.customer_name or "").strip().casefold() == key for row in sources
	):
		return review("customer_name_duplicate_candidates")
	if any(
		row.name != (link.target_name if link else None)
		and (row.organization_name or "").strip().casefold() == key
		for row in targets
	):
		return review("organization_duplicate_candidates")
	if not link:
		with creator_context(creator):
			target = frappe.get_doc({"doctype": "CRM Organization", **incoming}).insert(
				ignore_permissions=True
			)
		frappe.get_doc(
			{
				"doctype": LINK,
				"source_name": source.name,
				"target_name": target.name,
				"source_snapshot": json.dumps(incoming),
				"target_snapshot": json.dumps(snapshot(target)),
				"source_creator": source.owner,
				"source_created": source.creation,
				"source_modified": source.modified,
			}
		).insert(ignore_permissions=True)
		# Keep duplicate checks current within this batch.
		targets.append(frappe._dict(name=target.name, organization_name=target.organization_name))
		return {"status": "Created", "target": target.name}
	if not frappe.db.exists("CRM Organization", link.target_name):
		return review("target_missing")
	target = frappe.get_doc("CRM Organization", link.target_name, for_update=True)
	if target.owner != creator or source.owner != link.source_creator:
		return review("organization_creator_changed")
	previous, baseline = json.loads(link.source_snapshot), json.loads(link.target_snapshot)
	# Upgrades and first opt-in must not adopt an existing CRM address as a
	# disposable baseline. Disabling sync preserves the last tracked snapshots.
	if sync_addresses and "address" not in previous:
		if target.address and target.address != incoming["address"]:
			return review("existing_organization_address_requires_review")
		baseline["address"] = target.address or ""
	changes, conflicts = merge_changes(incoming, previous, snapshot(target), baseline)
	if conflicts:
		return {
			"status": "Review",
			"target": target.name,
			"issues": ["field_conflict:" + field for field in conflicts],
		}
	if changes:
		target.update(changes)
		target.save(ignore_permissions=True)
		for row in targets:
			if row.name == target.name:
				row.organization_name = target.organization_name
	for field in incoming:
		if incoming[field] != previous.get(field):
			baseline[field] = snapshot(target)[field]
	link.source_snapshot = json.dumps(previous | incoming)
	link.target_snapshot = json.dumps(baseline)
	link.source_modified = source.modified
	link.save(ignore_permissions=True)
	return {"status": "Updated" if changes else "Unchanged", "target": target.name}


def snapshot(doc):
	return {
		"organization_name": doc.organization_name or "",
		"website": doc.website or "",
		"address": doc.address or "",
	}
