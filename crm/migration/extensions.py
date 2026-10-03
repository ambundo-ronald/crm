"""Explicit custom-field review and read-only source history on the same site."""

import json
from urllib.parse import quote

import frappe
from frappe.utils import strip_html

from crm.migration.contacts import digest
from crm.migration.sync import RUN, _lock, require_admin

SOURCES = {
	"Lead": ("CRM ERPNext Sync Link", "CRM Lead"),
	"Opportunity": ("CRM ERPNext Opportunity Link", "CRM Deal"),
	"Customer": ("CRM ERPNext Customer Link", "CRM Organization"),
	"Prospect": ("CRM ERPNext Prospect Link", "CRM Organization"),
}
SAFE_TYPES = {
	"Data",
	"Small Text",
	"Text",
	"Long Text",
	"Check",
	"Int",
	"Float",
	"Date",
	"Datetime",
	"Select",
}


def mapped(source_doctype, source_name, lock=False):
	require_admin()
	if source_doctype not in SOURCES:
		frappe.throw("Unsupported source type")
	link_type, target_type = SOURCES[source_doctype]
	name = frappe.db.get_value(link_type, {"source_name": source_name}, "name")
	if not name:
		frappe.throw("Sync this source record before reviewing extensions")
	link = frappe.get_doc(link_type, name, for_update=lock)
	source = frappe.get_doc(source_doctype, source_name, for_update=lock)
	target = frappe.get_doc(target_type, link.target_name, for_update=lock)
	source.check_permission("read")
	target.check_permission("read")
	return source, target, link


def safe_field(field):
	return (
		field
		and field.fieldtype in SAFE_TYPES
		and not (
			field.hidden
			or field.permlevel
			or field.read_only
			or field.fetch_from
			or field.is_virtual
			or field.unique
		)
	)


@frappe.whitelist(methods=["GET", "POST"])
def field_inventory(source_doctype: str):
	require_admin()
	if source_doctype not in SOURCES:
		frappe.throw("Unsupported source type")
	target_type = SOURCES[source_doctype][1]
	result = {"source": [], "target": [], "target_doctype": target_type}
	for side, doctype in (("source", source_doctype), ("target", target_type)):
		meta = frappe.get_meta(doctype)
		for name in frappe.get_all("Custom Field", filters={"dt": doctype}, pluck="fieldname"):
			field = meta.get_field(name)
			if field:
				result[side].append(
					{
						"fieldname": name,
						"label": field.label,
						"fieldtype": field.fieldtype,
						"supported": bool(safe_field(field)),
					}
				)
	return result


def value(doc, field):
	item = doc.get(field)
	if item is None:
		return ""
	return json.loads(json.dumps(item, default=str))


def custom_proposal(source_doctype, source_name, fields, lock=False):
	source, target, link = mapped(source_doctype, source_name, lock)
	fields = frappe.parse_json(fields) if isinstance(fields, str) else fields
	if (
		not isinstance(fields, dict)
		or not fields
		or len(fields) > 30
		or any(not isinstance(k, str) or not isinstance(v, str) for k, v in fields.items())
	):
		frappe.throw(
			"Provide a JSON object mapping up to 30 source custom fields to destination custom fields"
		)
	if len(set(fields.values())) != len(fields):
		frappe.throw("Each destination field can have only one source")
	state = json.loads(link.custom_snapshot or "{}")
	rows, changes, next_state, issues = [], {}, dict(state), []
	for origin, destination in fields.items():
		a, b = source.meta.get_field(origin), target.meta.get_field(destination)
		if not (
			frappe.db.exists("Custom Field", {"dt": source.doctype, "fieldname": origin})
			and frappe.db.exists("Custom Field", {"dt": target.doctype, "fieldname": destination})
			and safe_field(a)
			and safe_field(b)
			and a.fieldtype == b.fieldtype
		):
			frappe.throw("Only compatible, visible, writable scalar Custom Fields can be mapped")
		incoming, current = value(source, origin), value(target, destination)
		previous = state.get(destination)
		issue = None
		if b.fieldtype == "Select" and incoming and incoming not in (b.options or "").split("\n"):
			issue = "select_option_requires_review"
		elif previous and previous["source_field"] != origin:
			issue = "source_field_mapping_changed"
		elif not previous and current not in ("", None) and current != incoming:
			issue = "existing_custom_value_requires_review"
		elif (
			previous
			and incoming != previous["source"]
			and current != previous["target"]
			and current != incoming
		):
			issue = "custom_field_conflict"
		elif not previous or incoming != previous["source"]:
			if current != incoming:
				changes[destination] = incoming
			next_state[destination] = {"source_field": origin, "source": incoming, "target": incoming}
		if issue:
			issues.append(destination + ":" + issue)
		rows.append(
			{
				"source_field": origin,
				"target_field": destination,
				"source_value": incoming,
				"target_value": current,
				"issue": issue,
				"will_update": destination in changes,
			}
		)
	if source.owner != link.source_creator:
		issues.append("source_creator_changed")
	if target.doctype == "CRM Deal":
		outbound = frappe.get_single("ERPNext CRM Settings")
		if (
			outbound.enabled
			and outbound.create_customer_on_status_change
			and outbound.deal_status == target.status
		):
			issues.append("outbound_customer_automation_requires_review")
	token = digest(
		[
			source.doctype,
			source.name,
			source.modified,
			target.doctype,
			target.name,
			target.modified,
			link.modified,
			fields,
			rows,
			state,
		]
	)
	return (
		{
			"rows": rows,
			"issues": issues,
			"preview_token": token,
			"target_doctype": target.doctype,
			"target_name": target.name,
		},
		target,
		link,
		changes,
		next_state,
	)


