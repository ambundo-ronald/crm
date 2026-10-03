import json
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from crm.migration.opportunity import DEFAULT_STATUSES, LINK, apply_opportunity
from crm.migration.sync import SETTINGS, configure_opportunities, initialize, run_batch


class TestOpportunitySync(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		initialize()
		frappe.db.set_single_value(
			SETTINGS,
			{
				"enabled": 1,
				"automatic": 0,
				"sync_opportunities": 0,
				"cursor": "",
				"opportunity_cursor": "",
				"status_map": "{}",
				"user_map": "{}",
				"opportunity_status_map": "{}",
			},
		)
		self.company = frappe.get_all("Company", fields=["name", "default_currency"], limit_page_length=1)[0]
		frappe.db.set_single_value(
			"FCRM Settings", {"currency": self.company.default_currency, "enable_forecasting": 0}
		)
		frappe.db.set_single_value("ERPNext CRM Settings", "enabled", 0)
		self.lead = frappe.get_doc(
			{
				"doctype": "Lead",
				"first_name": "Opportunity Sync",
				"status": "Lead",
				"lead_owner": "Administrator",
				"email_id": "opportunity-" + frappe.generate_hash(length=12) + "@example.invalid",
			}
		).insert()
		self.source = self.opportunity()
		result = run_batch()
		self.crm_lead = next(row["target"] for row in result["results"] if row["source"] == self.lead.name)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		super().tearDown()

	def opportunity(self):
		return frappe.get_doc(
			{
				"doctype": "Opportunity",
				"opportunity_from": "Lead",
				"party_name": self.lead.name,
				"company": self.company.name,
				"currency": self.company.default_currency,
				"opportunity_amount": 1200,
				"expected_closing": "2030-06-30",
				"opportunity_owner": "Administrator",
				"status": "Open",
			}
		).insert()

	def apply(self):
		return apply_opportunity(self.source.name, DEFAULT_STATUSES, {})

	def test_create_rerun_and_update_without_source_or_lead_changes(self):
		self.source.reload()
		before = self.source.modified
		lead_status = frappe.db.get_value("CRM Lead", self.crm_lead, "status")
		created = self.apply()
		self.assertEqual(created["status"], "Created", created)
		self.assertEqual(self.apply()["status"], "Unchanged")
		self.assertEqual(frappe.db.count(LINK, {"source_name": self.source.name}), 1)
		target = frappe.get_doc("CRM Deal", created["target"])
		self.assertEqual(target.lead, self.crm_lead)
		self.assertEqual(target.deal_value, 1200)
		self.assertEqual(target.currency, self.source.currency)
		self.assertEqual(target.exchange_rate, 1)
		self.assertFalse(target.contacts)
		self.assertFalse(frappe.db.get_value("CRM Lead", self.crm_lead, "converted"))
		self.assertEqual(frappe.db.get_value("CRM Lead", self.crm_lead, "status"), lead_status)
		self.assertEqual(str(frappe.db.get_value("Opportunity", self.source.name, "modified")), str(before))
		self.source.opportunity_amount = 1800
		self.source.expected_closing = None
		self.source.save()
		self.assertEqual(self.apply()["status"], "Updated")
		target.reload()
		self.assertEqual(target.deal_value, 1800)
		self.assertFalse(target.expected_closure_date)

	def test_conflict_protects_entire_record_and_crm_stage(self):
		target = frappe.get_doc("CRM Deal", self.apply()["target"])
		target.deal_value = 1500
		target.status = "Negotiation"
		target.next_step = "Call next week"
		target.save()
		self.assertEqual(self.apply()["status"], "Unchanged")
		self.source.opportunity_amount = 1600
		self.source.expected_closing = "2030-07-31"
		self.source.save()
		self.assertIn("field_conflict:deal_value", self.apply()["issues"])
		target.reload()
		self.assertEqual(str(target.expected_closure_date), "2030-06-30")
		self.assertEqual(target.deal_value, 1500)
		self.assertEqual(target.status, "Negotiation")
		self.assertEqual(target.next_step, "Call next week")
		target.deal_value = 1600
		target.save()
		self.assertEqual(self.apply()["status"], "Updated")

	def test_multiple_opportunities_keep_distinct_source_identities(self):
		first = self.apply()
		second = self.opportunity()
		result = apply_opportunity(second.name, DEFAULT_STATUSES, {})
		self.assertEqual(result["status"], "Created", result)
		self.assertNotEqual(first["target"], result["target"])

	def test_existing_manual_deal_is_not_adopted(self):
		manual = frappe.get_doc(
			{
				"doctype": "CRM Deal",
				"lead": self.crm_lead,
				"status": "Qualification",
				"deal_owner": "Administrator",
				"currency": self.company.default_currency,
			}
		).insert()
		self.assertIn("existing_deal_requires_review", self.apply()["issues"])
		self.assertFalse(frappe.db.exists(LINK, {"target_name": manual.name}))

	def test_unsupported_source_states_and_foreign_currency(self):
		for field, value, issue in [
			("status", "Converted", "opportunity_lifecycle_requires_review"),
			("opportunity_from", "Customer", "customer_or_prospect_mapping_required"),
			("currency", "ZZZ", "currency_conversion_requires_review"),
			("opportunity_owner", None, "opportunity_salesperson_requires_review"),
		]:
			original = self.source.get(field)
			frappe.db.set_value("Opportunity", self.source.name, field, value)
			self.assertIn(issue, self.apply()["issues"])
			frappe.db.set_value("Opportunity", self.source.name, field, original)
		frappe.db.set_value("Lead", self.lead.name, "unsubscribed", 1)
		self.assertIn("source_lead_contact_consent_requires_review", self.apply()["issues"])

	def test_relationship_change_and_terminal_deal_are_held(self):
		target = frappe.get_doc("CRM Deal", self.apply()["target"])
		frappe.db.set_value("CRM Deal", target.name, "lead", None)
		self.assertIn("opportunity_relationship_or_creator_changed", self.apply()["issues"])
		frappe.db.set_value("CRM Deal", target.name, {"lead": self.crm_lead, "status": "Won"})
		self.assertIn("deal_lifecycle_requires_review", self.apply()["issues"])

	def test_outbound_customer_creation_is_blocked(self):
		count = frappe.db.count("Customer")
		frappe.db.set_single_value(
			"ERPNext CRM Settings",
			{"enabled": 1, "create_customer_on_status_change": 1, "deal_status": "Qualification"},
		)
		self.assertIn("outbound_customer_automation_requires_review", self.apply()["issues"])
		self.assertEqual(frappe.db.count("Customer"), count)

	def test_opt_in_batch_logging_and_failure_rollback(self):
		self.assertFalse(frappe.db.exists(LINK, {"source_name": self.source.name}))
		configure_opportunities(enabled=True)
		from crm.fcrm.doctype.crm_erpnext_opportunity_link.crm_erpnext_opportunity_link import (
			CRMERPNextOpportunityLink,
		)

		with patch.object(
			CRMERPNextOpportunityLink,
			"before_insert",
			create=True,
			side_effect=ValueError("Synthetic mapping failure"),
		):
			result = run_batch()
			row = next(row for row in result["results"] if row["source"] == self.source.name)
			self.assertEqual(row["status"], "Failed")
		self.assertFalse(frappe.db.exists("CRM Deal", {"lead": self.crm_lead}))
		self.assertFalse(frappe.db.exists(LINK, {"source_name": self.source.name}))
		result = run_batch()
		row = next(row for row in result["results"] if row["source"] == self.source.name)
		self.assertEqual(row["status"], "Created", row)
		self.assertEqual(row["target_doctype"], "CRM Deal")
		self.assertEqual(row["source_doctype"], "Opportunity")

	def test_status_mapping_and_configuration_permissions(self):
		result = apply_opportunity(self.source.name, {"Open": "Won"}, {})
		self.assertIn("opportunity_status_mapping_requires_review", result["issues"])
		with self.assertRaises(frappe.ValidationError):
			frappe.get_single(SETTINGS).update({"opportunity_status_map": json.dumps({"Open": 4})}).save()
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			configure_opportunities(enabled=True)
		with self.assertRaises(frappe.PermissionError):
			self.apply()

	def test_products_missing_lead_mapping_and_agent_creator(self):
		from crm.migration.sync import LINK as LEAD_LINK

		frappe.get_doc(
			{
				"doctype": "Opportunity Item",
				"parent": self.source.name,
				"parenttype": "Opportunity",
				"parentfield": "items",
				"idx": 1,
				"item_code": "Synthetic item",
				"qty": 1,
			}
		).db_insert()
		self.assertIn("opportunity_products_require_mapping", self.apply()["issues"])
		frappe.db.delete("Opportunity Item", {"parent": self.source.name})
		lead_link = frappe.get_doc(LEAD_LINK, {"source_name": self.lead.name})
		lead_link.db_set("target_name", "missing-local-fixture")
		self.assertIn("sync_source_lead_first", self.apply()["issues"])
		lead_link.db_set("target_name", self.crm_lead)
		email = "opportunity.agent." + frappe.generate_hash(length=10) + "@example.invalid"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Opportunity Agent",
				"enabled": 1,
				"user_type": "Website User",
				"send_welcome_email": 0,
				"roles": [{"role": "Commission Agent"}],
			}
		).insert()
		self.source.db_set("owner", email)
		result = self.apply()
		self.assertEqual(result["status"], "Created", result)
		self.assertEqual(frappe.db.get_value("CRM Deal", result["target"], "owner"), email)
		self.assertEqual(frappe.session.user, "Administrator")
		frappe.set_user(email)
		with self.assertRaises(frappe.PermissionError):
			configure_opportunities(enabled=True)
		frappe.set_user("Administrator")
		frappe.clear_cache(user=email)

	def test_opportunity_cursor_is_independent_and_persisted(self):
		from crm.migration.opportunity import sync_batch

		settings = frappe.get_single(SETTINGS)
		settings.opportunity_cursor = self.source.name
		self.assertFalse(any(row["source"] == self.source.name for row in sync_batch(settings)["results"]))
		frappe.db.set_single_value(SETTINGS, "opportunity_cursor", self.source.name)
		stale_settings = frappe.get_single(SETTINGS)
		stale_settings.opportunity_cursor = "client-cannot-overwrite"
		stale_settings.save()
		self.assertEqual(frappe.db.get_single_value(SETTINGS, "opportunity_cursor"), self.source.name)
