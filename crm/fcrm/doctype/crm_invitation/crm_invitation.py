# Copyright (c) 2024, Frappe Technologies Pvt. Ltd. and contributors
# For license information, please see license.txt

import frappe
from frappe import _
from frappe.model.document import Document

from crm.api.user import validate_no_role_profile


class CRMInvitation(Document):
	# begin: auto-generated types
	# This code is auto-generated. Do not modify anything in this block.

	from typing import TYPE_CHECKING

	if TYPE_CHECKING:
		from frappe.types import DF

		accepted_at: DF.Datetime | None
		email: DF.Data
		email_sent_at: DF.Datetime | None
		invited_by: DF.Link | None
		key: DF.Data | None
		role: DF.Literal["", "Sales User", "Sales Manager", "System Manager", "Agent"]
		status: DF.Literal["", "Pending", "Accepted", "Expired"]
	# end: auto-generated types

	def before_insert(self):
		frappe.utils.validate_email_address(self.email, True)
		self.validate_existing_user()

		self.key = frappe.generate_hash(length=12)
		self.invited_by = frappe.session.user
		self.status = "Pending"

	def after_insert(self):
		self.invite_via_email()

	def invite_via_email(self):
		invite_link = frappe.utils.get_url(f"/api/method/crm.api.accept_invitation?key={self.key}")
		if frappe.local.dev_server:
			print(f"Invite link for {self.email}: {invite_link}")  # nosemgrep

		title = "Frappe CRM"
		template = "crm_invitation"

		frappe.sendmail(
			recipients=self.email,
			subject=f"You have been invited to join {title}",
			template=template,
			args={"title": title, "invite_link": invite_link},
			now=True,
		)
		self.db_set("email_sent_at", frappe.utils.now())

	@frappe.whitelist()
	def accept_invitation(self):
		frappe.only_for(["System Manager", "Sales Manager"], True)
		if self.accept():
			# the invitee was not around to set a password, mail them a link to do it
			frappe.get_doc("User", self.email).send_welcome_mail_to_user()

	def accept(self):
		if self.status != "Pending":
			frappe.throw(_("Invalid or expired key"))

		# Never turn an existing staff account into an external agent through an invite.
		if self.role == "Agent" and frappe.db.exists("User", self.email):
			frappe.throw(
				_("This account already exists. Manage its access in Settings."), frappe.PermissionError
			)
		user, is_new_user = self.create_user_if_not_exists()
		if not is_new_user:
			from crm.permissions.commission_agent import is_agent

			if is_agent(user.name):
				frappe.throw(_("Manage agent access in Settings."), frappe.PermissionError)
			validate_no_role_profile(user)
		user.append_roles(self.role)
		if self.role == "System Manager":
			user.append_roles("Sales Manager", "Sales User")
		elif self.role == "Sales Manager":
			user.append_roles("Sales User")
		if self.role == "Sales User":
			self.update_module_in_user(user, "FCRM")
		user.save(ignore_permissions=True)
		if self.role == "Agent":
			from crm.api.agent_admin import log, profile_issues

			if profile_issues(user):
				frappe.throw(
					_("Site defaults added incompatible roles. Review agent provisioning."),
					frappe.PermissionError,
				)
			log(user, "Created", "Agent joined through CRM invitation", 0)

		self.status = "Accepted"
		self.accepted_at = frappe.utils.now()
		self.key = None
		self.save(ignore_permissions=True)

		return is_new_user

	def update_module_in_user(self, user, module):
		block_modules = frappe.get_all(
			"Module Def",
			fields=["name as module"],
			filters={"name": ["!=", module]},
		)

		if block_modules:
			user.set("block_modules", block_modules)

	def validate_existing_user(self):
		# the invite would be accepted but the role never applied, so fail early
		if frappe.db.exists("User", self.email):
			validate_no_role_profile(frappe.get_doc("User", self.email))

	def create_user_if_not_exists(self):
		if not frappe.db.exists("User", self.email):
			first_name = self.email.split("@")[0].title()
			user = frappe.get_doc(
				doctype="User",
				user_type="Website User" if self.role == "Agent" else "System User",
				email=self.email,
				send_welcome_email=0,
				first_name=first_name,
				default_app="crm",
				redirect_url="/crm" if self.role == "Agent" else None,
			).insert(ignore_permissions=True)
			return user, True

		return frappe.get_doc("User", self.email), False


def expire_invitations():
	"""expire invitations after 3 days"""
	from frappe.utils import add_days, now

	days = 3
	invitations_to_expire = frappe.db.get_all(
		"CRM Invitation", filters={"status": "Pending", "creation": ["<", add_days(now(), -days)]}
	)
	for invitation in invitations_to_expire:
		invitation = frappe.get_doc("CRM Invitation", invitation.name)
		invitation.status = "Expired"
		invitation.save(ignore_permissions=True)
