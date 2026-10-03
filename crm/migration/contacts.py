"""Administrator-reviewed links to existing shared Contacts; never copy Contact data."""

import hashlib
import json

import frappe

from crm.migration.sync import RUN, _lock, require_admin
from crm.permissions.commission_agent import is_agent

AUDIT = "CRM ERPNext Contact Link"
MAPPINGS = {
	"Lead": ("CRM ERPNext Sync Link", "CRM Lead"),
	"Customer": ("CRM ERPNext Customer Link", "CRM Organization"),
}


def digest(value):
	return hashlib.sha256(json.dumps(value, sort_keys=True, default=str).encode()).hexdigest()


def require_site():
	require_admin()
	if "erpnext" not in frappe.get_installed_apps():
		frappe.throw("ERPNext must be installed on this site")


def candidate(contact, source_type, source_name, lock=False):
	if source_type not in MAPPINGS:
		frappe.throw("Only existing Lead and Customer contact links are supported")
	doc = frappe.get_doc("Contact", contact, for_update=lock)
	row = {
		"contact": doc.name,
		"contact_label": doc.full_name or doc.name,
		"source_doctype": source_type,
		"source_name": source_name,
		"other_link_count": len(doc.links),
		"other_links": [{"doctype": link.link_doctype, "name": link.link_name} for link in doc.links[:20]],
	}
	if not any(link.link_doctype == source_type and link.link_name == source_name for link in doc.links):
		return row | {"issues": ["source_contact_relationship_missing"]}
	mapping_type, target_type = MAPPINGS[source_type]
	mapping_name = frappe.db.get_value(mapping_type, {"source_name": source_name}, "name")
	if not mapping_name:
		return row | {"issues": ["sync_source_record_first"]}
	mapping = frappe.get_doc(mapping_type, mapping_name)
	if not frappe.db.exists(target_type, mapping.target_name):
		return row | {"issues": ["target_missing"]}
	source = frappe.get_doc(source_type, source_name, for_update=lock)
	if source_type == "Customer":
		from crm.migration.customer import business_customer

		eligible = business_customer(source)
	else:
		eligible = not source.disabled and not source.unsubscribed and source.status != "Do Not Contact"
	if not eligible or source.owner != mapping.source_creator:
		return row | {"issues": ["source_lifecycle_or_creator_requires_review"]}
	target = frappe.get_doc(target_type, mapping.target_name, for_update=lock)
	existing = next(
		(link for link in doc.links if link.link_doctype == target_type and link.link_name == target.name),
		None,
	)
	edge = digest([doc.name, target_type, target.name])
	audit = frappe.db.get_value(
		AUDIT, {"edge_key": edge, "state": "Active"}, ["name", "link_name"], as_dict=True
	)
	row.update(
		{
			"target_doctype": target_type,
			"target_name": target.name,
			"target_owner": target.owner,
			"agent_visibility": target_type == "CRM Lead" and is_agent(target.owner),
			"already_linked": bool(existing),
			"managed_link": audit.name if audit and existing and audit.link_name == existing.name else None,
			"issues": [],
		}
	)
	row["preview_token"] = digest(
		[
			doc.name,
			doc.modified,
			source_type,
			source.name,
			source.modified,
			mapping.name,
			mapping.modified,
			target_type,
			target.name,
			target.modified,
			target.owner,
			row["agent_visibility"],
			[(link.name, link.link_doctype, link.link_name) for link in doc.links],
		]
	)
	return row


@frappe.whitelist(methods=["GET", "POST"])
def preview_contact_links(after: str = ""):
	require_site()
	if len(after) > 140:
		frappe.throw("Invalid contact cursor")
	filters = {"parenttype": "Contact", "parentfield": "links", "link_doctype": ["in", list(MAPPINGS)]}
	if after:
		filters["name"] = [">", after]
	links = frappe.get_all(
		"Dynamic Link",
		filters=filters,
		fields=["name", "parent", "link_doctype", "link_name"],
		order_by="name asc",
		limit_page_length=51,
	)
	rows = []
	for link in links[:50]:
		try:
			row = candidate(link.parent, link.link_doctype, link.link_name)
		except frappe.DoesNotExistError:
			row = {
				"contact": link.parent,
				"source_doctype": link.link_doctype,
				"source_name": link.link_name,
				"issues": ["source_or_contact_missing"],
			}
		rows.append(row | {"key": link.name})
	return {
		"proposals": rows,
		"has_more": len(links) > 50,
		"next_after": links[49].name if len(links) > 50 else "",
	}


