"""Projected, ownership-scoped contracts for agents using the standard CRM UI.

No DocPerm is granted. The HTTP guard remains default-deny; only the contracts
below are reachable. Staff requests continue through their original handlers.
"""

import re

import frappe
from frappe.utils import cint

from crm.api import agent
from crm.permissions.commission_agent import is_agent, require_agent

FIELDS = {
	"CRM Lead": (*agent.LEAD_FIELDS, "lead_name", "creation", "owner"),
	"Contact": (*agent.CONTACT_FIELDS, "full_name", "modified", "creation"),
	"CRM Task": (
		"name",
		"title",
		"description",
		"status",
		"priority",
		"due_date",
		"reference_doctype",
		"reference_docname",
		"modified",
		"creation",
	),
}
EDITABLE = {
	"CRM Lead": agent.EDIT_FIELDS,
	"Contact": frozenset(("first_name", "last_name", "email_id", "mobile_no")),
	"CRM Task": frozenset(
		("title", "description", "status", "priority", "due_date", "reference_doctype", "reference_docname")
	),
}


def contact_scope(user):
	return frappe.db.sql(
		"""select c.name from tabContact c where c.owner=%s or exists (
		select 1 from `tabDynamic Link` dl inner join `tabCRM Lead` l on l.name=dl.link_name
		where dl.parent=c.name and dl.parenttype='Contact' and dl.parentfield='links'
		and dl.link_doctype='CRM Lead' and l.owner=%s)""",
		(user, user),
		pluck=True,
	)


def scope(doctype):
	user = require_agent()
	if doctype == "CRM Lead":
		return [["owner", "=", user]]
	if doctype == "Contact":
		return [["name", "in", contact_scope(user) or [""]]]
	if doctype == "CRM Task":
		leads = frappe.get_all("CRM Lead", filters={"owner": user}, pluck="name")
		return [
			["owner", "=", user],
			["reference_doctype", "=", "CRM Lead"],
			["reference_docname", "in", leads or [""]],
		]
	agent.deny()


def document(doctype, name):
	name = agent.record_name(name)
	if not frappe.get_all(doctype, filters=[*scope(doctype), ["name", "=", name]], limit_page_length=1):
		agent.deny()
	return frappe.get_doc(doctype, name)


def can_edit(doc):
	if doc.doctype == "Contact":
		return (
			doc.owner == frappe.session.user
			and not any(
				row.link_doctype != "CRM Lead"
				or not frappe.db.exists("CRM Lead", {"name": row.link_name, "owner": frappe.session.user})
				for row in doc.links
			)
			and not frappe.db.exists("CRM Contacts", {"contact": doc.name})
		)
	return not (doc.doctype == "CRM Lead" and doc.converted)


def projected(doc):
	return {
		"doctype": doc.doctype,
		**agent.project(doc, FIELDS[doc.doctype]),
		"__agent_read_only": not can_edit(doc),
	}


def fields(doctype):
	if doctype not in FIELDS:
		agent.deny()
	result = []
	for name in FIELDS[doctype]:
		df = frappe.get_meta(doctype).get_field(name)
		field = {"fieldname": name, "label": name.replace("_", " ").title(), "fieldtype": "Data"}
		if df:
			field.update({key: df.get(key) for key in ("label", "fieldtype", "options", "reqd")})
		# Do not deliver custom scripts, fetch_from, dependencies or arbitrary links.
		if field["fieldtype"] in ("Link", "Dynamic Link"):
			field.update(fieldtype="Data", options=None)
		if name == "status" and doctype == "CRM Lead":
			field.update(fieldtype="Select", options="\n".join(agent.STATUSES))
		field["read_only"] = int(name not in EDITABLE[doctype])
		if doctype == "CRM Task" and name == "reference_doctype":
			field.update(default="CRM Lead", read_only=1)
		if doctype == "CRM Task" and name == "reference_docname":
			field.update(fieldtype="Link", options="CRM Lead", label="Lead", reqd=1)
		result.append(field)
	return result


