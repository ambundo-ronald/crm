from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from crm.migration.contacts import (
	AUDIT,
	approve_contact_link,
	candidate,
	managed_contact_links,
	preview_contact_links,
	remove_contact_link,
)
from crm.migration.customer import LINK, apply_customer, sync_batch
from crm.migration.opportunity import DEFAULT_STATUSES, apply_opportunity
from crm.migration.sync import SETTINGS, configure_customers, initialize, run_batch


class TestCustomerContactSync(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		initialize()
		frappe.db.set_single_value(
			SETTINGS,
			{
				"enabled": 1,
				"automatic": 0,
				"sync_customers": 0,
				"sync_customer_addresses": 0,
				"sync_opportunities": 0,
				"cursor": "",
				"customer_cursor": "",
				"opportunity_cursor": "",
				"status_map": "{}",
				"user_map": "{}",
			},
		)
		self.customer = frappe.get_doc(
			{
				"doctype": "Customer",
				"customer_name": "Sync Business " + frappe.generate_hash(length=10),
				"customer_type": "Company",
				"customer_group": frappe.get_all("Customer Group", pluck="name", limit_page_length=1)[0],
				"territory": frappe.get_all("Territory", pluck="name", limit_page_length=1)[0],
			}
		).insert()
		self.agent = "relationship.agent." + frappe.generate_hash(length=10) + "@example.invalid"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": self.agent,
				"first_name": "Relationship Agent",
				"enabled": 1,
				"user_type": "Website User",
				"send_welcome_email": 0,
				"roles": [{"role": "Commission Agent"}],
			}
		).insert()
		self.lead = frappe.get_doc(
			{
				"doctype": "Lead",
				"first_name": "Relationship Lead",
				"email_id": frappe.generate_hash(length=10) + "@example.invalid",
				"lead_owner": "Administrator",
				"status": "Lead",
			}
		).insert()
		self.lead.db_set("owner", self.agent)
		result = run_batch()
		self.crm_lead = next(row["target"] for row in result["results"] if row["source"] == self.lead.name)
		self.contact = frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": "Shared relationship contact",
				"email_ids": [{"email_id": "shared@example.invalid", "is_primary": 1}],
				"links": [
					{"link_doctype": "Lead", "link_name": self.lead.name},
					{"link_doctype": "Customer", "link_name": self.customer.name},
				],
			}
		).insert()

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.clear_cache(user=self.agent)
		super().tearDown()

	def approve(self, source_type="Lead", source=None):
		source = source or self.lead.name
		row = candidate(self.contact.name, source_type, source)
		return approve_contact_link(self.contact.name, source_type, source, row["preview_token"])

	def test_customer_rerun_update_and_source_unchanged(self):
		before = self.customer.modified
		result = apply_customer(self.customer.name, {})
		self.assertEqual(result["status"], "Created", result)
		self.assertEqual(apply_customer(self.customer.name, {})["status"], "Unchanged")
		self.assertEqual(frappe.db.count(LINK, {"source_name": self.customer.name}), 1)
		self.assertEqual(str(frappe.db.get_value("Customer", self.customer.name, "modified")), str(before))
		self.customer.website = "https://example.invalid"
		self.customer.save()
		self.assertEqual(apply_customer(self.customer.name, {})["status"], "Updated")
		self.customer.website = ""
		self.customer.save()
		self.assertEqual(apply_customer(self.customer.name, {})["status"], "Updated")
		self.assertFalse(frappe.db.get_value("CRM Organization", result["target"], "website"))

	def test_customer_conflict_duplicate_and_exclusions(self):
		result = apply_customer(self.customer.name, {})
		target = frappe.get_doc("CRM Organization", result["target"])
		target.website = "https://local.example.invalid"
		target.save()
		self.customer.website = "https://upstream.example.invalid"
		self.customer.save()
		self.assertIn("field_conflict:website", apply_customer(self.customer.name, {})["issues"])
		for field, value in [("customer_type", "Individual"), ("disabled", 1), ("is_frozen", 1)]:
			original = self.customer.get(field)
			frappe.db.set_value("Customer", self.customer.name, field, value)
			self.assertEqual(apply_customer(self.customer.name, {})["status"], "Review")
			frappe.db.set_value("Customer", self.customer.name, field, original)
		duplicate = frappe.get_doc(
			{
				"doctype": "CRM Organization",
				"organization_name": "Collision " + frappe.generate_hash(length=8),
			}
		).insert()
		self.customer.reload()
		self.customer.customer_name = duplicate.organization_name
		self.customer.save()
		self.assertIn("organization_duplicate_candidates", apply_customer(self.customer.name, {})["issues"])

	def test_customer_opt_in_and_failed_mapping_rolls_back(self):
		self.assertFalse(frappe.db.exists(LINK, {"source_name": self.customer.name}))
		configure_customers(enabled=True)
		from crm.fcrm.doctype.crm_erpnext_customer_link.crm_erpnext_customer_link import (
			CRMERPNextCustomerLink,
		)

		with patch.object(
			CRMERPNextCustomerLink, "before_insert", create=True, side_effect=ValueError("Synthetic failure")
		):
			rows = sync_batch(frappe.get_single(SETTINGS))["results"]
			row = next(row for row in rows if row["source"] == self.customer.name)
			self.assertEqual(row["status"], "Failed")
		self.assertFalse(frappe.db.exists("CRM Organization", self.customer.customer_name))
		self.assertEqual(apply_customer(self.customer.name, {})["status"], "Created")

	def test_customer_opportunity_uses_organization_without_fake_lead(self):
		organization = apply_customer(self.customer.name, {})["target"]
		company = frappe.get_all("Company", fields=["name", "default_currency"], limit_page_length=1)[0]
		frappe.db.set_single_value(
			"FCRM Settings", {"currency": company.default_currency, "enable_forecasting": 0}
		)
		frappe.db.set_single_value("ERPNext CRM Settings", "enabled", 0)
		opportunity = frappe.get_doc(
			{
				"doctype": "Opportunity",
				"opportunity_from": "Customer",
				"party_name": self.customer.name,
				"company": company.name,
				"currency": company.default_currency,
				"opportunity_amount": 1200,
				"expected_closing": "2030-06-30",
				"opportunity_owner": "Administrator",
				"status": "Open",
			}
		).insert()
		result = apply_opportunity(opportunity.name, DEFAULT_STATUSES, {})
		self.assertEqual(result["status"], "Created", result)
		target = frappe.get_doc("CRM Deal", result["target"])
		self.assertEqual(target.organization, organization)
		self.assertFalse(target.lead)
		self.assertEqual(apply_opportunity(opportunity.name, DEFAULT_STATUSES, {})["status"], "Unchanged")
		frappe.db.set_value("Customer", self.customer.name, "disabled", 1)
		self.assertIn(
			"customer_lifecycle_requires_review",
			apply_opportunity(opportunity.name, DEFAULT_STATUSES, {})["issues"],
		)

	def test_contact_preview_is_read_only_and_shows_agent_scope(self):
		before = frappe.db.get_value("Contact", self.contact.name, "modified")
		count = frappe.db.count("Dynamic Link")
		row = candidate(self.contact.name, "Lead", self.lead.name)
		self.assertTrue(row["agent_visibility"])
		self.assertEqual(row["target_owner"], self.agent)
		self.assertEqual(row["other_link_count"], 2)
		preview_contact_links()
		self.assertEqual(frappe.db.count("Dynamic Link"), count)
		self.assertEqual(frappe.db.get_value("Contact", self.contact.name, "modified"), before)

	def test_contact_reuse_visibility_and_reversal(self):
		from crm.api.agent import contacts, save_contact

		count = frappe.db.count("Contact")
		before = self.contact.as_dict()
		self.assertNotIn(self.contact.name, [row.name for row in contacts(self.agent)])
		result = self.approve()
		self.assertEqual(result["status"], "Linked")
		self.assertIn(self.contact.name, [row.name for row in contacts(self.agent)])
		self.assertNotIn(self.contact.name, [row.name for row in contacts("other.agent@example.invalid")])
		self.contact.reload()
		self.assertEqual(self.contact.owner, before.owner)
		self.assertEqual(self.contact.email_id, before.email_id)
		self.assertEqual(frappe.db.count("Contact"), count)
		self.assertEqual(len(self.contact.links), 3)
		self.assertEqual(self.approve()["status"], "Already linked")
		frappe.set_user(self.agent)
		with self.assertRaises(frappe.PermissionError):
			save_contact({"first_name": "Do not change"}, name=self.contact.name)
		frappe.set_user("Administrator")
		remove_contact_link(result["audit"])
		self.assertNotIn(self.contact.name, [row.name for row in contacts(self.agent)])
		self.contact.reload()
		self.assertEqual(len(self.contact.links), 2)
		self.assertEqual(remove_contact_link(result["audit"])["status"], "Already removed")
		self.assertEqual(self.approve()["status"], "Linked")

	def test_contact_to_organization_grants_no_agent_lead_access(self):
		from crm.api.agent import contacts

		organization = apply_customer(self.customer.name, {})["target"]
		row = candidate(self.contact.name, "Customer", self.customer.name)
		self.assertFalse(row["agent_visibility"])
		self.approve("Customer", self.customer.name)
		self.assertTrue(
			frappe.db.exists(
				"Dynamic Link",
				{"parent": self.contact.name, "link_doctype": "CRM Organization", "link_name": organization},
			)
		)
		self.assertNotIn(self.contact.name, [row.name for row in contacts(self.agent)])

	def test_stale_review_and_forged_source_are_rejected(self):
		row = candidate(self.contact.name, "Lead", self.lead.name)
		frappe.db.set_value("CRM Lead", self.crm_lead, "owner", "Administrator")
		with self.assertRaises(frappe.ValidationError):
			approve_contact_link(self.contact.name, "Lead", self.lead.name, row["preview_token"])
		with self.assertRaises(frappe.ValidationError):
			approve_contact_link(self.contact.name, "User", "Administrator", "forged")
		frappe.db.delete("Dynamic Link", {"parent": self.contact.name, "link_doctype": "Lead"})
		with self.assertRaises(frappe.ValidationError):
			approve_contact_link(self.contact.name, "Lead", self.lead.name, row["preview_token"])

	def test_preexisting_link_is_not_managed_or_removed(self):
		self.contact.append("links", {"link_doctype": "CRM Lead", "link_name": self.crm_lead})
		self.contact.save()
		self.assertEqual(self.approve()["status"], "Already linked")
		self.assertFalse(frappe.db.exists(AUDIT, {"contact": self.contact.name}))
		self.assertFalse(candidate(self.contact.name, "Lead", self.lead.name)["managed_link"])

	def test_link_removal_survives_source_unlink(self):
		audit = self.approve()["audit"]
		frappe.db.delete("Dynamic Link", {"parent": self.contact.name, "link_doctype": "Lead"})
		self.assertIn(audit, [row.name for row in managed_contact_links()["links"]])
		remove_contact_link(audit)
		self.assertEqual(frappe.db.get_value(AUDIT, audit, "state"), "Removed")

	def test_relationship_actions_deny_guests_and_agents(self):
		for user in ("Guest", self.agent):
			frappe.set_user(user)
			for action in (preview_contact_links, managed_contact_links, configure_customers):
				with self.assertRaises(frappe.PermissionError):
					action()
			with self.assertRaises(frappe.PermissionError):
				approve_contact_link(self.contact.name, "Lead", self.lead.name, "forged")
			with self.assertRaises(frappe.PermissionError):
				remove_contact_link("forged")
		frappe.set_user("Administrator")

	def make_address(self, linked=True):
		return frappe.get_doc(
			{
				"doctype": "Address",
				"address_title": "Sync Address " + frappe.generate_hash(length=10),
				"address_type": "Billing",
				"address_line1": "Synthetic street",
				"city": "Nairobi",
				"country": "Kenya",
				"links": [{"link_doctype": "Customer", "link_name": self.customer.name}] if linked else [],
			}
		).insert()

	def test_primary_address_opt_in_reuses_identity_without_source_writes(self):
		address = self.make_address()
		self.customer.db_set("customer_primary_address", address.name)
		before = frappe.get_doc("Address", address.name).as_dict()
		organization = apply_customer(self.customer.name, {})["target"]
		self.assertFalse(frappe.db.get_value("CRM Organization", organization, "address"))
		result = apply_customer(self.customer.name, {}, sync_addresses=True)
		self.assertEqual(result["status"], "Updated", result)
		self.assertEqual(frappe.db.get_value("CRM Organization", organization, "address"), address.name)
		self.assertEqual(frappe.get_doc("Address", address.name).as_dict(), before)
		self.assertEqual(apply_customer(self.customer.name, {}, sync_addresses=True)["status"], "Unchanged")
		self.customer.db_set("customer_primary_address", None)
		self.assertEqual(apply_customer(self.customer.name, {}, sync_addresses=True)["status"], "Updated")
		self.assertFalse(frappe.db.get_value("CRM Organization", organization, "address"))
		self.assertTrue(frappe.db.exists("Address", address.name))

	def test_address_conflicts_and_disabled_sync_preserve_baseline(self):
		first, second, local = self.make_address(), self.make_address(), self.make_address()
		self.customer.db_set("customer_primary_address", first.name)
		organization = apply_customer(self.customer.name, {}, sync_addresses=True)["target"]
		frappe.db.set_value("CRM Organization", organization, "address", local.name)
		self.customer.db_set("customer_primary_address", second.name)
		apply_customer(self.customer.name, {})
		result = apply_customer(self.customer.name, {}, sync_addresses=True)
		self.assertIn("field_conflict:address", result["issues"])
		self.assertEqual(frappe.db.get_value("CRM Organization", organization, "address"), local.name)

	def test_first_address_opt_in_preserves_existing_crm_choice(self):
		organization = apply_customer(self.customer.name, {})["target"]
		address = self.make_address()
		frappe.db.set_value("CRM Organization", organization, "address", address.name)
		result = apply_customer(self.customer.name, {}, sync_addresses=True)
		self.assertIn("existing_organization_address_requires_review", result["issues"])

	def test_unverified_or_disabled_address_blocks_whole_customer(self):
		address = self.make_address(linked=False)
		self.customer.db_set("customer_primary_address", address.name)
		result = apply_customer(self.customer.name, {}, sync_addresses=True)
		self.assertEqual(result["status"], "Review")
		self.assertFalse(frappe.db.exists(LINK, {"source_name": self.customer.name}))
		address.append("links", {"link_doctype": "Customer", "link_name": self.customer.name})
		address.disabled = 1
		address.save()
		self.assertEqual(apply_customer(self.customer.name, {}, sync_addresses=True)["status"], "Review")

	def test_address_setting_permissions_and_customer_batch(self):
		from crm.migration.sync import configure_customer_addresses

		address = self.make_address()
		self.customer.db_set("customer_primary_address", address.name)
		configure_customer_addresses(enabled=True)
		configure_customers(enabled=True)
		result = sync_batch(frappe.get_single(SETTINGS))
		row = next(row for row in result["results"] if row["source"] == self.customer.name)
		self.assertEqual(frappe.db.get_value("CRM Organization", row["target"], "address"), address.name)
		for user in ("Guest", self.agent):
			frappe.set_user(user)
			with self.assertRaises(frappe.PermissionError):
				configure_customer_addresses(enabled=True)
		frappe.set_user("Administrator")
