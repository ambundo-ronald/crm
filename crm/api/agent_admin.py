"""Administrator-managed external agents; financial commissions are out of scope."""

import frappe
from frappe.rate_limiter import rate_limit
from frappe.utils import get_datetime, now_datetime, validate_email_address

from crm.permissions.commission_agent import ROLE, is_agent

AUDIT = "CRM Agent Access Log"


def require_admin():
	if is_agent() or (frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles()):
		frappe.throw("Only administrators can manage external agents", frappe.PermissionError)


def clean_reason(reason):
	reason = (reason or "").strip()
	if not reason or len(reason) > 500:
		frappe.throw("Provide a reason between 1 and 500 characters")
	return reason


def profile_issues(doc):
	issues = []
	if doc.user_type != "Website User":
		issues.append("Agent must be a Website User")
	if doc.role_profile_name:
		issues.append("Remove the role profile before enabling agent access")
	if {row.role for row in doc.roles} - {ROLE, "All", "Guest"}:
		issues.append("Additional roles require administrator review")
	return issues


def agent_doc(user, modified=None):
	if user in ("Administrator", "Guest", frappe.session.user):
		frappe.throw("This account cannot be managed as an external agent", frappe.PermissionError)
	doc = frappe.get_doc("User", user, for_update=True)
	if ROLE not in {row.role for row in doc.roles}:
		frappe.throw("This is not an external agent account", frappe.PermissionError)
	if modified is not None and str(doc.modified) != modified:
		frappe.throw("The account changed. Refresh before applying this action.")
	return doc


def log(doc, action, reason, previous_enabled):
	frappe.get_doc(
		{
			"doctype": AUDIT,
			"agent": doc.name,
			"action": action,
			"actor": frappe.session.user,
			"reason": reason,
			"previous_enabled": previous_enabled,
			"enabled": doc.enabled,
		}
	).insert(ignore_permissions=True)


@frappe.whitelist(methods=["GET", "POST"])
def list_agents(after: str = "", search: str = ""):
	require_admin()
	if len(after) > 140 or len(search) > 140:
		frappe.throw("Search or cursor is too long")
	user, role = frappe.qb.DocType("User"), frappe.qb.DocType("Has Role")
	query = (
		frappe.qb.from_(user)
		.select(user.name)
		.where(
			user.name.isin(
				frappe.qb.from_(role)
				.select(role.parent)
				.where((role.parenttype == "User") & (role.role == ROLE))
			)
		)
	)
	if after:
		query = query.where(user.name > after)
	if search.strip():
		query = query.where(
			user.name.like("%" + search.strip() + "%") | user.full_name.like("%" + search.strip() + "%")
		)
	rows = query.orderby(user.name).limit(51).run(as_dict=True)
	result = []
	for row in rows[:50]:
		doc = frappe.get_doc("User", row.name)
		result.append(
			{
				"name": doc.name,
				"full_name": doc.full_name,
				"enabled": doc.enabled,
				"modified": str(doc.modified),
				"last_login": doc.last_login,
				"issues": profile_issues(doc),
			}
		)
	return {
		"agents": result,
		"has_more": len(rows) > 50,
		"next_after": rows[49].name if len(rows) > 50 else "",
		"mail_muted": bool(frappe.conf.get("mute_emails")),
	}


@frappe.whitelist(methods=["POST"])
def create_agent(email: str, first_name: str, last_name: str = ""):
	require_admin()
	email, first_name, last_name = email.strip().lower(), first_name.strip(), last_name.strip()
	if not first_name or len(first_name) > 140 or len(last_name) > 140 or len(email) > 140:
		frappe.throw("Provide a first name and valid email; each value must be at most 140 characters")
	validate_email_address(email, throw=True)
	if frappe.db.exists("User", email):
		frappe.throw("That account already exists. Existing accounts are never converted to agents here.")
	doc = frappe.get_doc(
		{
			"doctype": "User",
			"email": email,
			"first_name": first_name,
			"last_name": last_name,
			"enabled": 1,
			"user_type": "Website User",
			"send_welcome_email": 0,
			"redirect_url": "/crm-agent",
			"roles": [{"role": ROLE}],
		}
	).insert(ignore_permissions=True)
	if profile_issues(doc):
		frappe.throw("Site defaults added incompatible roles. Review account provisioning before retrying.")
	log(doc, "Created", "External agent account created; no email sent", 0)
	return {"name": doc.name, "status": "Created"}


