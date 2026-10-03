"""Conservative same-site Opportunity -> Deal sync. No contacts or reverse writes."""

import json
import math

import frappe

from crm.migration.sync_merge import merge_changes

LINK = "CRM ERPNext Opportunity Link"
DEFAULT_STATUSES = {"Open": "Qualification", "Replied": "Qualification", "Quotation": "Proposal/Quotation"}


def sync_batch(settings):
	from crm.migration.sync import parse_mapping, require_admin

	require_admin()

	status_map = DEFAULT_STATUSES | parse_mapping(settings.opportunity_status_map)
	user_map = parse_mapping(settings.user_map)
	rows = frappe.get_all(
		"Opportunity",
		filters={"name": [">", settings.opportunity_cursor]} if settings.opportunity_cursor else {},
		pluck="name",
		order_by="name asc",
		limit_page_length=51,
	)
	results = []
	for name in rows[:50]:
		frappe.db.savepoint("sync_opportunity")
		try:
			result = apply_opportunity(name, status_map, user_map)
		except Exception as exc:
			frappe.db.rollback(save_point="sync_opportunity")
			result = {"status": "Failed", "issues": [type(exc).__name__]}
		results.append(
			{"source": name, "source_doctype": "Opportunity", "target_doctype": "CRM Deal", **result}
		)
	return {"results": results, "has_more": len(rows) > 50, "next_after": rows[49] if len(rows) > 50 else ""}


def review(*issues):
	return {"status": "Review", "issues": list(issues)}


