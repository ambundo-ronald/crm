"""Allowlisted agent operations. Never return arbitrary documents or linked history."""

import frappe
from frappe import _
from frappe.utils import cint, get_datetime, now_datetime

from crm.permissions.commission_agent import require_agent

LEAD_FIELDS = (
	"name",
	"first_name",
	"last_name",
	"email",
	"mobile_no",
	"phone",
	"organization",
	"job_title",
	"status",
	"modified",
	"converted",
)
EDIT_FIELDS = frozenset(LEAD_FIELDS) - {"name", "modified", "converted"}
CONTACT_FIELDS = ("name", "first_name", "last_name", "email_id", "mobile_no", "phone")
STATUSES = ("New", "Contacted", "Nurture", "Qualified")


def deny():
	frappe.throw(_("Not permitted"), frappe.PermissionError)


def payload(data, allowed):
	data = frappe.parse_json(data) if isinstance(data, str) else data
	if not isinstance(data, dict) or set(data) - set(allowed):
		frappe.throw(_("Unsupported fields"), frappe.ValidationError)
	if any(not isinstance(value, (str, type(None))) for value in data.values()):
		frappe.throw(_("Expected text values"), frappe.ValidationError)
	if any(len(value or "") > 500 for value in data.values()):
		frappe.throw(_("Field value is too long"), frappe.ValidationError)
	return data


def record_name(value):
	if isinstance(value, bool) or not isinstance(value, (str, int)) or not 0 < len(str(value)) <= 140:
		deny()
	return str(value)


def own_lead(name, user):
	name = record_name(name)
	# Check the stored creator, not caller-supplied owner or mutable lead_owner.
	if not frappe.db.exists("CRM Lead", {"name": name, "owner": user}):
		deny()
	return frappe.get_doc("CRM Lead", name)


def project(doc, fields):
	return {field: doc.get(field) for field in fields}


@frappe.whitelist(methods=["GET"])
def list_leads(query="", start=0):
	user = require_agent()
	filters = {"owner": user}
	if query:
		filters["lead_name"] = ["like", "%" + str(query)[:100] + "%"]
	return frappe.get_all(
		"CRM Lead",
		filters=filters,
		fields=list(LEAD_FIELDS),
		order_by="modified desc",
		limit_start=max(0, cint(start)),
		limit_page_length=25,
	)


def contacts(user, lead=None, start=0):
	# Dynamic Link is the explicit Contact -> CRM Lead relationship.
	# Do not expand through deals/customers or return a contact's other links.
	lead_clause = "and l.name = %(lead)s" if lead else ""
	owner_clause = "" if lead else "c.owner = %(user)s or"
	return frappe.db.sql(
		f"""select c.name, c.first_name, c.last_name, c.email_id, c.mobile_no, c.phone
            from tabContact c
            where {owner_clause} exists (
                select 1 from `tabDynamic Link` dl
                inner join `tabCRM Lead` l on l.name = dl.link_name
                where dl.parent = c.name and dl.parenttype = 'Contact'
                  and dl.parentfield = 'links' and dl.link_doctype = 'CRM Lead'
                  and l.owner = %(user)s {lead_clause}
            )
            order by c.modified desc limit 25 offset %(start)s""",
		{"user": user, "lead": lead, "start": max(0, cint(start))},
		as_dict=True,
	)


@frappe.whitelist(methods=["GET"])
def list_contacts(start=0):
	return contacts(require_agent(), start=start)


@frappe.whitelist(methods=["GET"])
def get_lead(name):
	user = require_agent()
	doc = own_lead(name, user)
	return {
		"lead": project(doc, LEAD_FIELDS),
		"contacts": contacts(user, lead=name),
		"follow_ups": frappe.get_all(
			"CRM Task",
			filters={
				"owner": user,
				"reference_doctype": "CRM Lead",
				"reference_docname": name,
			},
			fields=["name", "title", "due_date", "status"],
			order_by="creation desc",
			limit_page_length=50,
		),
		"statuses": list(STATUSES),
	}


@frappe.whitelist(methods=["POST"])
def save_lead(data, name=None):
	user = require_agent()
	values = payload(data, EDIT_FIELDS)
	if "status" in values and values["status"] not in STATUSES:
		frappe.throw(_("Choose an available lead status"), frappe.ValidationError)
	if name:
		doc = own_lead(name, user)
		if doc.converted:
			frappe.throw(_("Converted leads are read-only"), frappe.PermissionError)
	else:
		doc = frappe.new_doc("CRM Lead")
		doc.owner = user
		doc.status = "New"
	doc.update(values)
	# Dedicated endpoint provides the authorization above. No broad DocPerm is granted.
	doc.save(ignore_permissions=True)
	return project(doc, LEAD_FIELDS)