@frappe.whitelist(methods=["POST"])
def preview_custom_fields(source_doctype: str, source_name: str, fields):
	return custom_proposal(source_doctype, source_name, fields)[0]


@frappe.whitelist(methods=["POST"])
def apply_custom_fields(source_doctype: str, source_name: str, fields, preview_token: str):
	require_admin()
	_lock()
	proposal, target, link, changes, state = custom_proposal(source_doctype, source_name, fields, lock=True)
	if proposal["issues"] or proposal["preview_token"] != preview_token:
		frappe.throw("The custom-field proposal changed or requires review. Refresh before applying.")
	target.check_permission("write")
	if changes:
		target.update(changes)
		target.save()
		for field in changes:
			state[field]["target"] = value(target, field)
	link.custom_snapshot = json.dumps(state)
	link.save(ignore_permissions=True)
	frappe.get_doc(
		{
			"doctype": RUN,
			"summary": "Reviewed custom fields",
			"results": json.dumps(
				[
					{
						"source": source_name,
						"source_doctype": source_doctype,
						"target": target.name,
						"target_doctype": target.doctype,
						"status": "Updated" if changes else "Unchanged",
						"fields": list(fields)
						if isinstance(fields, dict)
						else list(frappe.parse_json(fields)),
					}
				]
			),
		}
	).insert(ignore_permissions=True)
	return {"status": "Updated" if changes else "Unchanged"}


@frappe.whitelist(methods=["GET", "POST"])
def source_history(source_doctype: str, source_name: str, kind: str = "Comment", after: str = ""):
	source, _target, _link = mapped(source_doctype, source_name)
	if len(after) > 140:
		frappe.throw("Invalid history cursor")
	if kind not in ("Comment", "Communication", "File", "ToDo", "Event", "CRM Note"):
		frappe.throw("Unsupported history type")
	if kind == "CRM Note":
		filters = {"parenttype": source.doctype, "parent": source.name}
	elif kind == "File":
		filters = {"attached_to_doctype": source.doctype, "attached_to_name": source.name}
	elif kind == "ToDo":
		filters = {"reference_type": source.doctype, "reference_name": source.name}
	elif kind == "Event":
		# Subquery avoids loading an unbounded participant inventory into memory.
		event, participant = frappe.qb.DocType("Event"), frappe.qb.DocType("Event Participants")
		query = (
			frappe.qb.from_(event)
			.select(event.name)
			.where(
				event.name.isin(
					frappe.qb.from_(participant)
					.select(participant.parent)
					.where(
						(participant.parenttype == "Event")
						& (participant.reference_doctype == source.doctype)
						& (participant.reference_docname == source.name)
					)
				)
			)
		)
		if after:
			query = query.where(event.name > after)
		rows = query.orderby(event.name).limit(51).run(as_dict=True)
		filters = None
	else:
		filters = {"reference_doctype": source.doctype, "reference_name": source.name}
		if kind == "Comment":
			filters["comment_type"] = "Comment"
	if filters is not None:
		if after:
			filters["name"] = [">", after]
		rows = frappe.get_all(
			kind, filters=filters, fields=["name"], order_by="name asc", limit_page_length=51
		)
	result = []
	for row in rows[:50]:
		doc = frappe.get_doc(kind, row.name)
		if kind != "CRM Note" and not doc.has_permission("read"):
			continue
		content = doc.get("note") or doc.get("content") or doc.get("description") or ""
		result.append(
			{
				"name": doc.name,
				"kind": kind,
				"owner": doc.get("added_by") or doc.owner,
				"creation": doc.get("added_on") or doc.creation,
				"subject": doc.get("subject") or doc.get("file_name") or kind,
				"content": strip_html(content)[:20000],
				"content_truncated": len(strip_html(content)) > 20000,
				"source_url": "/app/"
				+ (
					source.doctype.lower().replace(" ", "-")
					if kind == "CRM Note"
					else kind.lower().replace(" ", "-")
				)
				+ "/"
				+ quote(source.name if kind == "CRM Note" else doc.name, safe=""),
			}
		)
	return {
		"rows": result,
		"has_more": len(rows) > 50,
		"next_after": str(rows[49].name) if len(rows) > 50 else "",
		"read_only": True,
	}
