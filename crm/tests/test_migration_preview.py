from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from crm.migration.erpnext import preview


class TestMigrationPreview(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.source = frappe.get_doc(
			{
				"doctype": "Lead",
				"first_name": "Migration preview sample",
				"email_id": "migration.preview@example.invalid",
				"status": "Lead",
				"lead_owner": "Administrator",
			}
		).insert()
		self.second = frappe.get_doc(
			{
				"doctype": "Lead",
				"first_name": "Migration preview second",
				"status": "Do Not Contact",
				"lead_owner": "Administrator",
			}
		).insert()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		super().tearDown()

	def test_preview_does_not_write_and_reports_stable_source_identity(self):
		original_sql = frappe.db.sql

		def read_only(query, *args, **kwargs):
			statement = str(query).lstrip().lower()
			self.assertTrue(statement.startswith(("select", "with", "show", "describe")), statement[:60])
			return original_sql(query, *args, **kwargs)

		with patch.object(frappe.db, "sql", side_effect=read_only):
			report = preview(limit=500)
		self.assertEqual(report["mode"], "read_only_preview")
		row = next(row for row in report["proposals"] if row["source_key"][2] == self.source.name)
		self.assertEqual(row["source_key"], [frappe.local.site, "Lead", self.source.name])
		self.assertEqual(row["proposed_creator"], "Administrator")
		self.assertEqual(
			frappe.db.get_value("Lead", self.source.name, "modified"),
			frappe.utils.get_datetime(self.source.modified),
		)
		self.assertFalse(frappe.db.exists("CRM Lead", {"email": "migration.preview@example.invalid"}))
		excluded = next(row for row in report["proposals"] if row["source_key"][2] == self.second.name)
		self.assertEqual(excluded["action"], "review")

	def test_pagination_and_input_validation(self):
		first = preview(limit=1)
		self.assertTrue(first["has_more"])
		second = preview(limit=1, after=first["next_after"])
		self.assertNotEqual(first["proposals"][0]["source_key"], second["proposals"][0]["source_key"])
		for args in ({"limit": 501}, {"after": ["like", "%"]}, {"status_map": {"Lead": 1}}):
			with self.subTest(args=args), self.assertRaises(frappe.ValidationError):
				preview(**args)

	def test_guests_and_agent_accounts_are_denied(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			preview()
		frappe.set_user("Administrator")
		with patch("crm.migration.erpnext.is_agent", return_value=True):
			with self.assertRaises(frappe.PermissionError):
				preview()
		self.assertNotIn(preview, frappe.whitelisted)
