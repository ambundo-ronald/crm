import unittest

from crm.migration.planner import plan_leads


class TestMigrationPlanner(unittest.TestCase):
	def setUp(self):
		self.source = {
			"name": "ERP-1",
			"first_name": "Sample",
			"email_id": "sample@example.invalid",
			"owner": "sales@example.invalid",
			"lead_owner": "sales@example.invalid",
			"status": "Lead",
		}
		self.users = {"sales@example.invalid": {"enabled": 1, "user_type": "System User"}}
		self.statuses = ["New", "Contacted", "Nurture", "Qualified"]

	def plan(self, source=None, targets=None, **kwargs):
		return plan_leads(
			[source or self.source], targets or [], self.users, self.statuses, "local.test", **kwargs
		)[0]

	def test_explicit_field_mapping_and_provenance(self):
		self.source.update(company_name="Sample Ltd", creation="2020-01-01 09:00:00")
		row = self.plan()
		self.assertEqual(row["action"], "create_candidate")
		self.assertEqual(row["source_key"], ["local.test", "Lead", "ERP-1"])
		self.assertEqual(row["proposed_fields"]["email"], "sample@example.invalid")
		self.assertEqual(row["proposed_fields"]["organization"], "Sample Ltd")
		self.assertEqual(row["provenance"]["creation"], "2020-01-01 09:00:00")
		self.assertNotIn("name", row["proposed_fields"])
		self.assertNotIn("owner", row["proposed_fields"])

	def test_duplicate_email_and_formatted_phone_are_reviewed_not_merged(self):
		self.source["mobile_no"] = "+254 700-000-001"
		row = self.plan(
			targets=[
				{"name": "CRM-1", "email": " SAMPLE@example.invalid "},
				{"name": "CRM-2", "phone": "+254700000001"},
			]
		)
		self.assertEqual(row["duplicate_crm_leads"], ["CRM-1", "CRM-2"])
		self.assertEqual(row["action"], "review")

	def test_source_duplicates_are_found_outside_the_page(self):
		other = dict(self.source, name="ERP-2")
		row = plan_leads(
			[self.source, other], [], self.users, self.statuses, "local.test", batch=[self.source]
		)[0]
		self.assertEqual(row["duplicate_source_leads"], ["ERP-2"])

	def test_disabled_or_unknown_creator_requires_explicit_resolution(self):
		self.source["owner"] = "old@example.invalid"
		self.assertIn("creator_missing_or_disabled", self.plan()["issues"])
		self.assertEqual(
			self.plan(user_map={"old@example.invalid": "sales@example.invalid"})["action"], "create_candidate"
		)
		self.users["sales@example.invalid"]["enabled"] = 0
		self.assertIn("creator_missing_or_disabled", self.plan()["issues"])

	def test_lifecycle_and_consent_flags_cannot_be_removed_by_status_mapping(self):
		for status in ("Converted", "Do Not Contact", "Lost Quotation"):
			with self.subTest(status=status):
				row = self.plan(dict(self.source, status=status), status_map={status: "New"})
				self.assertIn("lifecycle_or_contact_consent_requires_review", row["issues"])
		for flag in ("disabled", "unsubscribed"):
			self.assertIn(
				"lifecycle_or_contact_consent_requires_review",
				self.plan(dict(self.source, **{flag: 1}))["issues"],
			)

	def test_unknown_status_missing_name_and_partial_inventory(self):
		row = self.plan(dict(self.source, status="Custom", first_name=""), inventory_complete=False)
		self.assertIn("unmapped_status", row["issues"])
		self.assertIn("missing_first_name", row["issues"])
		self.assertIn("duplicate_inventory_incomplete", row["issues"])
		self.assertIn("target_status_missing", self.plan(status_map={"Lead": "Missing"})["issues"])

	def test_agent_creator_is_preserved_without_staff_assignment(self):
		self.users["sales@example.invalid"].update(user_type="Website User", is_agent=True)
		row = self.plan(dict(self.source, lead_owner=None))
		self.assertEqual(row["action"], "create_candidate")
		self.assertEqual(row["proposed_creator"], "sales@example.invalid")
		self.assertNotIn("lead_owner", row["proposed_fields"])
		self.assertIn("salesperson_requires_review", self.plan()["issues"])

	def test_contact_link_disclosure_requires_review(self):
		row = self.plan(dict(self.source, contacts=["Shared-Contact"]))
		self.assertEqual(row["shared_contacts"], ["Shared-Contact"])
		self.assertIn("shared_contact_links_require_review", row["issues"])

	def test_phone_country_codes_are_not_guessed(self):
		row = self.plan(
			dict(self.source, email_id=None, mobile_no="0700000001"),
			targets=[{"name": "CRM-1", "mobile_no": "+254700000001"}],
		)
		self.assertFalse(row["duplicate_crm_leads"])


if __name__ == "__main__":
	unittest.main()
