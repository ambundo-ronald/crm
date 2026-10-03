import frappe

from crm.permissions.commission_agent import require_agent

no_cache = 1


def get_context(context):
	if frappe.session.user == "Administrator":
		frappe.local.flags.redirect_location = "/crm"
		raise frappe.Redirect

	if frappe.session.user == "Guest":
		frappe.local.flags.redirect_location = "/login?redirect-to=/crm-agent"
		raise frappe.Redirect
	require_agent()
	context.csrf_token = frappe.sessions.get_csrf_token()
	context.agent_name = frappe.db.get_value("User", frappe.session.user, "full_name")
	context.time_zone = frappe.utils.get_system_timezone()
