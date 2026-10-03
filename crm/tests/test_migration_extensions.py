import frappe
from frappe.tests import IntegrationTestCase

from crm.migration.extensions import (
	apply_custom_fields,
	field_inventory,
	preview_custom_fields,
	source_history,
)
from crm.migration.prospect import apply_prospect
from crm.migration.sync import initialize
from crm.migration.validation import report


class TestMigrationExtensions(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

		frappe.set_user("Administrator")
		cls.field = "custom_dev2_migration_test"
		cls.created_fields = []
		for doctype in ("Prospect", "CRM Organization"):
			if not frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": cls.field}):
				create_custom_fields(
					{doctype: [{"fieldname": cls.field, "label": "Migration test only", "fieldtype": "Data"}]}
				)
				cls.created_fields.append(doctype + "-" + cls.field)
		frappe.db.commit()

	@classmethod
	def tearDownClass(cls):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		for name in cls.created_fields:
			frappe.delete_doc("Custom Field", name, force=True)
		frappe.db.commit()
		super().tearDownClass()

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		initialize()
		self.source = frappe.get_doc(
			{
				"doctype": "Prospect",
				"company_name": "Extension " + frappe.generate_hash(length=10),
				"company": frappe.get_all("Company", pluck="name", limit_page_length=1)[0],
				self.field: "Original",
			}
		).insert()
		self.target = apply_prospect(self.source.name, {})["target"]
		self.fields = {self.field: self.field}

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		super().tearDown()

	def preview(self):
		return preview_custom_fields("Prospect", self.source.name, self.fields)

	def apply(self):
		return apply_custom_fields("Prospect", self.source.name, self.fields, self.preview()["preview_token"])

	def test_custom_preview_apply_rerun_clear_and_source_preserved(self):
		before = frappe.get_doc("Prospect", self.source.name).as_dict()
		proposal = self.preview()
		self.assertFalse(proposal["issues"])
		self.assertFalse(frappe.db.get_value("CRM Organization", self.target, self.field))
		self.assertEqual(self.apply()["status"], "Updated")
		self.assertEqual(self.apply()["status"], "Unchanged")
		self.assertEqual(frappe.get_doc("Prospect", self.source.name).as_dict(), before)
		self.source.db_set(self.field, None)
		self.assertEqual(self.apply()["status"], "Updated")
		self.assertFalse(frappe.db.get_value("CRM Organization", self.target, self.field))

	def test_custom_local_conflict_and_stale_preview(self):
		proposal = self.preview()
		self.source.db_set(self.field, "Changed")
		with self.assertRaises(frappe.ValidationError):
			apply_custom_fields("Prospect", self.source.name, self.fields, proposal["preview_token"])
		self.apply()
		frappe.db.set_value("CRM Organization", self.target, self.field, "Local")
		self.source.db_set(self.field, "Another")
		self.assertTrue(self.preview()["issues"])
		with self.assertRaises(frappe.ValidationError):
			self.apply()
		self.assertEqual(frappe.db.get_value("CRM Organization", self.target, self.field), "Local")

	def test_standard_fields_and_existing_custom_values_are_protected(self):
		for fields in ({"website": "website"}, {self.field: "owner"}):
			with self.assertRaises(frappe.ValidationError):
				preview_custom_fields("Prospect", self.source.name, fields)
		frappe.db.set_value("CRM Organization", self.target, self.field, "Existing")
		self.assertTrue(self.preview()["issues"])
		inventory = field_inventory("Prospect")
		self.assertTrue(
			any(row["fieldname"] == self.field and row["supported"] for row in inventory["source"])
		)

	def test_history_is_read_only_escaped_and_source_scoped(self):
		comment = self.source.add_comment("Comment", "<b>Original note</b>")
		before = frappe.get_doc("Comment", comment.name).as_dict()
		history = source_history("Prospect", self.source.name)
		row = next(row for row in history["rows"] if row["name"] == comment.name)
		self.assertEqual(row["content"], "Original note")
		self.assertEqual(frappe.get_doc("Comment", comment.name).as_dict(), before)
		self.assertEqual(row["owner"], comment.owner)
		self.assertFalse(
			frappe.db.exists(
				"Comment",
				{
					"reference_doctype": "CRM Organization",
					"reference_name": self.target,
					"content": comment.content,
				},
			)
		)
		self.source.reload()
		self.source.append(
			"notes",
			{"note": "<p>Legacy note</p>", "added_by": "Administrator", "added_on": "2020-01-02 12:00:00"},
		)
		self.source.save()
		notes = source_history("Prospect", self.source.name, "CRM Note")
		self.assertEqual(notes["rows"][0]["content"], "Legacy note")
		for kind in ("Communication", "File", "ToDo", "Event"):
			self.assertTrue(source_history("Prospect", self.source.name, kind)["read_only"])
		with self.assertRaises(frappe.ValidationError):
			source_history("Prospect", self.source.name, "User")

	def test_history_pagination_and_unmapped_sources(self):
		first = self.source.add_comment("Comment", "One")
		second = self.source.add_comment("Comment", "Two")
		cursor = min(first.name, second.name)
		rows = source_history("Prospect", self.source.name, after=cursor)["rows"]
		self.assertTrue(all(row["name"] > cursor for row in rows))
		self.source.reload()
		for index in range(51):
			self.source.append("notes", {"note": "Paged note " + str(index), "added_by": "Administrator"})
		self.source.save()
		page = source_history("Prospect", self.source.name, "CRM Note")
		self.assertTrue(page["has_more"])
		self.assertIsInstance(page["next_after"], str)
		self.assertEqual(
			len(source_history("Prospect", self.source.name, "CRM Note", page["next_after"])["rows"]), 1
		)
		with self.assertRaises(frappe.ValidationError):
			source_history("Prospect", "unmapped")

	def test_admin_only_extensions_and_unverified_staging_gates(self):
		result = report()
		self.assertFalse(result["ready_for_production"])
		self.assertIn("database_and_public_private_files_restored", result["unverified_gates"])
		frappe.set_user("Guest")
		for action in (
			report,
			lambda: field_inventory("Prospect"),
			self.preview,
			self.apply,
			lambda: source_history("Prospect", self.source.name),
		):
			with self.assertRaises(frappe.PermissionError):
				action()