def revoke_credentials(doc):
	from frappe.sessions import clear_sessions

	clear_sessions(user=doc.name, force=True)
	doc.api_key = ""
	doc.api_secret = ""
	doc.reset_password_key = ""
	doc.last_reset_password_key_generated_on = None
	frappe.db.set_value("OAuth Bearer Token", {"user": doc.name}, "status", "Revoked")
	frappe.db.delete("OAuth Authorization Code", {"user": doc.name})


@frappe.whitelist(methods=["POST"])
def set_agent_enabled(user: str, enabled: bool, reason: str, modified: str):
	require_admin()
	reason = clean_reason(reason)
	doc = agent_doc(user, modified)
	if enabled and profile_issues(doc):
		frappe.throw("Resolve the agent's account type and additional roles before reactivation")
	previous = doc.enabled
	if bool(previous) == enabled:
		return {"status": "Unchanged"}
	revoke_credentials(doc)
	doc.enabled = int(enabled)
	doc.send_welcome_email = 0
	doc.save(ignore_permissions=True)
	frappe.clear_cache(user=doc.name)
	log(doc, "Reactivated" if enabled else "Suspended", reason, previous)
	return {"status": "Reactivated" if enabled else "Suspended"}


@frappe.whitelist(methods=["POST"])
@rate_limit(limit=5, seconds=300)
def invite_agent(user: str, modified: str):
	require_admin()
	doc = agent_doc(user, modified)
	if not doc.enabled or profile_issues(doc):
		frappe.throw("Only enabled agents with a restricted role profile can receive setup emails")
	if frappe.conf.get("mute_emails"):
		frappe.throw("Email is muted on this site. No setup email was sent.")
	if (
		doc.last_reset_password_key_generated_on
		and (now_datetime() - get_datetime(doc.last_reset_password_key_generated_on)).total_seconds() < 60
	):
		frappe.throw("Wait at least one minute before requesting another setup email")
	# Use Frappe's expiring password setup flow; never expose the key or password.
	doc.db_set("redirect_url", "/crm-agent")
	log(doc, "Invitation requested", "Administrator requested a password setup email", doc.enabled)
	doc.validate_reset_password()
	doc._reset_password(send_email=True)
	return {"status": "Invitation requested"}


@frappe.whitelist(methods=["GET", "POST"])
def access_history(user: str, after: str = ""):
	require_admin()
	if len(after) > 140:
		frappe.throw("Invalid history cursor")
	agent_doc(user)
	entry = frappe.qb.DocType(AUDIT)
	query = (
		frappe.qb.from_(entry)
		.select(
			entry.name,
			entry.creation,
			entry.actor,
			entry.action,
			entry.reason,
			entry.previous_enabled,
			entry.enabled,
		)
		.where(entry.agent == user)
	)
	if after:
		cursor = frappe.db.get_value(AUDIT, {"agent": user, "name": after}, "creation")
		if not cursor:
			frappe.throw("Invalid history cursor")
		query = query.where((entry.creation < cursor) | ((entry.creation == cursor) & (entry.name < after)))
	rows = (
		query.orderby(entry.creation, order=frappe.qb.desc)
		.orderby(entry.name, order=frappe.qb.desc)
		.limit(51)
		.run(as_dict=True)
	)
	return {
		"rows": rows[:50],
		"has_more": len(rows) > 50,
		"next_after": rows[49].name if len(rows) > 50 else "",
	}
