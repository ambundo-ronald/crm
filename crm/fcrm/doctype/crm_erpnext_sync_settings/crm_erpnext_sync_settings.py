import frappe
from frappe.model.document import Document


class CRMERPNextSyncSettings(Document):
	def validate(self):
		from crm.migration.sync import SETTINGS, _lock, parse_mapping, require_admin

		require_admin()
		_lock()
		# Desk saves cannot reset the internal cursor or last-run timestamp.
		self.opportunity_cursor = frappe.db.get_single_value(SETTINGS, "opportunity_cursor")
		self.cursor = frappe.db.get_single_value(SETTINGS, "cursor")
		self.last_run = frappe.db.get_single_value(SETTINGS, "last_run")
		parse_mapping(self.status_map)
		parse_mapping(self.opportunity_status_map)
		parse_mapping(self.user_map)
		if self.enabled and "erpnext" not in frappe.get_installed_apps():
			frappe.throw("ERPNext must be installed on this site")
