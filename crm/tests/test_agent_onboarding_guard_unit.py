"""Run without a bench: python -m unittest discover -s crm/tests -p '*guard_unit.py'.

Executes the real request guard with only its Frappe environment mocked. Full
password/key validation still needs the bench integration tests.
"""

import runpy
import sys
import unittest
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import patch


class TestAgentOnboardingGuard(unittest.TestCase):
	def setUp(self):
		self.frappe = ModuleType("frappe")
		self.frappe._ = lambda value: value
		self.frappe.session = SimpleNamespace(user="agent@example.invalid")
		self.frappe.get_roles = lambda user: ["Agent"]
		self.frappe.db = SimpleNamespace(get_value=lambda *args: True)
		self.frappe.local = SimpleNamespace(request=None)
		self.frappe.form_dict = {}
		self.frappe.PermissionError = PermissionError
		self.frappe.AuthenticationError = PermissionError
		self.frappe.throw = self.deny
		bridge = ModuleType("crm.api.agent_ui")
		bridge.CONTRACTS = set()
		bridge.override_name = lambda name: name.replace(".", "__")
		self.modules = patch.dict(sys.modules, {"frappe": self.frappe, "crm.api.agent_ui": bridge})
		self.modules.start()
		self.addCleanup(self.modules.stop)
		self.guard = runpy.run_path(str(Path(__file__).parents[1] / "permissions" / "commission_agent.py"))["restrict_request"]

	@staticmethod
	def deny(message, exception):
		raise exception(message)

	def request(self, path, method="GET", **form):
		self.frappe.local.request = SimpleNamespace(path=path, method=method)
		self.frappe.form_dict = form
		self.guard()

	def test_invitation_with_existing_agent_cookie(self):
		self.request("/api/method/crm.api.accept_invitation", key="synthetic-key")

	def test_password_page_and_submission(self):
		for method in ("GET", "HEAD"):
			self.request("/update-password", method)
		for endpoint in ("update_password", "test_password_strength"):
			self.request("/api/method/frappe.core.doctype.user.user." + endpoint, "POST")

	def test_legacy_form_command_dispatch(self):
		self.request("/", "POST", cmd="frappe.core.doctype.user.user.update_password")

	def test_other_business_paths_still_denied(self):
		for path in ("/app", "/desk", "/api/resource/User", "/api/method/frappe.client.delete", "/private/files/secret.pdf", "/update-password/other"):
			with self.subTest(path=path), self.assertRaises(PermissionError):
				self.request(path)

	def test_command_spoofing_still_denied(self):
		with self.assertRaises(PermissionError):
			self.request("/api/method/frappe.client.delete", "POST", cmd="crm.api.accept_invitation")
		with self.assertRaises(PermissionError):
			self.request("/update-password", "POST", cmd="frappe.client.delete")

	def test_suspended_agent_still_denied(self):
		self.frappe.db.get_value = lambda *args: False
		with self.assertRaises(PermissionError):
			self.request("/api/method/crm.api.accept_invitation")

	def test_guest_flow_unchanged(self):
		self.frappe.session.user = "Guest"
		self.request("/api/method/crm.api.accept_invitation")
