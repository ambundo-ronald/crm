"""Administrative, read-only same-site ERPNext migration preview.

Run with bench execute; intentionally not whitelisted and has no apply mode.
"""

import frappe
from frappe import _
from frappe.utils import cint

from crm.migration.planner import DEFAULT_STATUSES, FIELD_MAP, plan_leads
from crm.permissions.commission_agent import is_agent

INVENTORY_LIMIT = 10000


def preview(limit=100, after=None, status_map=None, user_map=None):
	if is_agent() or (frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles()):
		frappe.throw(_("Only administrators can preview an ERPNext migration"), frappe.PermissionError)
	if "erpnext" not in frappe.get_installed_apps():
		frappe.throw(_("This preview requires ERPNext on the same site"), frappe.ValidationError)
	limit = cint(limit)
	if not 1 <= limit <= 500:
		frappe.throw(_("Choose a batch size between 1 and 500"), frappe.ValidationError)
	if after is not None and (not isinstance(after, str) or len(after) > 140):
		frappe.throw(_("Invalid source cursor"), frappe.ValidationError)

	def mapping(value):
		value = frappe.parse_json(value) if isinstance(value, str) else value
		value = {} if value is None else value
		if not isinstance(value, dict) or any(
			not isinstance(k, str) or not isinstance(v, str) for k, v in value.items()
		):
			frappe.throw(_("Mappings must contain text keys and values"), frappe.ValidationError)
		return value

	status_map, user_map = mapping(status_map), mapping(user_map)
	fields = [
		"name",
		"owner",
		"creation",
		"modified",
		"status",
		"lead_owner",
		"disabled",
		"unsubscribed",
		*FIELD_MAP,
	]
	source_meta = frappe.get_meta("Lead")
	target_meta = frappe.get_meta("CRM Lead")
	missing = [field for field in FIELD_MAP if not source_meta.has_field(field)]
	missing += ["CRM Lead." + field for field in FIELD_MAP.values() if not target_meta.has_field(field)]
	if missing:
		frappe.throw(
			_("Incompatible migration fields: {0}").format(", ".join(missing)), frappe.ValidationError
		)
	sources = frappe.get_all("Lead", fields=fields, order_by="name asc", limit_page_length=INVENTORY_LIMIT)
	targets = frappe.get_all(
		"CRM Lead",
		fields=["name", "email", "mobile_no", "phone"],
		order_by="name asc",
		limit_page_length=INVENTORY_LIMIT,
	)
	counts = {
		dt: frappe.db.count(dt)
		for dt in ("Lead", "Opportunity", "Customer", "Contact", "Address", "CRM Lead", "CRM Deal")
	}
	inventory_complete = counts["Lead"] <= INVENTORY_LIMIT and counts["CRM Lead"] <= INVENTORY_LIMIT
	# Page independently of the duplicate-scan bound; never silently stop at 10,000 leads.
	batch = frappe.get_all(
		"Lead",
		filters={"name": [">", after]} if after else {},
		fields=fields,
		order_by="name asc",
		limit_page_length=limit + 1,
	)
	has_more = len(batch) > limit
	batch = batch[:limit]
	if batch:
		links = frappe.get_all(
			"Dynamic Link",
			filters={
				"parenttype": "Contact",
				"parentfield": "links",
				"link_doctype": "Lead",
				"link_name": ["in", [row.name for row in batch]],
			},
			fields=["parent", "link_name"],
		)
		for row in batch:
			row["contacts"] = [link.parent for link in links if link.link_name == row.name]
	users = {row.name: row for row in frappe.get_all("User", fields=["name", "enabled", "user_type"])}
	for role in frappe.get_all(
		"Has Role", filters={"parenttype": "User", "role": "Commission Agent"}, fields=["parent"]
	):
		if role.parent in users:
			users[role.parent]["is_agent"] = True
	statuses = frappe.get_all("CRM Lead Status", pluck="name")
	proposals = plan_leads(
		sources,
		targets,
		users,
		statuses,
		frappe.local.site,
		status_map=status_map,
		user_map=user_map,
		batch=batch,
		inventory_complete=inventory_complete,
	)
	for row in proposals:
		for field in target_meta.fields:
			if field.reqd and not field.default and field.fieldname not in row["proposed_fields"]:
				row["issues"].append("unmapped_required_target_field:" + field.fieldname)
				row["action"] = "review"
	return {
		"mode": "read_only_preview",
		"source_site": frappe.local.site,
		"same_site": True,
		"counts": counts,
		"duplicate_inventory_complete": inventory_complete,
		"summary": {
			"review": sum(row["action"] == "review" for row in proposals),
			"create_candidate": sum(row["action"] == "create_candidate" for row in proposals),
		},
		"status_mapping": DEFAULT_STATUSES | status_map,
		"available_target_statuses": statuses,
		"source_custom_fields": frappe.get_all("Custom Field", filters={"dt": "Lead"}, pluck="fieldname"),
		"target_custom_fields": frappe.get_all("Custom Field", filters={"dt": "CRM Lead"}, pluck="fieldname"),
		"proposals": proposals,
		"has_more": has_more,
		"next_after": batch[-1].name if has_more and batch else None,
		"not_migrated": [
			"Opportunity/CRM Deal",
			"Customer/CRM Organization",
			"shared Contact/Address links",
			"industry/territory mappings",
			"custom fields",
			"notes/communications/files",
			"tasks/events",
			"consent/lifecycle flags",
			"source mapping storage and checkpoints",
		],
		"notice": "Proposals only. No records written. An approved mapping and separate importer are required.",
	}