@frappe.whitelist(methods=["POST"])
def save_contact(data, lead=None, name=None):
	user = require_agent()
	values = payload(data, ("first_name", "last_name", "email", "mobile_no"))
	if lead:
		own_lead(lead, user)
	if name:
		name = record_name(name)
		if not frappe.db.exists("Contact", {"name": name, "owner": user}):
			deny()
		doc = frappe.get_doc("Contact", name)
		# Editing shared contact details can affect ERPNext records; keep them read-only.
		if any(
			row.link_doctype != "CRM Lead"
			or not frappe.db.exists("CRM Lead", {"name": row.link_name, "owner": user})
			for row in doc.links
		) or frappe.db.exists("CRM Contacts", {"contact": name}):
			deny()
	else:
		doc = frappe.new_doc("Contact")
		doc.owner = user
	for field in ("first_name", "last_name"):
		if field in values:
			doc.set(field, values[field])
	if "email" in values:
		doc.set("email_ids", [])
		if values["email"]:
			doc.append("email_ids", {"email_id": values["email"], "is_primary": 1})
	if "mobile_no" in values:
		doc.set("phone_nos", [])
		if values["mobile_no"]:
			doc.append("phone_nos", {"phone": values["mobile_no"], "is_primary_mobile_no": 1})
	if lead and not any(row.link_doctype == "CRM Lead" and row.link_name == lead for row in doc.links):
		doc.append("links", {"link_doctype": "CRM Lead", "link_name": lead})
	doc.save(ignore_permissions=True)
	return project(doc, CONTACT_FIELDS)


@frappe.whitelist(methods=["POST"])
def add_follow_up(lead, title, due_date=None):
	user = require_agent()
	own_lead(lead, user)
	if not isinstance(title, str) or not title.strip() or len(title) > 140:
		frappe.throw(_("Enter a follow-up title of up to 140 characters"), frappe.ValidationError)
	due = get_datetime(due_date) if due_date else None
	if due and due < now_datetime():
		frappe.throw(_("Choose a future follow-up date"), frappe.ValidationError)
	task = frappe.get_doc(
		{
			"doctype": "CRM Task",
			"owner": user,
			"title": title.strip(),
			"status": "Todo",
			"reference_doctype": "CRM Lead",
			"reference_docname": lead,
			"due_date": due,
		}
	)
	task.insert(ignore_permissions=True)
	return {"name": task.name, "title": task.title, "due_date": task.due_date, "status": task.status}


@frappe.whitelist(methods=["POST"])
def complete_follow_up(name):
	name = record_name(name)
	user = require_agent()
	if not frappe.db.exists("CRM Task", {"name": name, "owner": user, "reference_doctype": "CRM Lead"}):
		deny()
	task = frappe.get_doc("CRM Task", name)
	own_lead(task.reference_docname, user)
	task.status = "Done"
	task.save(ignore_permissions=True)
	return {"name": task.name, "status": task.status}


APPOINTMENT_FIELDS = ("name", "subject", "starts_on", "ends_on", "location", "status", "reference_docname")


def appointment_time(value):
	# Browser inputs are wall-clock times in the explicitly displayed site timezone.
	from datetime import datetime
	from zoneinfo import ZoneInfo

	if not isinstance(value, str):
		frappe.throw(_("Enter a date and time"), frappe.ValidationError)
	try:
		parsed = datetime.fromisoformat(value)
		if parsed.tzinfo is not None:
			raise ValueError
		zone = ZoneInfo(frappe.utils.get_system_timezone())
		from datetime import UTC

		roundtrips = {
			parsed.replace(tzinfo=zone, fold=fold).astimezone(UTC).astimezone(zone).replace(tzinfo=None)
			for fold in (0, 1)
		}
		offsets = {parsed.replace(tzinfo=zone, fold=fold).utcoffset() for fold in (0, 1)}
		if parsed not in roundtrips or len(offsets) != 1:
			raise ValueError
		return parsed
	except (ValueError, TypeError):
		frappe.throw(
			_("Enter an unambiguous local date and time in the site timezone"), frappe.ValidationError
		)


@frappe.whitelist(methods=["GET"])
def list_appointments(start, end, lead=None):
	require_agent()
	from crm.api.appointments import list_appointments as list_calendar

	return list_calendar(start, end, lead)


@frappe.whitelist(methods=["POST"])
def save_appointment(lead=None, data=None, name=None):
	require_agent()
	from crm.api.appointments import save_appointment as save_calendar

	return save_calendar(data, lead, name)


@frappe.whitelist(methods=["POST"])
def convert_appointment_to_lead(name, data):
	require_agent()
	from crm.api.appointments import convert_to_lead

	return convert_to_lead(name, data)


@frappe.whitelist(methods=["GET", "POST"])
def my_day():
	require_agent()
	from crm.api.productivity import my_day as daily_work

	return daily_work()


@frappe.whitelist(methods=["POST"])
def complete_daily_task(name: str, modified: str):
	require_agent()
	from crm.api.productivity import complete_task

	return complete_task(name, modified)