def apply_opportunity(name, status_map, user_map):
	from crm.migration.sync import LINK as LEAD_LINK
	from crm.migration.sync import creator_context, require_admin
	from crm.permissions.commission_agent import is_agent

	require_admin()
	source = frappe.get_doc("Opportunity", name, for_update=True)
	if source.docstatus == 2 or source.status not in DEFAULT_STATUSES:
		return review("opportunity_lifecycle_requires_review")
	lead = organization = None
	lead_name = organization_name = None
	if source.opportunity_from == "Lead":
		lead_name = frappe.db.get_value(LEAD_LINK, {"source_name": source.party_name}, "target_name")
		if not lead_name or not frappe.db.exists("CRM Lead", lead_name):
			return review("sync_source_lead_first")
		lead = frappe.get_doc("CRM Lead", lead_name, for_update=True)
		erp_lead = frappe.get_doc("Lead", source.party_name)
		if erp_lead.disabled or erp_lead.unsubscribed or erp_lead.status == "Do Not Contact":
			return review("source_lead_contact_consent_requires_review")
		party_filter = {"lead": lead.name}
		mapping_filter = {"target_lead": lead.name}
	elif source.opportunity_from == "Customer":
		from crm.migration.customer import LINK as CUSTOMER_LINK
		from crm.migration.customer import business_customer

		if not frappe.db.exists("Customer", source.party_name):
			return review("customer_mapping_required")
		customer = frappe.get_doc("Customer", source.party_name, for_update=True)
		if not business_customer(customer):
			return review("customer_lifecycle_requires_review")
		organization_name = frappe.db.get_value(CUSTOMER_LINK, {"source_name": customer.name}, "target_name")
		if not organization_name or not frappe.db.exists("CRM Organization", organization_name):
			return review("sync_source_customer_first")
		organization = frappe.get_doc("CRM Organization", organization_name, for_update=True)
		party_filter = {"organization": organization.name}
		mapping_filter = {"target_organization": organization.name}
	else:
		return review("prospect_mapping_required")
	creator = user_map.get(source.owner, source.owner)
	if creator == "Guest" or not frappe.db.get_value("User", creator, "enabled"):
		return review("creator_missing_or_disabled")
	assignee = user_map.get(source.opportunity_owner, source.opportunity_owner)
	if (
		not assignee
		or not frappe.db.get_value("User", assignee, "enabled")
		or frappe.db.get_value("User", assignee, "user_type") != "System User"
		or is_agent(assignee)
	):
		return review("opportunity_salesperson_requires_review")
	base_currency = frappe.db.get_single_value("FCRM Settings", "currency") or "USD"
	if source.currency != base_currency:
		return review("currency_conversion_requires_review")
	if source.items:
		return review("opportunity_products_require_mapping")
	amount = float(source.opportunity_amount or 0)
	if not math.isfinite(amount) or amount < 0:
		return review("invalid_opportunity_amount")
	link_name = frappe.db.get_value(LINK, {"source_name": source.name}, "name")
	link = frappe.get_doc(LINK, link_name) if link_name else None
	if link:
		if not frappe.db.exists("CRM Deal", link.target_name):
			return review("target_missing")
		target = frappe.get_doc("CRM Deal", link.target_name, for_update=True)
		if (
			source.party_name != link.source_party
			or (link.source_party_doctype or "Lead") != source.opportunity_from
			or (lead_name or "") != (link.target_lead or "")
			or (target.lead or "") != (lead_name or "")
			or (
				source.opportunity_from == "Customer"
				and (
					organization_name != link.target_organization or target.organization != organization_name
				)
			)
			or target.owner != creator
			or source.owner != link.source_creator
		):
			return review("opportunity_relationship_or_creator_changed")
		if target.currency != source.currency or target.products:
			return review("deal_currency_or_products_changed")
		if frappe.db.get_value("CRM Deal Status", target.status, "type") not in ("Open", "Ongoing"):
			return review("deal_lifecycle_requires_review")
	else:
		if lead and lead.converted:
			return review("lead_already_converted")
		# Existing manually-created deals are candidates, never automatic matches.
		existing = frappe.get_all("CRM Deal", filters=party_filter, pluck="name", limit_page_length=1001)
		if len(existing) > 1000:
			return review("deal_duplicate_inventory_incomplete")
		mapped = set(frappe.get_all(LINK, filters=mapping_filter, pluck="target_name"))
		if set(existing) - mapped:
			return review("existing_deal_requires_review")
		status = status_map.get(source.status)
		if not status or frappe.db.get_value("CRM Deal Status", status, "type") not in ("Open", "Ongoing"):
			return review("opportunity_status_mapping_requires_review")
		target = frappe.get_doc(
			{
				"doctype": "CRM Deal",
				"lead": lead_name,
				"lead_name": lead.lead_name if lead else None,
				"organization": organization_name,
				"organization_name": lead.organization if lead else organization.organization_name,
				"first_name": lead.first_name if lead else None,
				"last_name": lead.last_name if lead else None,
				"status": status,
				"deal_owner": assignee,
				"currency": source.currency,
				"exchange_rate": 1,
			}
		)
	# The existing outbound integration can create ERPNext customers on any save.
	outbound = frappe.get_single("ERPNext CRM Settings")
	if (
		outbound.enabled
		and outbound.create_customer_on_status_change
		and outbound.deal_status == target.status
	):
		return review("outbound_customer_automation_requires_review")
	incoming = {"deal_value": amount, "expected_closure_date": str(source.expected_closing or "")}
	if not link:
		target.update(incoming)
		with creator_context(creator):
			target.insert(ignore_permissions=True)
		frappe.get_doc(
			{
				"doctype": LINK,
				"source_name": source.name,
				"target_name": target.name,
				"source_party": source.party_name,
				"target_lead": lead_name,
				"target_organization": organization_name,
				"source_party_doctype": source.opportunity_from,
				"source_snapshot": json.dumps(incoming),
				"target_snapshot": json.dumps(snapshot(target)),
				"source_creator": source.owner,
				"source_created": source.creation,
				"source_modified": source.modified,
			}
		).insert(ignore_permissions=True)
		return {"status": "Created", "target": target.name}
	previous = json.loads(link.source_snapshot)
	baseline = json.loads(link.target_snapshot)
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
	for field in incoming:
		if incoming[field] != previous.get(field):
			baseline[field] = snapshot(target)[field]
	link.source_snapshot = json.dumps(incoming)
	link.target_snapshot = json.dumps(baseline)
	link.source_modified = source.modified
	link.save(ignore_permissions=True)
	return {"status": "Updated" if changes else "Unchanged", "target": target.name}


def snapshot(doc):
	return {
		"deal_value": float(doc.deal_value or 0),
		"expected_closure_date": str(doc.expected_closure_date or ""),
	}
