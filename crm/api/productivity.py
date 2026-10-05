"""Personal daily work, with document permissions checked before projection."""

from datetime import datetime, time, timedelta

import frappe
from frappe.utils import get_system_timezone, now_datetime

from crm.api import check_app_permission
from crm.api.agent import deny, own_lead, record_name
from crm.api.appointments import rows as appointment_rows
from crm.permissions.commission_agent import is_agent, require_agent

OPEN = ("Backlog", "Todo", "In Progress")
LIMIT = 100


def require_user():
	if is_agent():
		return require_agent()
	if (
		frappe.session.user == "Guest"
		or not check_app_permission()
		or not frappe.db.get_value("User", frappe.session.user, "enabled")
	):
		deny()
	return frappe.session.user


def permitted_task(name, write=False):
	doc = frappe.get_doc("CRM Task", record_name(str(name)), for_update=write)
	user = frappe.session.user
	if is_agent():
		if doc.owner != user or doc.reference_doctype != "CRM Lead":
			deny()
		own_lead(doc.reference_docname, user)
	else:
		if doc.assigned_to != user and not (doc.owner == user and not doc.assigned_to):
			deny()
		doc.check_permission("write" if write else "read")
		if doc.reference_doctype:
			if doc.reference_doctype not in ("CRM Lead", "CRM Deal") or not doc.reference_docname:
				deny()
			frappe.get_doc(doc.reference_doctype, doc.reference_docname).check_permission("read")
		elif doc.reference_docname:
			deny()
	return doc


def task_group(user, condition):
	task = frappe.qb.DocType("CRM Task")
	scope = (
		task.owner == user
		if is_agent()
		else (
			(task.assigned_to == user)
			| ((task.owner == user) & (task.assigned_to.isnull() | (task.assigned_to == "")))
		)
	)
	if is_agent():
		scope &= task.reference_doctype == "CRM Lead"
	candidates = (
		frappe.qb.from_(task)
		.select(task.name)
		.where(scope & task.status.isin(OPEN) & condition)
		.orderby(task.due_date)
		.orderby(task.name)
		.limit(LIMIT + 1)
		.run(as_dict=True)
	)
	result = []
	for row in candidates[:LIMIT]:
		try:
			doc = permitted_task(row.name)
		except (frappe.PermissionError, frappe.DoesNotExistError):
			continue
		result.append(
			{
				key: doc.get(key)
				for key in (
					"name",
					"title",
					"status",
					"due_date",
					"priority",
					"reference_doctype",
					"reference_docname",
				)
			}
			| {"modified": str(doc.modified), "can_complete": is_agent() or doc.has_permission("write")}
		)
	return {"items": result, "truncated": len(candidates) > LIMIT}


def new_leads(user):
	filters = {"owner" if is_agent() else "lead_owner": user, "status": "New", "converted": 0}
	candidates = frappe.get_all(
		"CRM Lead", filters=filters, fields=["name"], order_by="creation asc, name asc", limit=LIMIT + 1
	)
	result = []
	for row in candidates[:LIMIT]:
		try:
			if is_agent():
				doc = own_lead(row.name, user)
			else:
				doc = frappe.get_doc("CRM Lead", row.name)
				doc.check_permission("read")
		except (frappe.PermissionError, frappe.DoesNotExistError):
			continue
		result.append({key: doc.get(key) for key in ("name", "first_name", "last_name", "creation")})
	return {"items": result, "truncated": len(candidates) > LIMIT}


@frappe.whitelist(methods=["GET", "POST"])
def my_day():
	user = require_user()
	now = now_datetime()
	start = datetime.combine(now.date(), time.min)
	end = start + timedelta(days=1)
	horizon = end + timedelta(days=7)
	task = frappe.qb.DocType("CRM Task")
	tasks = {
		"overdue": task_group(user, task.due_date < start),
		"today": task_group(user, (task.due_date >= start) & (task.due_date < end)),
		"upcoming": task_group(user, (task.due_date >= end) & (task.due_date < horizon)),
		"undated": task_group(user, task.due_date.isnull()),
	}
	events, truncated = appointment_rows(user, start, end)
	return {
		"date": str(now.date()),
		"time_zone": get_system_timezone(),
		"tasks": tasks,
		"appointments": {
			"items": [row for row in events[:500] if row.status == "Open"],
			"truncated": truncated,
		},
		"new_leads": new_leads(user),
	}


@frappe.whitelist(methods=["POST"])
def complete_task(name: str, modified: str):
	require_user()
	doc = permitted_task(name, write=True)
	if str(doc.modified) != modified:
		frappe.throw("This task changed. Refresh My Day before completing it.")
	if doc.status == "Done":
		return {"name": doc.name, "status": doc.status}
	if doc.status not in OPEN:
		frappe.throw("Only open tasks can be completed")
	doc.status = "Done"
	doc.save(ignore_permissions=is_agent())
	return {"name": doc.name, "status": doc.status}