def layout(doctype, side=False):
	visible = [f for f in fields(doctype) if f["fieldname"] in EDITABLE[doctype]]
	if side:
		for f in visible:
			if f["fieldtype"] == "Select":
				f["options"] = [{"label": v, "value": v} for v in (f.get("options") or "").split("\n")]
	sections = [{"name": "details", "label": "Details", "columns": [{"name": "details", "fields": visible}]}]
	return sections if side else [{"name": "details", "label": "Details", "sections": sections}]


def filters_for(doctype, value):
	value = frappe.parse_json(value) if isinstance(value, str) else value
	if not value:
		return []
	if not isinstance(value, dict):
		agent.deny()
	result = []
	for key, val in value.items():
		if key not in FIELDS[doctype]:
			agent.deny()
		op, val = val if isinstance(val, list) and len(val) == 2 else ("=", val)
		if op not in ("=", "!=", "like", "not like", "in", "not in", ">", "<", ">=", "<=", "is"):
			agent.deny()
		if isinstance(val, (dict, list)) and (
			op not in ("in", "not in") or not isinstance(val, list) or len(val) > 100
		):
			agent.deny()
		result.append([key, op, frappe.session.user if val == "@me" else val])
	return result


def list_data(p, native=False):
	dt = p.get("doctype")
	base = scope(dt)
	base += filters_for(dt, p.get("filters")) + filters_for(dt, p.get("default_filters"))
	order = p.get("order_by") or "modified desc"
	if not re.fullmatch(r"[a-z_]+ (asc|desc)", order) or order.split()[0] not in FIELDS[dt]:
		agent.deny()
	limit = max(1, min(cint(p.get("page_length") or p.get("limit_page_length") or 20), 100))
	start = max(0, min(cint(p.get("limit_start") or p.get("start")), 100000))
	data = frappe.get_all(
		dt, fields=list(FIELDS[dt]), filters=base, order_by=order, limit_start=start, limit_page_length=limit
	)
	if not native:
		return data
	keys = {
		"CRM Lead": ("lead_name", "status", "email", "mobile_no", "modified"),
		"Contact": ("full_name", "email_id", "mobile_no", "modified"),
		"CRM Task": ("title", "status", "due_date", "priority"),
	}[dt]
	meta = {f["fieldname"]: f for f in fields(dt)}
	columns = [
		{"key": k, "label": meta[k]["label"], "type": meta[k]["fieldtype"], "width": "12rem"} for k in keys
	]
	return {
		"data": data,
		"columns": columns,
		"rows": list(FIELDS[dt]),
		"fields": fields(dt),
		"page_length": limit,
		"page_length_count": limit,
		"is_default": True,
		"views": [],
		"total_count": frappe.db.count(dt, filters=base),
		"row_count": len(data),
		"form_script": None,
		"list_script": None,
		"view_type": "list",
		"column_field": None,
		"title_field": keys[0],
		"kanban_columns": [],
		"kanban_fields": [],
		"group_by_field": None,
	}


def save(p, mode):
	if mode == "set_value":
		dt, name = p.get("doctype"), p.get("name")
		values = p.get("fieldname")
		values = values if isinstance(values, dict) else {values: p.get("value")}
	else:
		values = frappe.parse_json(p.get("doc"))
		if not isinstance(values, dict):
			agent.deny()
		values = dict(values)
		dt, name = values.pop("doctype", None), values.pop("name", None)
	if dt not in FIELDS or (mode == "insert" and name):
		agent.deny()
	doc = document(dt, name) if name else None
	if doc and not can_edit(doc):
		agent.deny()
	# A native save echoes projected read-only fields; accept only unchanged values.
	for key in list(values):
		if key not in EDITABLE[dt]:
			if key == "__agent_read_only" and doc and values[key] == (not can_edit(doc)):
				values.pop(key)
			elif key == "__newDocument" and not doc:
				values.pop(key)
			elif doc and key in FIELDS[dt] and str(values[key] or "") == str(doc.get(key) or ""):
				values.pop(key)
			else:
				agent.deny()
	if dt == "CRM Lead":
		result = agent.save_lead(values, name)
	elif dt == "Contact":
		if "email_id" in values:
			values["email"] = values.pop("email_id")
		result = agent.save_contact(values, name=name)
	else:
		values = agent.payload(values, EDITABLE[dt])
		if not doc:
			doc = frappe.new_doc(dt)
			doc.owner = frappe.session.user
		doc.update(values)
		doc.reference_doctype = doc.reference_doctype or "CRM Lead"
		doc.status = doc.status or "Todo"
		doc.priority = doc.priority or "Low"
		if doc.reference_doctype != "CRM Lead":
			agent.deny()
		agent.own_lead(doc.reference_docname, frappe.session.user)
		if doc.status not in ("Backlog", "Todo", "In Progress", "Done", "Canceled") or doc.priority not in (
			"Low",
			"Medium",
			"High",
		):
			agent.deny()
		doc.save(ignore_permissions=True)
		result = {"name": doc.name}
	return projected(document(dt, result["name"]))


