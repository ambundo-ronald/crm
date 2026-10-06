"""Restricted HTTP surface for external agents; staff permissions are unchanged."""

import frappe
from frappe import _

ROLE = "Agent"
LEGACY_ROLE = "Commission Agent"
METHODS = frozenset(
	{
		"crm.api.agent.list_leads",
		"crm.api.agent.my_day",
		"crm.api.agent.complete_daily_task",
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
	return user not in ("Guest", "Administrator") and bool(
		{ROLE, LEGACY_ROLE}.intersection(frappe.get_roles(user))
	)


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
	from crm.api.agent_ui import CONTRACTS, override_name

	allowed = (
		METHODS
		| CONTRACTS
		| {
			"crm.api.appointments.list_appointments",
			"crm.api.appointments.save_appointment",
			"crm.api.appointments.convert_to_lead",
			"crm.api.productivity.my_day",
			"crm.api.productivity.complete_task",
		}
	)
	cmd = frappe.form_dict.get("cmd")
	path = request.path.rstrip("/") or "/"
	method = cmd or (path.removeprefix("/api/method/") if path.startswith("/api/method/") else None)
	if method in CONTRACTS and frappe.override_whitelisted_method(
		method
	) != "crm.api.agent_ui." + override_name(method):
		# Another installed app must not silently replace the restricted contract.
		frappe.throw(_("Agent access requires the restricted CRM handler."), frappe.PermissionError)
	if cmd and path.startswith("/api/method/") and path.removeprefix("/api/method/") != cmd:
		frappe.throw(_("Not permitted"), frappe.PermissionError)
	if cmd:
		if cmd in allowed:
			return
	elif path.startswith("/api/method/"):
		if path.removeprefix("/api/method/") in allowed:
			return
	elif (path == "/crm" or path.startswith("/crm/")) and request.method in ("GET", "HEAD"):
		return
	elif path in ("/crm-agent", "/login") and request.method in ("GET", "HEAD"):
		# Website controllers handle redirects; raising Redirect from auth_hooks
		# bypasses Frappe's website redirect handling and produces an error page.
		return
	frappe.throw(_("This account can only access its own CRM records."), frappe.PermissionError)


def install_role():
	if not frappe.db.exists("Role", ROLE):
		frappe.get_doc({"doctype": "Role", "role_name": ROLE, "desk_access": 0}).insert(
			ignore_permissions=True
		)

	# Add the new role before removing the legacy role; preserve users and ownership.
	for name in frappe.get_all(
		"Has Role", filters={"parenttype": "User", "role": LEGACY_ROLE}, pluck="parent"
	):
		user = frappe.get_doc("User", name)
		user.append_roles(ROLE)
		user.redirect_url = "/crm"
		user.set("roles", [row for row in user.roles if row.role != LEGACY_ROLE])
		user.save(ignore_permissions=True)
		frappe.clear_cache(user=name)
