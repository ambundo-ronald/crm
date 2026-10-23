"""Diagnostic safety tests runnable without a Frappe bench."""

import runpy
import sys
import unittest
from pathlib import Path
from types import ModuleType
from unittest.mock import Mock, patch


class TestInvitationDiagnostics(unittest.TestCase):
	def setUp(self):
		self.frappe = ModuleType("frappe")
		self.frappe.get_doc = Mock()
		self.frappe.logger = Mock()
		with patch.dict(sys.modules, {"frappe": self.frappe}):
			self.step = runpy.run_path(str(
				Path(__file__).parents[1] / "utils" / "invitation_diagnostics.py"
			))["invitation_step"]

	def test_failure_is_recorded_without_secrets_and_reraised(self):
		secret = "synthetic-invitation-key-and-password"
		error = PermissionError(secret)
		with self.assertRaises(PermissionError) as raised:
			with self.step("accept_and_create_account"):
				raise error
		self.assertIs(raised.exception, error)
		record = self.frappe.get_doc.call_args.args[0]
		self.assertEqual(set(record), {"doctype", "method", "error"})
		self.assertEqual(record["doctype"], "Error Log")
		self.assertIn("Stage: accept_and_create_account", record["error"])
		self.assertIn("Exception: PermissionError", record["error"])
		self.assertNotIn(secret, str(record))
		self.frappe.get_doc.return_value.deferred_insert.assert_called_once_with()
		logged = self.frappe.logger.return_value.error.call_args.args[0]
		self.assertNotIn(secret, logged)
		self.assertFalse(self.frappe.logger.call_args.kwargs["with_more_info"])

	def test_logging_failure_does_not_mask_original_error(self):
		self.frappe.get_doc.side_effect = RuntimeError("database unavailable")
		self.frappe.logger.side_effect = RuntimeError("logger unavailable")
		error = PermissionError("original failure")
		with self.assertRaises(PermissionError) as raised:
			with self.step("create_password_setup_link"):
				raise error
		self.assertIs(raised.exception, error)

	def test_success_does_not_log(self):
		with self.step("create_password_setup_link"):
			pass
		self.frappe.get_doc.assert_not_called()
		self.frappe.logger.assert_not_called()