def self_user():
	u = frappe.db.get_value(
		"User",
		require_agent(),
		["name", "email", "full_name", "first_name", "last_name", "language", "enabled"],
		as_dict=True,
	)
	u.update(
		role="Agent", roles=["Agent"], session_user=True, user_type="Website User", is_telephony_agent=False
	)
	return u


def activities(name):
	doc = document("CRM Lead", name)
	versions = [
		{
			"activity_type": "creation",
			"creation": doc.creation,
			"owner": doc.owner,
			"data": "created this lead",
			"is_lead": True,
		}
	]
	from crm.api.appointments import own_event

	for e in frappe.get_all(
		"Event",
		filters={
			"owner": frappe.session.user,
			"reference_doctype": "CRM Lead",
			"reference_docname": doc.name,
			"event_type": "Private",
		},
		pluck="name",
		limit_page_length=100,
	):
		event = own_event(e)
		versions.append(
			{
				"name": event.name,
				"activity_type": "appointment",
				"creation": event.creation,
				"owner": event.owner,
				"is_lead": True,
				"data": agent.project(event, ("subject", "starts_on", "ends_on", "location", "status"))
				| {"time_zone": frappe.utils.get_system_timezone()},
			}
		)
	tasks = list_data({"doctype": "CRM Task", "filters": {"reference_docname": doc.name}, "page_length": 100})
	for task in tasks:
		task["assigned_to"] = frappe.session.user
	return [versions, [], [], tasks, []]


def dispatch(method, p):
	require_agent()
	if method == "crm.api.session.get_users":
		u = self_user()
		return [[u], [u]]
	if method == "crm.api.session.get_user_info":
		return [self_user()]
	if method == "frappe.client.get":
		if p.get("doctype") == "FCRM Settings":
			return {
				"doctype": "FCRM Settings",
				"name": "FCRM Settings",
				"dropdown_items": [
					{"is_standard": 1, "name1": "logout", "label": "Log out", "icon": "log-out"}
				],
			}
		return projected(document(p.get("doctype"), p.get("name")))
	if method in ("frappe.client.save", "frappe.client.insert", "frappe.client.set_value"):
		return save(p, method.rsplit(".", 1)[1])
	if method == "frappe.client.get_doc_permissions":
		doc = document(p.get("doctype"), p.get("docname"))
		return {
			"permissions": {
				"read": 1,
				"write": int(can_edit(doc)),
				"create": 1,
				"delete": 0,
				"export": 0,
				"share": 0,
			}
		}
	if method == "frappe.desk.form.load.getdoctype":
		dt = p.get("doctype")
		meta = {
			"doctype": "DocType",
			"name": dt,
			"fields": fields(dt),
			"permissions": [],
			"title_field": {"CRM Lead": "lead_name", "Contact": "full_name", "CRM Task": "title"}[dt],
		}
		frappe.response["docs"] = [meta]
		frappe.response["user_settings"] = "{}"
		return
	if method == "frappe.client.get_list":
		dt = p.get("doctype")
		if dt == "CRM Lead Status":
			return frappe.get_all(
				dt,
				filters={"name": ["in", agent.STATUSES]},
				fields=["name", "color", "position", "type"],
				order_by="position asc",
			)
		if dt in ("CRM Form Script", "CRM Deal Status", "CRM Communication Status"):
			return []
		return list_data(p)
	if method == "crm.api.doc.get_data":
		return list_data(p, native=True)
	if method.endswith(".get_fields_layout"):
		return layout(p.get("doctype"))
	if method.endswith(".get_sidepanel_sections"):
		return layout(p.get("doctype"), side=True)
	if method in ("crm.api.doc.get_filterable_fields", "crm.api.doc.sort_options"):
		return [f | {"value": f["fieldname"], "name": f["fieldname"]} for f in fields(p.get("doctype"))]
	if method == "crm.api.doc.get_quick_filters":
		return []
	if method == "crm.api.doc.get_assigned_users":
		document(p.get("doctype"), p.get("name"))
		return []
	if method == "crm.api.activities.get_activities":
		return activities(p.get("name"))
	if method == "frappe.desk.search.search_link":
		dt = p.get("doctype")
		if dt == "CRM Lead Status":
			return [
				{"value": s, "description": ""}
				for s in agent.STATUSES
				if str(p.get("txt") or "").lower() in s.lower()
			]
		if dt == "User":
			return [{"value": frappe.session.user, "description": self_user().full_name}]
		rows = list_data(
			{"doctype": dt, "filters": {"name": ["like", "%" + str(p.get("txt") or "")[:100] + "%"]}}
		)
		return [{"value": r.name, "description": ""} for r in rows]
	if method == "frappe.onboarding.get_onboarding_status":
		return {}
	if method == "frappe.utils.telemetry.pulse.client.boot_config":
		return {"enabled": False}
	if method in EMPTY_LIST:
		return []
	if method in DISABLED:
		return False
	agent.deny()


