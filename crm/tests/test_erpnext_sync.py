import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from crm.migration.sync import (
	LINK,
	RUN,
	SETTINGS,
	configure,
	initialize,
	run_batch,
	scheduled_sync,
	status,
	sync_now,
)


class TestERPNextSync(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		initialize()
		frappe.db.set_single_value(
			SETTINGS, {"enabled": 1, "automatic": 0, "cursor": "", "status_map": "{}", "user_map": "{}"}
		)
		self.source = frappe.get_doc(
			{
				"doctype": "Lead",
				"first_name": "Sync Sample",
				"email_id": "sync-" + frappe.generate_hash(length=12) + "@example.invalid",
				"status": "Lead",
				"lead_owner": "Administrator",
			}
		).insert()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		super().tearDown()

	def row(self):
		return next(row for row in run_batch()["results"] if row["source"] == self.source.name)

	def test_create_repeat_update_and_source_unchanged(self):
		modified = self.source.modified
		created = self.row()
		self.assertEqual(created["status"], "Created", created)
		self.assertEqual(self.row()["status"], "Unchanged")
		self.assertEqual(frappe.db.count(LINK, {"source_name": self.source.name}), 1)
		self.assertEqual(str(frappe.db.get_value("Lead", self.source.name, "modified")), str(modified))
		self.source.phone = "254700112233"
		self.source.save()
		self.assertEqual(self.row()["status"], "Updated")
		self.assertEqual(frappe.db.get_value("CRM Lead", created["target"], "phone"), self.source.phone)
		self.source.phone = ""
		self.source.save()
		self.assertEqual(self.row()["status"], "Updated")
		self.assertFalse(frappe.db.get_value("CRM Lead", created["target"], "phone"))

	def test_local_edits_preserved_and_conflicts_block_entire_record(self):
		created = self.row()
		target = frappe.get_doc("CRM Lead", created["target"])
		target.phone = "254711000111"
		target.status = "Qualified"
		target.save()
		self.assertEqual(self.row()["status"], "Unchanged")
		self.source.phone = "254722000222"
		self.source.job_title = "Director"
		self.source.save()
		row = self.row()
		self.assertEqual(row["status"], "Review")
		self.assertIn("field_conflict:phone", row["issues"])
		target.reload()
		self.assertEqual(target.phone, "254711000111")
		self.assertFalse(target.job_title)
		self.assertEqual(target.status, "Qualified")
		# Explicitly reconcile the CRM value, then retry normally.
		target.phone = self.source.phone
		target.save()
		self.assertEqual(self.row()["status"], "Updated")

	def test_consent_duplicates_and_conversion_require_review(self):
		self.source.status = "Do Not Contact"
		self.source.save()
		self.assertEqual(self.row()["status"], "Review")
		self.assertFalse(frappe.db.exists(LINK, {"source_name": self.source.name}))
		self.source.status = "Lead"
		self.source.save()
		created = self.row()
		frappe.db.set_value("CRM Lead", created["target"], "converted", 1)
		self.assertIn("creator_or_conversion_changed", self.row()["issues"])

	def test_failure_rolls_back_mapping_and_target_and_retry_succeeds(self):
		from crm.migration import sync

		original_apply = sync._apply

		def fail_after_insert(proposal):
			result = original_apply(proposal)
			if proposal["source_key"][2] == self.source.name:
				raise ValueError("Synthetic failure")
			return result

		with patch.object(sync, "_apply", side_effect=fail_after_insert):
			self.assertEqual(self.row()["status"], "Failed")
		self.assertFalse(frappe.db.exists(LINK, {"source_name": self.source.name}))
		self.assertFalse(frappe.db.exists("CRM Lead", {"email": self.source.email_id}))
		self.assertEqual(self.row()["status"], "Created")
		self.assertTrue(frappe.db.count(RUN))

	def test_disabled_schedule_and_permissions(self):
		with patch("crm.migration.sync.run_batch") as run:
			scheduled_sync()
			run.assert_not_called()
			frappe.db.set_single_value(SETTINGS, "automatic", 1)
			scheduled_sync()
			run.assert_called_once_with(automatic=True)
		configure(enabled=False)
		with self.assertRaises(frappe.ValidationError):
			sync_now()
		frappe.set_user("Guest")
		for method in (status, sync_now, configure):
			with self.assertRaises(frappe.PermissionError):
				method()
		frappe.set_user("Administrator")
		with patch("crm.migration.sync.is_agent", return_value=True):
			with self.assertRaises(frappe.PermissionError):
				configure(enabled=True)

	def test_pagination_and_mapping_validation(self):
		with self.assertRaises(frappe.ValidationError):
			frappe.get_single(SETTINGS).update({"user_map": json.dumps({"x": 4})}).save()
		from crm.migration import sync

		real_preview = sync.preview
		with patch.object(sync, "preview", side_effect=lambda **kw: real_preview(**(kw | {"limit": 1}))):
			first = run_batch()
			second = run_batch()
			self.assertTrue(first["has_more"])
			self.assertNotEqual(first["results"][0]["source"], second["results"][0]["source"])

	def test_duplicates_never_merge_and_contacts_stay_unlinked(self):
		contacts = frappe.get_all(
			"Dynamic Link",
			filters={"parenttype": "Contact", "link_doctype": "Lead", "link_name": self.source.name},
			pluck="parent",
		)
		created = self.row()
		self.assertEqual(created["status"], "Created")
		if contacts:
			self.assertFalse(
				frappe.db.exists(
					"Dynamic Link",
					{"parent": ["in", contacts], "link_doctype": "CRM Lead", "link_name": created["target"]},
				)
			)
		duplicate = frappe.get_doc(
			{
				"doctype": "CRM Lead",
				"first_name": "Existing duplicate",
				"email": self.source.email_id,
				"status": "New",
				"lead_owner": "Administrator",
			}
		).insert()
		self.source.job_title = "Should not overwrite"
		self.source.save()
		row = self.row()
		self.assertIn("crm_duplicate_candidates", row["issues"])
		self.assertFalse(frappe.db.get_value("CRM Lead", created["target"], "job_title"))
		self.assertFalse(duplicate.job_title)

	def test_agent_creator_is_preserved_without_contact_access_expansion(self):
		from crm.api.agent import own_lead

		email = "sync.agent." + frappe.generate_hash(length=10) + "@example.invalid"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Sync Agent",
				"enabled": 1,
				"user_type": "Website User",
				"send_welcome_email": 0,
				"roles": [{"role": "Commission Agent"}],
			}
		).insert()
		self.source.db_set("owner", email)
		created = self.row()
		self.assertEqual(created["status"], "Created", created)
		self.assertEqual(frappe.db.get_value("CRM Lead", created["target"], "owner"), email)
		own_lead(created["target"], email)
		with self.assertRaises(frappe.PermissionError):
			own_lead(created["target"], "someone.else@example.invalid")
		frappe.set_user(email)
		with self.assertRaises(frappe.PermissionError):
			sync_now()
		frappe.set_user("Administrator")
		frappe.clear_cache(user=email)

	def test_initialize_persists_disabled_lock_row(self):
		frappe.db.sql("DELETE FROM `tabSingles` WHERE doctype=%s", SETTINGS)
		frappe.db.value_cache.pop(SETTINGS, None)
		initialize()
		self.assertTrue(
			frappe.db.sql("SELECT field FROM `tabSingles` WHERE doctype=%s AND field='enabled'", SETTINGS)
		)
		self.assertFalse(status()["enabled"])
		configure(enabled=True)
		self.assertTrue(status()["enabled"])
