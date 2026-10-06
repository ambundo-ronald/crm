from unittest.mock import patch

import frappe
from frappe.core.doctype.user.user import User
from frappe.tests import IntegrationTestCase

from crm.api import agent
from crm.api import agent_admin as admin
from crm.permissions.commission_agent import ROLE, install_role, restrict_request


class TestAgentAdmin(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		install_role()
		self.email = "admin-test-" + frappe.generate_hash(length=10) + "@example.invalid"
		admin.create_agent(self.email, "Administration", "Test")

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.clear_cache(user=self.email)
		super().tearDown()

	def modified(self):
		return str(frappe.db.get_value("User", self.email, "modified"))

	def change(self, enabled, reason="Access review"):
		return admin.set_agent_enabled(self.email, enabled, reason, self.modified())

	def test_creation_and_projection(self):
		doc = frappe.get_doc("User", self.email)
		self.assertEqual(doc.user_type, "Website User")
		self.assertEqual({r.role for r in doc.roles}, {ROLE})
		self.assertFalse(doc.send_welcome_email)
		self.assertFalse(doc.reset_password_key)
		row = admin.list_agents(search=self.email)["agents"][0]
		self.assertEqual(row["issues"], [])
		self.assertNotIn("api_secret", row)
		self.assertNotIn("reset_password_key", row)
		with self.assertRaises(frappe.ValidationError):
			admin.create_agent("Administrator", "Staff")
		with self.assertRaises(frappe.ValidationError):
			admin.create_agent(self.email, "Duplicate")

	def test_administration_requires_admin(self):
		for user in ("Guest", self.email):
			frappe.set_user(user)
			for method, args in (
				(admin.list_agents, {}),
				(admin.create_agent, {"email": "blocked@example.invalid", "first_name": "Blocked"}),
				(admin.access_history, {"user": self.email}),
				(
					admin.set_agent_enabled,
					{"user": self.email, "enabled": False, "reason": "Test", "modified": self.modified()},
				),
			):
				with (
					self.subTest(user=user, method=method.__name__),
					self.assertRaises(frappe.PermissionError),
				):
					method(**args)
		frappe.set_user("Administrator")
		doc = frappe.get_doc("User", self.email)
		doc.append("roles", {"role": "System Manager"})
		doc.save(ignore_permissions=True)
		frappe.set_user(self.email)
		with self.assertRaises(frappe.PermissionError):
			admin.list_agents()

	def test_suspend_preserves_records_and_revokes_credentials(self):
		frappe.set_user(self.email)
		lead = agent.save_lead({"first_name": "Retained"})["name"]
		contact = agent.save_contact({"first_name": "Retained contact"}, lead=lead)["name"]
		frappe.set_user("Administrator")
		doc = frappe.get_doc("User", self.email)
		doc.api_key = "synthetic-key"
		doc.api_secret = "synthetic-secret"
		doc.reset_password_key = "synthetic-reset"
		doc.save(ignore_permissions=True)
		with patch("frappe.sessions.clear_sessions") as sessions:
			self.change(False)
			sessions.assert_any_call(user=self.email, force=True)
		doc.reload()
		self.assertFalse(doc.enabled)
		self.assertFalse(doc.api_key)
		self.assertFalse(doc.api_secret)
		self.assertFalse(doc.reset_password_key)
		self.assertEqual(frappe.db.get_value("CRM Lead", lead, "owner"), self.email)
		self.assertEqual(frappe.db.get_value("Contact", contact, "owner"), self.email)
		frappe.set_user(self.email)
		with self.assertRaises(frappe.PermissionError):
			agent.list_leads()
		with self.assertRaises(frappe.AuthenticationError):
			restrict_request()
		frappe.set_user("Administrator")
		self.change(True)
		doc.reload()
		self.assertTrue(doc.enabled)
		self.assertFalse(doc.api_key)
		frappe.set_user(self.email)
		self.assertIn(lead, [row.name for row in agent.list_leads()])

	def test_stale_blank_reason_and_unsafe_profile(self):
		with self.assertRaises(frappe.ValidationError):
			admin.set_agent_enabled(self.email, False, "Test", "stale")
		with self.assertRaises(frappe.ValidationError):
			self.change(False, " ")
		doc = frappe.get_doc("User", self.email)
		doc.append("roles", {"role": "Sales User"})
		doc.save(ignore_permissions=True)
		self.change(False)
		with self.assertRaises(frappe.ValidationError):
			self.change(True)
		self.assertFalse(frappe.db.get_value("User", self.email, "enabled"))

	def test_setup_invitation_never_returns_secret(self):
		with patch.dict(frappe.conf, {"mute_emails": 0}), patch.object(User, "password_reset_mail") as mail:
			result = admin.invite_agent(self.email, self.modified())
			mail.assert_called_once()
			self.assertEqual(result, {"status": "Invitation requested"})
			doc = frappe.get_doc("User", self.email)
			self.assertTrue(doc.reset_password_key)
			self.assertEqual(doc.redirect_url, "/crm")
			with self.assertRaises(frappe.ValidationError):
				admin.invite_agent(self.email, self.modified())
		self.change(False)
		with self.assertRaises(frappe.ValidationError):
			admin.invite_agent(self.email, self.modified())

	def test_muted_invitation_does_not_send(self):
		with patch.dict(frappe.conf, {"mute_emails": 1}), patch.object(User, "password_reset_mail") as mail:
			with self.assertRaises(frappe.ValidationError):
				admin.invite_agent(self.email, self.modified())
			mail.assert_not_called()
		self.assertFalse(frappe.db.get_value("User", self.email, "reset_password_key"))

	def test_audit_is_immutable_and_paginated_newest_first(self):
		self.change(False, "Contract paused")
		self.change(True, "Contract renewed")
		rows = admin.access_history(self.email)["rows"]
		self.assertEqual([row.action for row in rows], ["Reactivated", "Suspended", "Created"])
		self.assertEqual(rows[0].actor, "Administrator")
		self.assertEqual(rows[0].reason, "Contract renewed")
		doc = frappe.get_doc(admin.AUDIT, rows[0].name)
		doc.reason = "Tampered"
		with self.assertRaises(frappe.ValidationError):
			doc.save(ignore_permissions=True)
		with self.assertRaises(frappe.ValidationError):
			doc.delete(ignore_permissions=True)
		for i in range(52):
			admin.log(frappe.get_doc("User", self.email), "Created", str(i), 0)
		first = admin.access_history(self.email)
		second = admin.access_history(self.email, first["next_after"])
		self.assertEqual(len(first["rows"]), 50)
		self.assertEqual(len(second["rows"]), 5)
		self.assertFalse({r.name for r in first["rows"]} & {r.name for r in second["rows"]})
		with self.assertRaises(frappe.ValidationError):
			admin.access_history(self.email, "nonexistent")

	def test_oauth_tokens_remain_revoked_after_reactivation(self):
		token = frappe.get_doc(
			{
				"doctype": "OAuth Bearer Token",
				"expires_in": 3600,
				"user": self.email,
				"access_token": frappe.generate_hash(length=32),
				"refresh_token": frappe.generate_hash(length=32),
				"status": "Active",
			}
		).insert(ignore_permissions=True)
		other = frappe.get_doc(
			{
				"doctype": "OAuth Bearer Token",
				"expires_in": 3600,
				"user": "Administrator",
				"access_token": frappe.generate_hash(length=32),
				"status": "Active",
			}
		).insert(ignore_permissions=True)
		code = frappe.get_doc(
			{
				"doctype": "OAuth Authorization Code",
				"user": self.email,
				"authorization_code": frappe.generate_hash(length=32),
				"validity": "Valid",
			}
		).insert(ignore_permissions=True)
		self.change(False)
		self.assertEqual(frappe.db.get_value(token.doctype, token.name, "status"), "Revoked")
		self.assertFalse(frappe.db.exists(code.doctype, code.name))
		self.change(True)
		self.assertEqual(frappe.db.get_value(token.doctype, token.name, "status"), "Revoked")
		self.assertEqual(frappe.db.get_value(other.doctype, other.name, "status"), "Active")