EMPTY_LIST = {
	"crm.api.views.get_views",
	"crm.api.session.get_organizations",
	"crm.api.notifications.get_notifications",
	"frappe.apps.get_apps",
}
DISABLED = {
	"crm.api.whatsapp.is_whatsapp_enabled",
	"crm.api.whatsapp.is_whatsapp_installed",
	"crm.integrations.api.is_call_integration_enabled",
}
CONTRACTS = (
	{
		"frappe.onboarding.get_onboarding_status",
		"frappe.utils.telemetry.pulse.client.boot_config",
		"crm.api.session.get_users",
		"crm.api.session.get_user_info",
		"frappe.client.get",
		"frappe.client.save",
		"frappe.client.insert",
		"frappe.client.set_value",
		"frappe.client.get_doc_permissions",
		"frappe.client.get_list",
		"frappe.desk.form.load.getdoctype",
		"crm.api.doc.get_data",
		"crm.api.doc.get_filterable_fields",
		"crm.api.doc.sort_options",
		"crm.api.doc.get_quick_filters",
		"crm.api.doc.get_assigned_users",
		"crm.api.activities.get_activities",
		"frappe.desk.search.search_link",
		"crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_fields_layout",
		"crm.fcrm.doctype.crm_fields_layout.crm_fields_layout.get_sidepanel_sections",
	}
	| EMPTY_LIST
	| DISABLED
)


def override_name(method):
	return method.replace(".", "__")


def handler(method):
	@frappe.whitelist()
	def wrapped(**kwargs):
		if is_agent():
			if (
				method in ("frappe.client.save", "frappe.client.insert", "frappe.client.set_value")
				and frappe.request.method != "POST"
			):
				agent.deny()
			return dispatch(method, kwargs)
		# Preserve any earlier installed-app override for staff as well.
		previous = [
			path
			for path in frappe.get_hooks("override_whitelisted_methods", {}).get(method, [])
			if not path.startswith("crm.api.agent_ui.")
		]
		original = frappe.get_attr(previous[-1] if previous else method)
		# Preserve the original handler's authorization and HTTP-method constraints.
		frappe.is_whitelisted(original)
		from frappe.handler import is_valid_http_method

		is_valid_http_method(original)
		return frappe.call(original, **kwargs)

	return wrapped


for _method in CONTRACTS:
	globals()[override_name(_method)] = handler(_method)
