from datetime import datetime
from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from crm.api import productivity
from crm.permissions.commission_agent import install_role


class TestProductivity(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		frappe.set_user("Administrator")
		install_role()
		cls.a = "productivity.agent.a@example.invalid"
		cls.b = "productivity.agent.b@example.invalid"
		cls.staff = "productivity.staff@example.invalid"
		for email in (cls.a, cls.b, cls.staff):
			if not frappe.db.exists("User", email):
				frappe.get_doc(
					{
						"doctype": "User",
						"email": email,
						"first_name": "Productivity",
						"user_type": "System User" if email == cls.staff else "Website User",
						"send_welcome_email": 0,
						"roles": [{"role": "Sales User" if email == cls.staff else "Agent"}],
					}
				).insert(ignore_permissions=True)
		frappe.db.commit()

	def setUp(self):
		super().setUp()
		frappe.set_user("Administrator")
		self.lead_a = self.lead(self.a)
		self.lead_b = self.lead(self.b)
		self.clock = patch("crm.api.productivity.now_datetime", return_value=datetime(2035, 6, 12, 12))
		self.clock.start()

	def tearDown(self):
		self.clock.stop()
		frappe.set_user("Administrator")
		frappe.db.rollback()
		for user in (self.a, self.b, self.staff):
			frappe.clear_cache(user=user)
		super().tearDown()

	def insert_as(self, values):
		previous = frappe.session.user
		frappe.set_user(values["owner"])
		try:
			return frappe.get_doc(values).insert(ignore_permissions=True)
		finally:
			frappe.set_user(previous)

	def lead(self, owner):
		return self.insert_as(
			{
				"doctype": "CRM Lead",
				"first_name": "Daily lead",
				"status": "New",
				"owner": owner,
				"lead_owner": owner if owner == self.staff else None,
			}
		).name

	def task(self, owner=None, lead=None, due="2035-06-12 14:00:00", **values):
		return self.insert_as(
			{
				"doctype": "CRM Task",
				"title": "Daily task",
				"owner": owner or self.a,
				"status": "Todo",
				"due_date": due,
				"reference_doctype": "CRM Lead",
				"reference_docname": lead or self.lead_a,
				**values,
			}
		)

	def daily(self, user=None):
		frappe.set_user(user or self.a)
		return productivity.my_day()

	def test_date_boundaries_and_open_statuses(self):
		overdue = self.task(due="2035-06-11 23:59:59")
		today = self.task(due="2035-06-12 00:00:00")
		earlier = self.task(due="2035-06-12 09:00:00")
		upcoming = self.task(due="2035-06-13 00:00:00")
		undated = self.task(due=None)
		self.task(due="2035-06-20 00:00:00")
		self.task(status="Done")
		self.task(status="Canceled")
		data = self.daily()
		self.assertEqual(data["date"], "2035-06-12")
		expected = {
			"overdue": {overdue.name},
			"today": {today.name, earlier.name},
			"upcoming": {upcoming.name},
			"undated": {undated.name},
		}
		for key, names in expected.items():
			self.assertEqual({r["name"] for r in data["tasks"][key]["items"]}, names)

	def test_agents_cannot_gain_tasks_from_assignment_or_links(self):
		own = self.task()
		hidden_link = self.task(lead=self.lead_b)
		others = self.task(owner=self.b)
		frappe.db.set_value("CRM Task", others.name, "assigned_to", self.a)
		unlinked = self.task(reference_doctype=None, reference_docname=None)
		data = self.daily()
		self.assertEqual([r["name"] for r in data["tasks"]["today"]["items"]], [own.name])
		self.assertEqual([r["name"] for r in data["new_leads"]["items"]], [self.lead_a])
		for task in (hidden_link, others, unlinked):
			with self.assertRaises(frappe.PermissionError):
				productivity.complete_task(str(task.name), str(task.modified))

	def test_staff_personal_assignment_and_document_permissions(self):
		owned = self.task(owner=self.staff, reference_doctype=None, reference_docname=None)
		assigned = self.task(
			owner="Administrator", assigned_to=self.staff, reference_doctype=None, reference_docname=None
		)
		self.task(
			owner=self.staff, assigned_to="Administrator", reference_doctype=None, reference_docname=None
		)
		data = self.daily(self.staff)
		self.assertEqual({r["name"] for r in data["tasks"]["today"]["items"]}, {owned.name, assigned.name})
		with patch("frappe.model.document.Document.check_permission", side_effect=frappe.PermissionError):
			self.assertEqual(productivity.my_day()["tasks"]["today"]["items"], [])
			with self.assertRaises(frappe.PermissionError):
				productivity.complete_task(str(owned.name), str(owned.modified))

	def test_task_link_permission_is_required_for_staff(self):
		task = self.task(owner=self.staff)
		original = frappe.model.document.Document.check_permission

		def check(doc, *args, **kwargs):
			if doc.doctype == "CRM Lead":
				raise frappe.PermissionError
			return original(doc, *args, **kwargs)

		frappe.set_user(self.staff)
		with patch("frappe.model.document.Document.check_permission", check):
			self.assertEqual(productivity.my_day()["tasks"]["today"]["items"], [])
			with self.assertRaises(frappe.PermissionError):
				productivity.complete_task(str(task.name), str(task.modified))

	def test_completion_and_stale_edits(self):
		task = self.task()
		frappe.set_user(self.a)
		with self.assertRaises(frappe.ValidationError):
			productivity.complete_task(str(task.name), "stale")
		self.assertEqual(productivity.complete_task(str(task.name), str(task.modified))["status"], "Done")
		self.assertEqual(productivity.my_day()["tasks"]["today"]["items"], [])
		self.assertEqual(frappe.db.get_value("CRM Task", task.name, "owner"), self.a)

	def test_completion_rechecks_reassignment_and_cancelled_status(self):
		task = self.task(owner=self.staff, reference_doctype=None, reference_docname=None)
		frappe.db.set_value("CRM Task", task.name, "assigned_to", "Administrator")
		frappe.set_user(self.staff)
		with self.assertRaises(frappe.PermissionError):
			productivity.complete_task(str(task.name), str(task.modified))
		frappe.set_user("Administrator")
		cancelled = self.task(status="Canceled")
		frappe.set_user(self.a)
		with self.assertRaises(frappe.ValidationError):
			productivity.complete_task(str(cancelled.name), str(cancelled.modified))

	def test_today_appointments_are_personal_open_and_overlap_day(self):
		def event(owner, start, end, **kwargs):
			return self.insert_as(
				{
					"doctype": "Event",
					"owner": owner,
					"subject": "Daily meeting",
					"starts_on": start,
					"ends_on": end,
					"event_type": "Private",
					"status": "Open",
					"send_reminder": 0,
					**kwargs,
				}
			).name

		overnight = event(self.a, "2035-06-11 23:00:00", "2035-06-12 01:00:00")
		event(self.b, "2035-06-12 10:00:00", "2035-06-12 11:00:00")
		event(self.a, "2035-06-12 10:00:00", "2035-06-12 11:00:00", status="Completed")
		event(
			self.a,
			"2035-06-12 10:00:00",
			"2035-06-12 11:00:00",
			reference_doctype="CRM Lead",
			reference_docname=self.lead_b,
		)
		event(self.a, "2035-06-13 00:00:00", "2035-06-13 01:00:00")
		self.assertEqual([r.name for r in self.daily()["appointments"]["items"]], [overnight])

	def test_guests_and_disabled_agents_denied(self):
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			productivity.my_day()
		frappe.set_user("Administrator")
		frappe.db.set_value("User", self.a, "enabled", 0)
		frappe.set_user(self.a)
		with self.assertRaises(frappe.PermissionError):
			productivity.my_day()

	def test_lists_are_bounded_and_projected(self):
		for _ in range(4):
			self.task(description="Internal task detail")
		with patch("crm.api.productivity.LIMIT", 2):
			group = self.daily()["tasks"]["today"]
		self.assertEqual(len(group["items"]), 2)
		self.assertTrue(group["truncated"])
		self.assertNotIn("description", group["items"][0])
		self.assertNotIn("owner", group["items"][0])
