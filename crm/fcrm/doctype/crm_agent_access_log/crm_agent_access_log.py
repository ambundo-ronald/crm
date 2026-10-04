import frappe
from frappe.model.document import Document


class CRMAgentAccessLog(Document):
	def validate(self):
		if not self.is_new():
			frappe.throw("Agent access history cannot be changed")

	def on_trash(self):
		frappe.throw("Agent access history cannot be deleted")
