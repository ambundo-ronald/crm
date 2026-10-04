"""Restricted HTTP surface for external agents; staff permissions are unchanged."""

import frappe
from frappe import _

ROLE = "Commission Agent"
METHODS = frozenset(
	{
		"crm.api.agent.list_leads",
		"crm.api.agent.list_appointments",
		"crm.api.agent.save_appointment",
		"crm.api.agent.convert_appointment_to_lead",
		"crm.api.agent.get_lead",
		"crm.api.agent.save_lead",
		"crm.api.agent.list_contacts",
		"crm.api.agent.save_contact",
		"crm.api.agent.add_follow_up",
		"crm.api.agent.complete_follow_up",
		"login",
		"logout",
		"frappe.auth.get_logged_user",
	}
)


def is_agent(user=None):
	user = user or frappe.session.user
	return user not in ("Guest", "Administrator") and ROLE in frappe.get_roles(user)


def require_agent():
	if not is_agent() or not frappe.db.get_value("User", frappe.session.user, "enabled"):
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	return frappe.session.user


def restrict_request():
	# auth_hooks runs after both API-key/OAuth and cookie authentication.
	if not is_agent():
		return
	if not frappe.db.get_value("User", frappe.session.user, "enabled"):
		frappe.throw(_("This agent account is suspended."), frappe.AuthenticationError)
	request = frappe.local.request
	cmd = frappe.form_dict.get("cmd")
	path = request.path.rstrip("/") or "/"
	if cmd:
		if cmd in METHODS:
			return
	elif path.startswith("/api/method/"):
		if path.removeprefix("/api/method/") in METHODS:
			return
	elif path == "/crm-agent" and request.method in ("GET", "HEAD"):
		return
	elif path in ("/", "/app", "/desk", "/crm", "/login") and request.method in ("GET", "HEAD"):
		frappe.local.flags.redirect_location = "/crm-agent"
		redirect = frappe.Redirect()
		redirect.http_status_code = 302
		raise redirect
	frappe.throw(_("This account can only use the agent CRM workspace."), frappe.PermissionError)


def install_role():
	if not frappe.db.exists("Role", ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 0}).insert(
			ignore_permissions=True
		)