@frappe.whitelist(methods=["POST"])
def approve_contact_link(contact: str, source_doctype: str, source_name: str, preview_token: str):
	require_site()
	_lock()
	row = candidate(contact, source_doctype, source_name, lock=True)
	if row["issues"]:
		frappe.throw("Contact link requires review: " + ", ".join(row["issues"]))
	if row["preview_token"] != preview_token:
		frappe.throw("The contact or destination changed. Refresh the review before linking.")
	if row["already_linked"]:
		return {"status": "Already linked"}
	doc = frappe.get_doc("Contact", contact)
	child = doc.append("links", {"link_doctype": row["target_doctype"], "link_name": row["target_name"]})
	# Only add the verified relationship. Saving the entire Contact would run
	# unrelated ERPNext/CRM detail-update hooks against this shared identity.
	child.insert(ignore_permissions=True)
	frappe.db.set_value("Contact", doc.name, "modified_by", frappe.session.user)
	frappe.clear_document_cache("Contact", doc.name)
	edge = digest([doc.name, row["target_doctype"], row["target_name"]])
	audit_name = frappe.db.get_value(AUDIT, {"edge_key": edge}, "name")
	audit = frappe.get_doc(AUDIT, audit_name) if audit_name else frappe.new_doc(AUDIT)
	audit.update(
		{
			"edge_key": edge,
			"contact": doc.name,
			"source_doctype": source_doctype,
			"source_name": source_name,
			"target_doctype": row["target_doctype"],
			"target_name": row["target_name"],
			"link_name": child.name,
			"state": "Active",
			"approved_by": frappe.session.user,
			"approved_owner": row["target_owner"],
			"removed_by": None,
		}
	)
	audit.save(ignore_permissions=True)
	log_link(doc.name, "Linked", row["target_doctype"], row["target_name"])
	return {"status": "Linked", "audit": audit.name}


@frappe.whitelist(methods=["GET", "POST"])
def managed_contact_links(after: str = ""):
	require_site()
	if len(after) > 140:
		frappe.throw("Invalid contact cursor")
	filters = {"state": "Active"}
	if after:
		filters["name"] = [">", after]
	rows = frappe.get_all(
		AUDIT,
		filters=filters,
		fields=[
			"name",
			"contact",
			"source_doctype",
			"source_name",
			"target_doctype",
			"target_name",
			"approved_by",
			"approved_owner",
		],
		order_by="name asc",
		limit_page_length=51,
	)
	return {
		"links": rows[:50],
		"has_more": len(rows) > 50,
		"next_after": rows[49].name if len(rows) > 50 else "",
	}


@frappe.whitelist(methods=["POST"])
def remove_contact_link(name: str):
	require_site()
	_lock()
	audit = frappe.get_doc(AUDIT, name, for_update=True)
	if audit.state != "Active":
		return {"status": "Already removed"}
	frappe.get_doc("Contact", audit.contact, for_update=True)
	if frappe.db.exists("Dynamic Link", audit.link_name):
		link = frappe.get_doc("Dynamic Link", audit.link_name)
		if (link.parent, link.parenttype, link.parentfield, link.link_doctype, link.link_name) != (
			audit.contact,
			"Contact",
			"links",
			audit.target_doctype,
			audit.target_name,
		):
			frappe.throw("The recorded link was changed. Review it in Contact before removal.")
		frappe.db.delete("Dynamic Link", {"name": link.name})
		frappe.db.set_value("Contact", audit.contact, "modified_by", frappe.session.user)
		frappe.clear_document_cache("Contact", audit.contact)
	audit.state = "Removed"
	audit.removed_by = frappe.session.user
	audit.save(ignore_permissions=True)
	log_link(audit.contact, "Unlinked", audit.target_doctype, audit.target_name)
	return {"status": "Unlinked"}


def log_link(contact, action, target_type, target_name):
	frappe.get_doc(
		{
			"doctype": RUN,
			"summary": action + " shared Contact",
			"results": json.dumps(
				[
					{
						"source": contact,
						"source_doctype": "Contact",
						"target": contact,
						"target_doctype": "Contact",
						"status": action,
						"relationship": [target_type, target_name],
					}
				]
			),
		}
	).insert(ignore_permissions=True)
