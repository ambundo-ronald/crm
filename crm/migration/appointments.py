"""Opt-in same-site Appointment calendar links; ERPNext remains authoritative."""

from datetime import timedelta

import frappe
from frappe.utils import cint, get_datetime

from crm.migration.sync import require_admin
from crm.permissions.commission_agent import is_agent

LINK = "CRM ERPNext Appointment Link"


def available():
	return "erpnext" in frappe.get_installed_apps() and frappe.db.exists("DocType", LINK)


def projection(source):
	"""Fail closed for ambiguous links, invalid times and unidentified creators."""
	if source.status not in ("Open", "Closed", "Unverified"):
		frappe.throw("Unsupported appointment status")
	if source.owner in ("Guest", None, "") or not frappe.db.get_value("User", source.owner, "enabled"):
		frappe.throw("Appointment creator needs review")
	lead = None
	if source.appointment_with or source.party:
		if source.appointment_with != "Lead" or not source.party:
			frappe.throw("Only appointments for mapped Leads or without a party are supported")
		lead = frappe.db.get_value("CRM ERPNext Sync Link", {"source_name": source.party}, "target_name")
		if not lead or not frappe.db.exists("Lead", source.party) or not frappe.db.exists("CRM Lead", lead):
			frappe.throw("Sync the ERPNext Lead before linking this appointment")
		if is_agent(source.owner) and frappe.db.get_value("CRM Lead", lead, "owner") != source.owner:
			frappe.throw("Appointment creator does not own the mapped lead")
	if not source.scheduled_time:
		frappe.throw("Appointment time needs review")
	try:
		start = get_datetime(source.scheduled_time)
	except (TypeError, ValueError):
		frappe.throw("Appointment time needs review")
	duration = cint(frappe.db.get_single_value("Appointment Booking Settings", "appointment_duration"))
	if duration <= 0 or duration > 7 * 24 * 60:
		frappe.throw("Set a valid appointment duration in ERPNext Appointment Booking Settings")
	return {
		"name": "erpnext-appointment:" + source.name,
		"subject": "Appointment with " + (source.customer_name or source.name),
		"starts_on": str(start),
		"ends_on": str(start + timedelta(minutes=duration)),
		"status": source.status,
		"reference_docname": lead,
		"location": "",
		"read_only": True,
		"source": "ERPNext Appointment",
	}


@frappe.whitelist(methods=["GET", "POST"])
def preview(after: str = ""):
	require_admin()
	if not available():
		frappe.throw("ERPNext and the appointment link schema are required. Run migrate.")
	names = frappe.get_all(
		"Appointment", filters={"name": [">", after]}, order_by="name", pluck="name", limit=51
	)
	result = []
	for name in names[:50]:
		source = frappe.get_doc("Appointment", name)
		row = {
			"name": name,
			"status": "Ready",
			"issue": "",
			"linked": bool(frappe.db.exists(LINK, {"appointment": name})),
		}
		try:
			row["appointment"] = projection(source)
		except frappe.ValidationError as exc:
			row.update(status="Review", issue=str(exc))
		result.append(row)
	return {"rows": result, "has_more": len(names) > 50, "next_after": names[49] if len(names) > 50 else ""}


@frappe.whitelist(methods=["POST"])
def sync(names):
	require_admin()
	if not available():
		frappe.throw("ERPNext appointment sync is unavailable")
	names = frappe.parse_json(names) if isinstance(names, str) else names
	if (
		not isinstance(names, list)
		or not names
		or len(names) > 50
		or any(not isinstance(n, str) for n in names)
	):
		frappe.throw("Select up to 50 appointments")
	for name in sorted(set(names)):
		source = frappe.get_doc("Appointment", name, for_update=True)
		projection(source)  # Revalidate after preview; the request rolls back on a conflict.
		if not frappe.db.exists(LINK, {"appointment": name}):
			frappe.get_doc({"doctype": LINK, "appointment": name}).insert(ignore_permissions=True)
	return {"linked": len(set(names))}


def linked_event(name):
	if not available():
		return False
	return bool(
		frappe.db.sql(
			"""select l.name from `tabCRM ERPNext Appointment Link` l
		inner join tabAppointment a on a.name=l.appointment
		where a.calendar_event=%s limit 1""",
			name,
		)
	)


@frappe.whitelist(methods=["POST"])
def unlink(name: str):
	require_admin()
	link = frappe.db.get_value(LINK, {"appointment": name})
	if link:
		frappe.delete_doc(LINK, link, ignore_permissions=True)
	return {"unlinked": bool(link)}


def calendar_rows(user, start, end, lead=None):
	if not available():
		return [], False, set()
	# Seven days is the maximum supported duration, including overlaps from earlier dates.
	names = frappe.db.sql(
		"""select a.name from tabAppointment a inner join `tabCRM ERPNext Appointment Link` l
		on l.appointment=a.name where a.owner=%s and a.scheduled_time<%s
		and a.scheduled_time>%s order by a.scheduled_time, a.name limit 501""",
		(user, end, start - timedelta(days=7)),
		pluck=True,
	)
	result, events = [], set()
	for name in names[:500]:
		source = frappe.get_doc("Appointment", name)
		try:
			if source.owner != user:
				continue
			if not is_agent():
				source.check_permission("read")
			row = projection(source)
			if row["reference_docname"]:
				from crm.api.appointments import permitted_lead

				permitted_lead(row["reference_docname"])
			if get_datetime(row["ends_on"]) <= start or (lead and row["reference_docname"] != lead):
				continue
		except (frappe.ValidationError, frappe.PermissionError, frappe.DoesNotExistError):
			continue
		result.append(row)
		if source.calendar_event:
			events.add(source.calendar_event)
	return result, len(names) > 500, events
