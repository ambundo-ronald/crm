from datetime import timedelta

import frappe
from frappe.tests import IntegrationTestCase
from frappe.utils import now_datetime

from crm.api.appointments import own_event, rows
from crm.migration import appointments


class TestAppointmentSync(IntegrationTestCase):
	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		frappe.db.set_single_value("Appointment Booking Settings", "appointment_duration", 30)
		self.start = now_datetime() + timedelta(days=2)
		# Isolated fixture bypasses ERPNext email/assignment automation.
		self.source = frappe.get_doc(
			{
				"doctype": "Appointment",
				"name": "sync-test-" + frappe.generate_hash(length=10),
				"owner": "Administrator",
				"customer_name": "Sync Test",
				"customer_email": "sync@example.invalid",
				"scheduled_time": self.start,
				"status": "Open",
			}
		)
		self.source.db_insert()

	def tearDown(self):
		frappe.set_user("Administrator")
		super().tearDown()

	def visible(self):
		return rows("Administrator", self.start - timedelta(hours=1), self.start + timedelta(days=1))[0]

	def test_opt_in_and_idempotence(self):
		name = "erpnext-appointment:" + self.source.name
		self.assertNotIn(name, [r.name for r in self.visible()])
		appointments.sync([self.source.name])
		appointments.sync([self.source.name])
		self.assertEqual(frappe.db.count(appointments.LINK, {"appointment": self.source.name}), 1)
		row = next(r for r in self.visible() if r.name == name)
		self.assertTrue(row.read_only)
		self.assertEqual(row.status, "Open")
		appointments.unlink(self.source.name)
		self.assertNotIn(name, [r.name for r in self.visible()])
		self.assertTrue(frappe.db.exists("Appointment", self.source.name))

	def test_source_changes_and_deletion(self):
		appointments.sync([self.source.name])
		frappe.db.set_value("Appointment", self.source.name, "status", "Closed")
		row = next(r for r in self.visible() if r.name.endswith(self.source.name))
		self.assertEqual(row.status, "Closed")
		frappe.db.delete("Appointment", {"name": self.source.name})
		self.assertFalse(any(r.name.endswith(self.source.name) for r in self.visible()))

	def test_duplicate_event_and_write_protection(self):
		event = frappe.get_doc(
			{
				"doctype": "Event",
				"subject": "Existing appointment",
				"event_type": "Private",
				"starts_on": self.start,
				"ends_on": self.start + timedelta(minutes=30),
				"send_reminder": 0,
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value("Appointment", self.source.name, "calendar_event", event.name)
		appointments.sync([self.source.name])
		self.assertNotIn(event.name, [r.name for r in self.visible()])
		with self.assertRaises(frappe.PermissionError):
			own_event(event.name, write=True)

	def test_missing_lead_requires_review(self):
		frappe.db.set_value("Appointment", self.source.name, {"appointment_with": "Lead", "party": "missing"})
		with self.assertRaises(frappe.ValidationError):
			appointments.sync([self.source.name])
		self.assertFalse(frappe.db.exists(appointments.LINK, {"appointment": self.source.name}))

	def test_creator_scope_and_invalid_duration(self):
		appointments.sync([self.source.name])
		frappe.db.set_value("Appointment", self.source.name, "owner", "Guest")
		self.assertFalse(any(r.name.endswith(self.source.name) for r in self.visible()))
		frappe.db.set_value("Appointment", self.source.name, "owner", "Administrator")
		frappe.db.set_single_value("Appointment Booking Settings", "appointment_duration", 0)
		self.assertFalse(any(r.name.endswith(self.source.name) for r in self.visible()))

	def test_admin_only(self):
		frappe.set_user("Guest")
		for fn, args in ((appointments.preview, ()), (appointments.sync, ([self.source.name],))):
			with self.assertRaises(frappe.PermissionError):
				fn(*args)

	def test_agent_cannot_sync_or_see_other_creators(self):
		from crm.permissions.commission_agent import install_role

		install_role()
		email = "appointment-agent-" + frappe.generate_hash(length=8) + "@example.invalid"
		frappe.get_doc(
			{
				"doctype": "User",
				"email": email,
				"first_name": "Appointment Agent",
				"user_type": "Website User",
				"send_welcome_email": 0,
				"roles": [{"role": "Agent"}],
			}
		).insert(ignore_permissions=True)
		appointments.sync([self.source.name])
		frappe.set_user(email)
		with self.assertRaises(frappe.PermissionError):
			appointments.sync([self.source.name])
		visible, _, _ = appointments.calendar_rows(
			email, self.start - timedelta(hours=1), self.start + timedelta(hours=1)
		)
		self.assertEqual(visible, [])
		frappe.db.set_value("Appointment", self.source.name, "owner", email)
		visible, _, _ = appointments.calendar_rows(
			email, self.start - timedelta(hours=1), self.start + timedelta(hours=1)
		)
		self.assertEqual(len(visible), 1)
		self.assertTrue(visible[0]["read_only"])
		# A shared/assigned meeting must not grant the agent access to another creator's lead.
		frappe.set_user("Administrator")
		source_lead = frappe.get_doc({"doctype": "Lead", "first_name": "Appointment Source"}).insert()
		target = frappe.get_doc({"doctype": "CRM Lead", "first_name": "Other Creator"}).insert()
		frappe.get_doc(
			{
				"doctype": "CRM ERPNext Sync Link",
				"source_doctype": "Lead",
				"source_name": source_lead.name,
				"target_name": target.name,
				"source_snapshot": "{}",
				"target_snapshot": "{}",
			}
		).insert(ignore_permissions=True)
		frappe.db.set_value(
			"Appointment",
			self.source.name,
			{
				"appointment_with": "Lead",
				"party": source_lead.name,
			},
		)
		frappe.set_user(email)
		visible, _, _ = appointments.calendar_rows(
			email, self.start - timedelta(hours=1), self.start + timedelta(hours=1)
		)
		self.assertEqual(visible, [])
