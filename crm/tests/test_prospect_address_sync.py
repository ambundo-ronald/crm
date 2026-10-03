from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from crm.migration.addresses import (
	approve_address_link,
	candidate,
	managed_address_links,
	preview_address_links,
	remove_address_link,
)
from crm.migration.customer import apply_customer
from crm.migration.opportunity import DEFAULT_STATUSES, apply_opportunity
from crm.migration.prospect import LINK, apply_prospect, sync_batch
from crm.migration.sync import SETTINGS, configure_prospects, initialize


class TestProspectAddressSync(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		initialize()
		frappe.db.set_single_value(
			SETTINGS, {"enabled": 0, "sync_prospects": 0, "prospect_cursor": "", "user_map": "{}"}
		)
		self.company = frappe.get_all("Company", fields=["name", "default_currency"], limit_page_length=1)[0]
		self.prospect = frappe.get_doc(
			{
				"doctype": "Prospect",
				"company_name": "Sync Prospect " + frappe.generate_hash(length=10),
				"company": self.company.name,
				"website": "https://example.invalid",
			}
		).insert()
		self.agent = "prospect.agent." + frappe.generate_hash(length=10) + "@example.invalid"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": self.agent,
				"first_name": "Agent",
				"send_welcome_email": 0,
				"user_type": "Website User",
				"roles": [{"role": "Commission Agent"}],
			}
		).insert()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.clear_cache(user=self.agent)
		super().tearDown()

	def address(self):
		return frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": "Additional " + frappe.generate_hash(length=10),
				"address_type": "Shipping",
				"address_line1": "Synthetic street",
				"city": "Nairobi",
				"country": "Kenya",
				"links": [{"link_doctype": "Prospect", "link_name": self.prospect.name}],
			}
		).insert()

	def approve(self, address):
		row = candidate(address.name, "Prospect", self.prospect.name)
		return approve_address_link(
			address.name, "Prospect", self.prospect.name, row.get("preview_token", "")
		)

	def test_prospect_create_repeat_update_conflict_and_provenance(self):
		before = self.prospect.modified
		self.prospect.db_set("owner", self.agent, update_modified=False)
		result = apply_prospect(self.prospect.name, {})
		self.assertEqual(result["status"], "Created", result)
		organization = frappe.get_doc("CRM Organization", result["target"])
		self.assertEqual(organization.owner, self.agent)
		self.assertEqual(str(frappe.db.get_value("Prospect", self.prospect.name, "modified")), str(before))
		self.assertEqual(apply_prospect(self.prospect.name, {})["status"], "Unchanged")
		self.prospect.db_set("website", "https://new.example.invalid")
		self.assertEqual(apply_prospect(self.prospect.name, {})["status"], "Updated")
		frappe.db.set_value("CRM Organization", organization.name, "website", "https://local.example.invalid")
		self.prospect.db_set("website", "https://conflict.example.invalid")
		self.assertIn("field_conflict:website", apply_prospect(self.prospect.name, {})["issues"])
		self.assertEqual(frappe.db.count(LINK, {"source_name": self.prospect.name}), 1)

	def test_customer_prospect_name_collision_reviews_both(self):
		customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": self.prospect.company_name,
				"customer_type": "Company",
				"customer_group": frappe.get_all("Customer Group", pluck="name", limit_page_length=1)[0],
				"territory": frappe.get_all("Territory", pluck="name", limit_page_length=1)[0],
			}
		).insert()
		self.assertIn(
			"customer_prospect_duplicate_candidates", apply_prospect(self.prospect.name, {})["issues"]
		)
		self.assertIn("customer_prospect_duplicate_candidates", apply_customer(customer.name, {})["issues"])

	def test_prospect_opportunity_uses_organization_and_preserves_party(self):
		organization = apply_prospect(self.prospect.name, {})["target"]
		frappe.db.set_single_value(
			"FCRM Settings", {"currency": self.company.default_currency, "enable_forecasting": 0}
		)
		frappe.db.set_single_value("ERPNext CRM Settings", "enabled", 0)
		opportunity = frappe.get_doc(
			{
				"doctype": "Opportunity",
				"opportunity_from": "Prospect",
				"party_name": self.prospect.name,
				"company": self.company.name,
				"currency": self.company.default_currency,
				"opportunity_amount": 500,
				"opportunity_owner": "Administrator",
				"status": "Open",
			}
		).insert()
		result = apply_opportunity(opportunity.name, DEFAULT_STATUSES, {})
		self.assertEqual(result["status"], "Created", result)
		deal = frappe.get_doc("CRM Deal", result["target"])
		self.assertEqual(deal.organization, organization)
		self.assertFalse(deal.lead)
		self.assertEqual(apply_opportunity(opportunity.name, DEFAULT_STATUSES, {})["status"], "Unchanged")
		frappe.db.set_value("CRM Deal", deal.name, "organization", None)
		self.assertEqual(apply_opportunity(opportunity.name, DEFAULT_STATUSES, {})["status"], "Review")

	def test_prospect_batch_rollback_and_opt_in(self):
		self.assertFalse(frappe.get_single(SETTINGS).sync_prospects)
		configure_prospects(enabled=True)
		from crm.fcrm.doctype.crm_erpnext_prospect_link.crm_erpnext_prospect_link import (
			CRMERPNextProspectLink,
		)

		with patch.object(
			CRMERPNextProspectLink, "before_insert", create=True, side_effect=ValueError("Synthetic")
		):
			row = next(
				row
				for row in sync_batch(frappe.get_single(SETTINGS))["results"]
				if row["source"] == self.prospect.name
			)
			self.assertEqual(row["status"], "Failed")
		self.assertFalse(frappe.db.exists("CRM Organization", self.prospect.company_name))
		self.assertEqual(apply_prospect(self.prospect.name, {})["status"], "Created")

	def test_address_reuse_read_only_preview_and_exact_reversal(self):
		organization = apply_prospect(self.prospect.name, {})["target"]
		address = self.address()
		before = frappe.get_doc("Address", address.name).as_dict()
		preview_address_links()
		self.assertEqual(frappe.get_doc("Address", address.name).as_dict(), before)
		result = self.approve(address)
		self.assertEqual(result["status"], "Linked")
		self.assertEqual(self.approve(address)["status"], "Already linked")
		address.reload()
		self.assertEqual(address.address_line1, before.address_line1)
		self.assertEqual(len(address.links), 2)
		self.assertFalse(frappe.db.get_value("CRM Organization", organization, "address"))
		frappe.db.delete("Dynamic Link", {"parent": address.name, "link_doctype": "Prospect"})
		remove_address_link(result["audit"])
		self.assertEqual(len(frappe.get_doc("Address", address.name).links), 0)
		self.assertEqual(remove_address_link(result["audit"])["status"], "Already removed")

	def test_stale_disabled_and_preexisting_addresses(self):
		organization = apply_prospect(self.prospect.name, {})["target"]
		address = self.address()
		row = candidate(address.name, "Prospect", self.prospect.name)
		address.address_line1 = "Edited"
		address.save()
		with self.assertRaises(frappe.ValidationError):
			approve_address_link(address.name, "Prospect", self.prospect.name, row.get("preview_token", ""))
		address.append("links", {"link_doctype": "CRM Organization", "link_name": organization})
		address.save()
		self.assertEqual(self.approve(address)["status"], "Already linked")
		self.assertFalse(frappe.db.exists("CRM ERPNext Address Link", {"address": address.name}))
		address.disabled = 1
		address.save()
		with self.assertRaises(frappe.ValidationError):
			self.approve(address)

	def test_guests_agents_cannot_manage_prospects_or_addresses(self):
		for user in ("Guest", self.agent):
			frappe.set_user(user)
			for action in (configure_prospects, preview_address_links, managed_address_links):
				with self.assertRaises(frappe.PermissionError):
					action()
			with self.assertRaises(frappe.PermissionError):
				apply_prospect(self.prospect.name, {})
			with self.assertRaises(frappe.PermissionError):
				approve_address_link("forged", "Prospect", self.prospect.name, "forged")
			with self.assertRaises(frappe.PermissionError):
				remove_address_link("forged")

	def test_address_review_respects_lead_consent(self):
		from crm.migration.sync import configure, run_batch

		lead = frappe.get_doc(
			{
				"doctype": "Lead",
				"first_name": "Address Consent",
				"email_id": frappe.generate_hash(length=10) + "@example.invalid",
				"status": "Lead",
				"lead_owner": "Administrator",
			}
		).insert()
		configure(enabled=True)
		run_batch()
		address = self.address()
		address.append("links", {"link_doctype": "Lead", "link_name": lead.name})
		address.save()
		lead.db_set("status", "Do Not Contact")
		row = candidate(address.name, "Lead", lead.name)
		self.assertIn("source_lifecycle_or_creator_requires_review", row["issues"])
		with self.assertRaises(frappe.ValidationError):
			approve_address_link(address.name, "Lead", lead.name, "forged")

	def test_address_removal_refuses_changed_child(self):
		apply_prospect(self.prospect.name, {})
		address = self.address()
		result = self.approve(address)
		child = frappe.db.get_value("CRM ERPNext Address Link", result["audit"], "link_name")
		frappe.db.set_value(
			"Dynamic Link", child, {"link_doctype": "Prospect", "link_name": self.prospect.name}
		)
		with self.assertRaises(frappe.ValidationError):
			remove_address_link(result["audit"])
		self.assertTrue(frappe.db.exists("Dynamic Link", child))
