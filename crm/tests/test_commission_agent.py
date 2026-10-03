from unittest.mock import patch

import frappe
from frappe.tests import IntegrationTestCase

from crm.api import agent
from crm.permissions.commission_agent import install_role, restrict_request


class TestCommissionAgent(IntegrationTestCase):
	@classmethod
	def setUpClass(cls):
		super().setUpClass()
		install_role()
		cls.a = "permission.agent.a@example.invalid"
		cls.b = "permission.agent.b@example.invalid"
		for email in (cls.a, cls.b):
			if not frappe.db.exists("User", email):
				frappe.get_doc(
					{
						"doctype": "User",
						"email": email,
						"first_name": "Agent",
						"user_type": "Website User",
						"send_welcome_email": 0,
						"roles": [{"role": "Commission Agent"}],
					}
				).insert(ignore_permissions=True)
		cls.staff = "permission.sales@example.invalid"
		if not frappe.db.exists("User", cls.staff):
			frappe.get_doc(
				{
					"doctype": "User",
					"email": cls.staff,
					"first_name": "Calendar Sales",
					"user_type": "System User",
					"send_welcome_email": 0,
					"roles": [{"role": "Sales User"}],
				}
			).insert(ignore_permissions=True)
		frappe.db.commit()

	def setUp(self):
		super().setUp()
		frappe.set_user(self.a)
		self.a_lead = agent.save_lead({"first_name": "Agent A"})["name"]
		frappe.set_user(self.b)
		self.b_lead = agent.save_lead({"first_name": "Agent B"})["name"]
		frappe.set_user(self.a)

	def tearDown(self):
		frappe.set_user("Administrator")
		frappe.db.rollback()
		frappe.clear_cache(user=self.a)
		frappe.clear_cache(user=self.b)
		super().tearDown()

	def test_creator_scope_ignores_assignment(self):
		frappe.db.set_value("CRM Lead", self.b_lead, "lead_owner", self.a)
		names = [row.name for row in agent.list_leads()]
		self.assertIn(self.a_lead, names)
		self.assertNotIn(self.b_lead, names)
		with self.assertRaises(frappe.PermissionError):
			agent.get_lead(self.b_lead)
		with self.assertRaises(frappe.PermissionError):
			agent.save_lead({"first_name": "Forged"}, self.b_lead)

	def test_forged_fields_and_converted_leads(self):
		for field in ("owner", "lead_owner", "converted", "doctype", "products"):
			with self.subTest(field=field), self.assertRaises(frappe.ValidationError):
				agent.save_lead({field: self.b})
		agent.save_lead({"status": "Contacted"}, self.a_lead)
		frappe.db.set_value("CRM Lead", self.a_lead, "converted", 1)
		with self.assertRaises(frappe.PermissionError):
			agent.save_lead({"first_name": "Changed"}, self.a_lead)

	def test_contact_scope_and_link_forgery(self):
		own = agent.save_contact({"first_name": "Own"}, lead=self.a_lead)
		with self.assertRaises(frappe.PermissionError):
			agent.save_contact({"first_name": "Forged"}, lead=self.b_lead)
		frappe.set_user("Administrator")
		shared = frappe.get_doc(
			{
				"doctype": "Contact",
				"first_name": "Shared",
				"links": [
					{"link_doctype": "CRM Lead", "link_name": self.a_lead},
					{"link_doctype": "CRM Lead", "link_name": self.b_lead},
				],
			}
		).insert(ignore_permissions=True)
		hidden = frappe.get_doc({"doctype": "Contact", "first_name": "Hidden"}).insert(
			ignore_permissions=True
		)
		frappe.set_user(self.a)
		rows = {row.name: row for row in agent.list_contacts()}
		self.assertIn(own["name"], rows)
		self.assertIn(shared.name, rows)
		self.assertNotIn(hidden.name, rows)
		self.assertNotIn("links", rows[shared.name])
		with self.assertRaises(frappe.PermissionError):
			agent.save_contact({"first_name": "Changed"}, name=shared.name)

	def test_follow_up_scope(self):
		task = agent.add_follow_up(self.a_lead, "Call client")
		self.assertEqual(agent.complete_follow_up(task["name"])["status"], "Done")
		with self.assertRaises(frappe.PermissionError):
			agent.add_follow_up(self.b_lead, "Intrusion")
		frappe.set_user(self.b)
		with self.assertRaises(frappe.PermissionError):
			agent.complete_follow_up(task["name"])

	def test_request_boundary(self):
		paths = [
			"/api/resource/Customer",
			"/api/v2/document/CRM Lead",
			"/private/files/a.pdf",
			"/printview",
			"/api/method/crm.api.contact.get_linked_deals",
			"/api/method/frappe.realtime.get_user_info",
		]
		for path in paths:
			request = frappe._dict(path=path, method="GET")
			with (
				patch.object(frappe.local, "request", request, create=True),
				patch.object(frappe, "form_dict", frappe._dict()),
			):
				with self.assertRaises(frappe.PermissionError):
					restrict_request()
		request = frappe._dict(path="/api/method/crm.api.agent.list_leads", method="GET")
		with (
			patch.object(frappe.local, "request", request, create=True),
			patch.object(frappe, "form_dict", frappe._dict(cmd="frappe.client.get_list")),
		):
			with self.assertRaises(frappe.PermissionError):
				restrict_request()

	def test_staff_boundary_unchanged(self):
		frappe.set_user("Administrator")
		restrict_request()
		with self.assertRaises(frappe.PermissionError):
			agent.list_leads()

	def test_malformed_record_identifiers(self):
		for value in ({"owner": self.b}, ["like", "%"], True):
			with self.subTest(value=value), self.assertRaises(frappe.PermissionError):
				agent.get_lead(value)

	def test_role_revocation(self):
		frappe.set_user("Administrator")
		user = frappe.get_doc("User", self.a)
		user.remove_roles("Commission Agent")
		frappe.clear_cache(user=self.a)
		frappe.set_user(self.a)
		with self.assertRaises(frappe.PermissionError):
			agent.list_leads()

	def test_own_contact_shared_with_another_lead_is_read_only(self):
		contact = agent.save_contact({"first_name": "Own shared contact"}, lead=self.a_lead)
		frappe.set_user("Administrator")
		doc = frappe.get_doc("Contact", contact["name"])
		doc.append("links", {"link_doctype": "CRM Lead", "link_name": self.b_lead})
		doc.save(ignore_permissions=True)
		frappe.set_user(self.a)
		with self.assertRaises(frappe.PermissionError):
			agent.save_contact({"first_name": "Changed"}, name=doc.name)

	def appointment(self, lead=None, **changes):
		values = {
			"subject": "Client meeting",
			"starts_on": "2035-06-12T10:00:00",
			"ends_on": "2035-06-12T11:00:00",
			"location": "Office",
		}
		values.update(changes)
		return agent.save_appointment(lead or self.a_lead, values)

	def test_appointment_lifecycle_and_isolation(self):
		created = self.appointment()["appointment"]
		rows = agent.list_appointments("2035-06-12T00:00:00", "2035-06-13T00:00:00")
		self.assertEqual([row.name for row in rows["appointments"]], [created["name"]])
		self.assertNotIn("owner", rows["appointments"][0])
		with self.assertRaises(frappe.PermissionError):
			self.appointment(self.b_lead)
		frappe.set_user(self.b)
		self.assertFalse(
			agent.list_appointments("2035-06-12T00:00:00", "2035-06-13T00:00:00")["appointments"]
		)
		with self.assertRaises(frappe.PermissionError):
			agent.save_appointment(self.b_lead, {"status": "Cancelled"}, created["name"])
		frappe.set_user(self.a)
		changed = agent.save_appointment(
			self.a_lead,
			{"starts_on": "2035-06-12T12:00:00", "ends_on": "2035-06-12T13:00:00"},
			created["name"],
		)
		self.assertEqual(changed["appointment"]["starts_on"].hour, 12)
		done = agent.save_appointment(self.a_lead, {"status": "Completed"}, created["name"])
		self.assertEqual(done["appointment"]["status"], "Completed")
		frappe.db.set_value("CRM Lead", self.a_lead, "owner", self.b)
		self.assertFalse(
			agent.list_appointments("2035-06-12T00:00:00", "2035-06-13T00:00:00")["appointments"]
		)
		with self.assertRaises(frappe.PermissionError):
			agent.save_appointment(self.a_lead, {"status": "Cancelled"}, created["name"])

	def test_appointment_validation_and_conflicts(self):
		first = self.appointment()["appointment"]
		self.assertTrue(self.appointment()["conflict"])
		self.assertFalse(
			self.appointment(starts_on="2035-06-12T11:00:00", ends_on="2035-06-12T12:00:00")["conflict"]
		)
		for changes in (
			{"ends_on": "2035-06-12T10:00:00"},
			{"starts_on": "garbage"},
			{"starts_on": "2035-06-12T10:00:00Z"},
			{"subject": " "},
			{"owner": self.b},
			{"event_type": "Public"},
			{"status": "Invalid"},
			{"send_reminder": "1"},
		):
			with self.subTest(changes=changes), self.assertRaises(frappe.ValidationError):
				self.appointment(**changes)
		for start, end in (
			("2035-06-12T00:00:00", "2035-08-12T00:00:00"),
			("2035-06-13T00:00:00", "2035-06-12T00:00:00"),
		):
			with self.assertRaises(frappe.ValidationError):
				agent.list_appointments(start, end)
		cancelled = agent.save_appointment(self.a_lead, {"status": "Cancelled"}, first["name"])
		self.assertEqual(cancelled["appointment"]["status"], "Cancelled")
		frappe.set_user(self.b)
		self.assertFalse(self.appointment(self.b_lead)["conflict"])

	def test_appointment_dst_validation(self):
		with patch("frappe.utils.get_system_timezone", return_value="America/New_York"):
			for value in ("2035-03-11T02:30:00", "2035-11-04T01:30:00"):
				with self.subTest(value=value), self.assertRaises(frappe.ValidationError):
					agent.appointment_time(value)
			self.assertEqual(agent.appointment_time("2035-03-11T03:30:00").hour, 3)

	def test_appointment_shared_event_cannot_be_edited(self):
		created = self.appointment()["appointment"]
		frappe.db.set_value("Event", created["name"], "repeat_this_event", 1)
		with self.assertRaises(frappe.PermissionError):
			agent.save_appointment(self.a_lead, {"subject": "Changed"}, created["name"])

	def test_unlinked_meeting_conversion_is_scoped_and_idempotent(self):
		meeting = agent.save_appointment(
			data={
				"subject": "Walk-in introduction",
				"starts_on": "2035-06-12T10:00:00",
				"ends_on": "2035-06-12T11:00:00",
			}
		)["appointment"]
		self.assertFalse(meeting["reference_docname"])
		with self.assertRaises(frappe.ValidationError):
			agent.convert_appointment_to_lead(meeting["name"], {"first_name": "Visitor"})
		frappe.set_user(self.b)
		self.assertFalse(
			agent.list_appointments("2035-06-12T00:00:00", "2035-06-13T00:00:00")["appointments"]
		)
		with self.assertRaises(frappe.PermissionError):
			agent.convert_appointment_to_lead(meeting["name"], {"first_name": "Intruder"})
		with self.assertRaises(frappe.PermissionError):
			agent.save_appointment(name=meeting["name"], data={"status": "Completed"})
		frappe.set_user(self.a)
		agent.save_appointment(name=meeting["name"], data={"status": "Completed"})
		with self.assertRaises(frappe.ValidationError):
			agent.convert_appointment_to_lead(meeting["name"], {"first_name": "Visitor", "owner": self.b})
		result = agent.convert_appointment_to_lead(meeting["name"], {"first_name": "Visitor"})
		self.assertTrue(result["created"])
		self.assertEqual(frappe.db.get_value("CRM Lead", result["lead"], "owner"), self.a)
		retry = agent.convert_appointment_to_lead(meeting["name"], {"first_name": "Visitor"})
		self.assertEqual(retry, {"lead": result["lead"], "created": False})
		event = frappe.get_doc("Event", meeting["name"])
		self.assertEqual(event.subject, "Walk-in introduction")
		self.assertEqual(event.reference_docname, result["lead"])
		self.assertEqual(event.status, "Completed")

	def test_staff_meeting_permissions_and_conversion(self):
		from crm.api import appointments

		frappe.set_user(self.staff)
		meeting = appointments.save_appointment(
			{
				"subject": "Staff introduction",
				"starts_on": "2035-06-12T10:00:00",
				"ends_on": "2035-06-12T11:00:00",
			}
		)["appointment"]
		appointments.save_appointment({"status": "Completed"}, name=meeting["name"])
		with patch("frappe.model.document.Document.check_permission", side_effect=frappe.PermissionError):
			with self.assertRaises(frappe.PermissionError):
				appointments.convert_to_lead(meeting["name"], {"first_name": "Denied"})
		result = appointments.convert_to_lead(meeting["name"], {"first_name": "Staff visitor"})
		self.assertEqual(frappe.db.get_value("Event", meeting["name"], "reference_docname"), result["lead"])
		self.assertEqual(frappe.db.get_value("CRM Lead", result["lead"], "lead_owner"), self.staff)
		self.assertTrue(frappe.has_permission("CRM Lead", "read", result["lead"]))
		self.assertIn(
			meeting["name"],
			[
				row.name
				for row in appointments.list_appointments("2035-06-12T00:00:00", "2035-06-13T00:00:00")[
					"appointments"
				]
			],
		)
		frappe.set_user(self.a)
		with self.assertRaises(frappe.PermissionError):
			agent.convert_appointment_to_lead(meeting["name"], {"first_name": "Intruder"})
		frappe.set_user("Guest")
		with self.assertRaises(frappe.PermissionError):
			appointments.list_appointments("2035-06-12T00:00:00", "2035-06-13T00:00:00")

	def test_appointment_activity_current_status_and_privacy(self):
		from crm.api import appointments
		from crm.api.activities import get_lead_activities

		frappe.set_user(self.staff)
		lead = frappe.get_doc(
			{"doctype": "CRM Lead", "first_name": "Calendar lead", "lead_owner": self.staff, "status": "New"}
		).insert()
		event = appointments.save_appointment(
			{
				"subject": "Timeline meeting",
				"starts_on": "2035-06-12T10:00:00",
				"ends_on": "2035-06-12T11:00:00",
				"location": "Reception",
			},
			lead=lead.name,
		)["appointment"]
		entries = [row for row in get_lead_activities(lead.name)[0] if row["activity_type"] == "appointment"]
		self.assertEqual([row["name"] for row in entries], [event["name"]])
		self.assertEqual(entries[0]["data"]["location"], "Reception")
		self.assertNotIn("description", entries[0]["data"])
		appointments.save_appointment(
			{"starts_on": "2035-06-12T12:00:00", "ends_on": "2035-06-12T13:00:00", "status": "Cancelled"},
			lead=lead.name,
			name=event["name"],
		)
		entries = [row for row in get_lead_activities(lead.name)[0] if row["activity_type"] == "appointment"]
		self.assertEqual(len(entries), 1)
		self.assertEqual(entries[0]["data"]["status"], "Cancelled")
		self.assertEqual(entries[0]["data"]["starts_on"].hour, 12)
		frappe.set_user("Administrator")
		private = appointments.save_appointment(
			{
				"subject": "Private administrator meeting",
				"starts_on": "2035-06-12T10:00:00",
				"ends_on": "2035-06-12T11:00:00",
			},
			lead=lead.name,
		)["appointment"]
		frappe.set_user(self.staff)
		entries = [row for row in get_lead_activities(lead.name)[0] if row["activity_type"] == "appointment"]
		self.assertNotIn(private["name"], [row["name"] for row in entries])
		with self.assertRaises(frappe.PermissionError):
			get_lead_activities(self.b_lead)

	def test_converted_meeting_appears_once_in_lead_activity(self):
		from crm.api import appointments
		from crm.api.activities import get_lead_activities

		frappe.set_user(self.staff)
		meeting = appointments.save_appointment(
			{
				"subject": "Meeting before lead",
				"starts_on": "2035-06-12T10:00:00",
				"ends_on": "2035-06-12T11:00:00",
				"status": "Completed",
			}
		)["appointment"]
		result = appointments.convert_to_lead(meeting["name"], {"first_name": "Met visitor"})
		appointments.convert_to_lead(meeting["name"], {"first_name": "Met visitor"})
		entries = [
			row for row in get_lead_activities(result["lead"])[0] if row["activity_type"] == "appointment"
		]
		self.assertEqual([row["name"] for row in entries], [meeting["name"]])
		self.assertEqual(entries[0]["data"]["status"], "Completed")

	def test_lead_activity_without_event_access(self):
		from crm.api.activities import get_linked_appointments

		with patch.object(frappe, "has_permission", side_effect=lambda doctype, *args: doctype != "Event"):
			self.assertEqual(get_linked_appointments(self.a_lead), [])
