"""Personal appointments for CRM staff and external agents.

Meetings can precede a lead. Conversion links the original Event and is serialized
on that Event so retries cannot create a second lead.
"""

import frappe
from frappe import _
from frappe.utils import now_datetime

from crm.api import check_app_permission
from crm.api.agent import APPOINTMENT_FIELDS, appointment_time, deny, own_lead, payload, project, record_name
from crm.permissions.commission_agent import is_agent


def require_user():
	if is_agent():
		from crm.permissions.commission_agent import require_agent

		return require_agent()
	if frappe.session.user == "Guest" or not check_app_permission():
		deny()
	return frappe.session.user


def permitted_lead(name):
	name = record_name(name)
	if is_agent():
		return own_lead(name, frappe.session.user)
	doc = frappe.get_doc("CRM Lead", name)
	doc.check_permission("read")
	return doc


def own_event(name, write=False, for_update=False):
	name = record_name(name)
	if not frappe.db.exists("Event", {"name": name, "owner": frappe.session.user, "event_type": "Private"}):
		deny()
	doc = frappe.get_doc("Event", name, for_update=for_update)
	if doc.owner != frappe.session.user or doc.event_type != "Private":
		deny()
	if doc.reference_doctype:
		if doc.reference_doctype != "CRM Lead" or not doc.reference_docname:
			deny()
		permitted_lead(doc.reference_docname)
	elif doc.reference_docname:
		deny()
	if not is_agent():
		doc.check_permission("write" if write else "read")
	if write and (
		doc.event_participants
		or doc.links
		or doc.repeat_this_event
		or doc.sync_with_google_calendar
		or doc.pulled_from_google_calendar
	):
		deny()
	return doc


def rows(user, start, end, lead=None):
	candidates = frappe.db.sql(
		"""select e.name, e.subject, e.starts_on, e.ends_on, e.location, e.status, e.reference_docname
        from tabEvent e
        where e.owner = %(user)s and e.event_type = 'Private'
          and (e.reference_doctype = 'CRM Lead' or
               (coalesce(e.reference_doctype, '') = '' and coalesce(e.reference_docname, '') = ''))
          and e.starts_on < %(end)s and e.ends_on > %(start)s
          and (%(lead)s is null or e.reference_docname = %(lead)s)
        order by e.starts_on, e.name limit 501""",
		{"user": user, "start": start, "end": end, "lead": lead},
		as_dict=True,
	)
	visible = []
	for row in candidates:
		try:
			own_event(row.name)
		except (frappe.PermissionError, frappe.DoesNotExistError):
			continue
		visible.append(row)
	return visible, len(candidates) > 500


@frappe.whitelist(methods=["GET", "POST"])
def list_appointments(start, end, lead=None):
	user = require_user()
	start, end = appointment_time(start), appointment_time(end)
	if end <= start or (end - start).total_seconds() > 32 * 86400:
		frappe.throw(_("Choose a calendar range of up to 32 days"), frappe.ValidationError)
	if lead:
		lead = permitted_lead(lead).name
	appointments, truncated = rows(user, start, end, lead)
	return {
		"appointments": appointments[:500],
		"truncated": truncated,
		"time_zone": frappe.utils.get_system_timezone(),
	}


@frappe.whitelist(methods=["POST"])
def save_appointment(data, lead=None, name=None):
	user = require_user()
	lead = permitted_lead(lead).name if lead else None
	values = payload(data, ("subject", "starts_on", "ends_on", "location", "status"))
	if name:
		doc = own_event(name, write=True)
		if (doc.reference_docname or None) != lead:
			deny()  # Re-linking is reserved for the conversion operation.
	else:
		doc = frappe.get_doc(
			{
				"doctype": "Event",
				"owner": user,
				"event_type": "Private",
				"event_category": "Meeting",
				"reference_doctype": "CRM Lead" if lead else None,
				"reference_docname": lead,
				"status": "Open",
				"send_reminder": 0,
				"sync_with_google_calendar": 0,
			}
		)
		if not is_agent():
			doc.check_permission("create")
	doc.update(values)
	if not isinstance(doc.subject, str) or not doc.subject.strip() or len(doc.subject) > 140:
		frappe.throw(_("Enter an appointment title of up to 140 characters"), frappe.ValidationError)
	if doc.status not in ("Open", "Completed", "Cancelled"):
		frappe.throw(_("Choose an available appointment status"), frappe.ValidationError)
	start = appointment_time(str(doc.starts_on or ""))
	end = appointment_time(str(doc.ends_on or ""))
	if end <= start or (end - start).total_seconds() > 7 * 86400:
		frappe.throw(_("End must follow start, within seven days"), frappe.ValidationError)
	if (not name or "starts_on" in values) and doc.status == "Open" and start < now_datetime():
		frappe.throw(_("Choose a future appointment time"), frappe.ValidationError)
	doc.starts_on, doc.ends_on = start, end
	candidates, _truncated = rows(user, start, end)
	conflict = any(row.name != name and row.status == "Open" for row in candidates)
	doc.save(ignore_permissions=is_agent())
	return {"appointment": project(doc, APPOINTMENT_FIELDS), "conflict": conflict and doc.status == "Open"}


@frappe.whitelist(methods=["POST"])
def convert_to_lead(name, data):
	require_user()
	doc = own_event(name, write=True)
	# Lock only after access verification. Re-read after waiting for a concurrent conversion.
	doc = own_event(name, write=True, for_update=True)
	if doc.reference_docname:
		return {"lead": doc.reference_docname, "created": False}
	if doc.status != "Completed":
		frappe.throw(_("Mark the meeting completed before creating a lead"), frappe.ValidationError)
	values = payload(data, ("first_name", "last_name", "email", "mobile_no", "organization"))
	if not (values.get("first_name") or "").strip():
		frappe.throw(_("Enter the person's name to create a lead"), frappe.ValidationError)
	lead = frappe.get_doc({"doctype": "CRM Lead", **values, "owner": frappe.session.user, "status": "New"})
	if not is_agent():
		lead.lead_owner = frappe.session.user
	lead.insert(ignore_permissions=is_agent())
	if not is_agent():
		lead.check_permission("read")
	doc.reference_doctype = "CRM Lead"
	doc.reference_docname = lead.name
	doc.save(ignore_permissions=is_agent())
	return {"lead": lead.name, "created": True}
