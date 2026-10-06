"""Compatibility redirect for bookmarks to the retired separate workspace."""

import frappe

no_cache = 1


def get_context(context):
	frappe.local.flags.redirect_location = (
		"/login?redirect-to=/crm" if frappe.session.user == "Guest" else "/crm"
	)
	redirect = frappe.Redirect()
	redirect.http_status_code = 302
	raise redirect
