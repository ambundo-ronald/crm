"""Security regression tests for agents using the native CRM contracts."""

from unittest.mock import patch

import frappe

from crm.api import agent, agent_ui, invite_by_email
from crm.tests import test_commission_agent


class TestAgentUI(test_commission_agent.TestCommissionAgent):
	def test_native_lists_and_counts_cannot_override_ownership(self):
		data = agent_ui.dispatch("crm.api.doc.get_data", {"doctype": "CRM Lead"})
		self.assertIn(self.a_lead, [r.name for r in data["data"]])
		self.assertNotIn(self.b_lead, [r.name for r in data["data"]])
		foreign = agent_ui.dispatch(
			"crm.api.doc.get_data", {"doctype": "CRM Lead", "filters": {"owner": self.b}}
		)
		self.assertEqual(foreign["total_count"], 0)
		self.assertEqual(foreign["data"], [])
		with self.assertRaises(frappe.PermissionError):
			agent_ui.dispatch(
				"crm.api.doc.get_data",
				{"doctype": "CRM Lead", "order_by": "(select password from tabUser) desc"},
			)

	def test_native_get_and_mutations_reject_foreign_documents(self):
		for dt in ("User", "Customer", "CRM Deal", "CRM Organization", "File"):
			with self.subTest(doctype=dt), self.assertRaises(frappe.PermissionError):
				agent_ui.dispatch("frappe.client.get", {"doctype": dt, "name": self.b})
		for method, params in (
			("frappe.client.get", {"doctype": "CRM Lead", "name": self.b_lead}),
			(
				"frappe.client.set_value",
				{"doctype": "CRM Lead", "name": self.b_lead, "fieldname": "first_name", "value": "forged"},
			),
			("crm.api.activities.get_activities", {"name": self.b_lead}),
		):
			with self.subTest(method=method), self.assertRaises(frappe.PermissionError):
				agent_ui.dispatch(method, params)

	def test_native_save_only_changes_projected_editable_fields(self):
		doc = agent_ui.dispatch("frappe.client.get", {"doctype": "CRM Lead", "name": self.a_lead})
		doc["first_name"] = "Native update"
		result = agent_ui.dispatch("frappe.client.save", {"doc": doc})
		self.assertEqual(result["first_name"], "Native update")
		self.assertEqual(frappe.db.get_value("CRM Lead", self.a_lead, "owner"), self.a)
		for field in ("owner", "lead_owner", "custom_secret", "converted"):
			with self.subTest(field=field), self.assertRaises(frappe.PermissionError):
				agent_ui.dispatch(
					"frappe.client.set_value",
					{"doctype": "CRM Lead", "name": self.a_lead, "fieldname": field, "value": self.b},
				)

	def test_linked_shared_contact_is_read_only_and_links_are_private(self):
		frappe.set_user("Administrator")
		contact = frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": "Shared native",
				"links": [
					{"link_doctype": "CRM Lead", "link_name": self.a_lead},
					{"link_doctype": "CRM Lead", "link_name": self.b_lead},
				],
			}
		).insert(ignore_permissions=True)
		frappe.set_user(self.a)
		doc = agent_ui.dispatch("frappe.client.get", {"doctype": "Contact", "name": contact.name})
		self.assertTrue(doc["__agent_read_only"])
		self.assertNotIn("links", doc)
		with self.assertRaises(frappe.PermissionError):
			agent_ui.dispatch(
				"frappe.client.set_value",
				{"doctype": "Contact", "name": contact.name, "fieldname": "first_name", "value": "changed"},
			)

	def test_native_tasks_validate_lead_and_owner(self):
		values = {
			"doctype": "CRM Task",
			"title": "Native follow-up",
			"reference_doctype": "CRM Lead",
			"reference_docname": self.a_lead,
			"status": "Todo",
			"priority": "Low",
		}
		task = agent_ui.dispatch("frappe.client.insert", {"doc": values})
		self.assertEqual(frappe.db.get_value("CRM Task", task["name"], "owner"), self.a)
		values["reference_docname"] = self.b_lead
		with self.assertRaises(frappe.PermissionError):
			agent_ui.dispatch("frappe.client.insert", {"doc": values})
		frappe.set_user(self.b)
		with self.assertRaises(frappe.PermissionError):
			agent_ui.dispatch("frappe.client.get", {"doctype": "CRM Task", "name": task["name"]})

	def test_users_metadata_and_scripts_are_projected(self):
		users, crm_users = agent_ui.dispatch("crm.api.session.get_users", {"include_all": True})
		self.assertEqual([u.name for u in users], [self.a])
		self.assertEqual(crm_users[0].role, "Agent")
		self.assertEqual(
			agent_ui.dispatch("frappe.client.get_list", {"doctype": "CRM Form Script", "fields": ["*"]}), []
		)
		self.assertNotIn("lead_owner", [f["fieldname"] for f in agent_ui.fields("CRM Lead")])
		with self.assertRaises(frappe.PermissionError):
			agent_ui.fields("User")

	def test_invited_agent_is_restricted_website_user(self):
		frappe.set_user("Administrator")
		email = "native-invite-" + frappe.generate_hash(length=8) + "@example.invalid"
		with patch("crm.fcrm.doctype.crm_invitation.crm_invitation.CRMInvitation.invite_via_email"):
			result = invite_by_email(email, "Agent")
		self.assertEqual(result["to_invite"], [email])
		invitation = frappe.get_doc("CRM Invitation", {"email": email})
		frappe.set_user("Guest")
		self.assertTrue(invitation.accept())
		user = frappe.get_doc("User", email)
		self.assertEqual(user.user_type, "Website User")
		self.assertEqual({r.role for r in user.roles}, {"Agent"})
		self.assertIsNone(invitation.key)
		with self.assertRaises(frappe.ValidationError):
			invitation.accept()

	def test_agent_invitation_never_converts_existing_staff(self):
		frappe.set_user("Administrator")
		invitation = frappe.get_doc(
			{"doctype": "CRM Invitation", "email": self.staff, "role": "Agent", "status": "Pending"}
		)
		with self.assertRaises(frappe.PermissionError):
			invitation.accept()
		self.assertNotIn("Agent", frappe.get_roles(self.staff))

	def test_staff_invitation_roles_remain_unchanged(self):
		frappe.set_user("Administrator")
		for role in ("Sales User", "Sales Manager"):
			email = "native-staff-" + frappe.generate_hash(length=8) + "@example.invalid"
			with patch("crm.fcrm.doctype.crm_invitation.crm_invitation.CRMInvitation.invite_via_email"):
				invite_by_email(email, role)
			invitation = frappe.get_doc("CRM Invitation", {"email": email})
			self.assertTrue(invitation.accept())
			user = frappe.get_doc("User", email)
			self.assertEqual(user.user_type, "System User")
			self.assertIn(role, {r.role for r in user.roles})
			self.assertNotIn("Agent", {r.role for r in user.roles})

	def test_legacy_role_migration_preserves_records(self):
		from crm.permissions.commission_agent import LEGACY_ROLE, install_role

		frappe.set_user("Administrator")
		if not frappe.db.exists("Role", LEGACY_ROLE):
			frappe.get_doc({"doctype": "Role", "role_name": LEGACY_ROLE, "desk_access": 0}).insert(
				ignore_permissions=True
			)
		user = frappe.get_doc("User", self.a)
		user.set("roles", [{"role": LEGACY_ROLE}])
		user.save(ignore_permissions=True)
		install_role()
		user.reload()
		self.assertIn("Agent", {r.role for r in user.roles})
		self.assertNotIn(LEGACY_ROLE, {r.role for r in user.roles})
		self.assertEqual(user.redirect_url, "/crm")
		frappe.set_user(self.a)
		self.assertEqual(agent_ui.document("CRM Lead", self.a_lead).owner, self.a)

	def test_additive_staff_roles_and_suspension_do_not_bypass_scope(self):
		frappe.set_user("Administrator")
		user = frappe.get_doc("User", self.a)
		user.append_roles("System Manager")
		user.save(ignore_permissions=True)
		frappe.set_user(self.a)
		self.assertEqual(agent_ui.self_user().role, "Agent")
		with self.assertRaises(frappe.PermissionError):
			agent_ui.document("CRM Lead", self.b_lead)
		frappe.db.set_value("User", self.a, "enabled", 0)
		with self.assertRaises(frappe.PermissionError):
			agent_ui.dispatch("crm.api.session.get_users", {})

	def test_replaced_native_handler_fails_closed(self):
		from crm.permissions.commission_agent import restrict_request

		with (
			patch.object(
				frappe.local,
				"request",
				frappe._dict(path="/api/method/frappe.client.get", method="GET"),
				create=True,
			),
			patch.object(frappe, "form_dict", frappe._dict()),
			patch.object(frappe, "override_whitelisted_method", return_value="unsafe.app.get"),
		):
			with self.assertRaises(frappe.PermissionError):
				restrict_request()
