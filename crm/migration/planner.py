"""Pure ERPNext Lead migration planning. No Frappe imports or writes."""

import re
from collections import defaultdict

FIELD_MAP = {
	"first_name": "first_name",
	"middle_name": "middle_name",
	"last_name": "last_name",
	"email_id": "email",
	"mobile_no": "mobile_no",
	"phone": "phone",
	"website": "website",
	"company_name": "organization",
	"job_title": "job_title",
	"no_of_employees": "no_of_employees",
}
DEFAULT_STATUSES = {
	"Lead": "New",
	"Open": "New",
	"Replied": "Contacted",
	"Interested": "Nurture",
	"Opportunity": "Qualified",
	"Quotation": "Qualified",
}
SENSITIVE_STATUSES = {"Converted", "Lost Quotation", "Do Not Contact"}


def email_key(value):
	return str(value or "").strip().casefold()


def phone_key(value):
	# Formatting only. Do not guess a country code or equate local/international numbers.
	digits = re.sub(r"\D", "", str(value or ""))
	return digits if len(digits) >= 7 else ""


def identities(row, email_field):
	keys = set()
	if email := email_key(row.get(email_field)):
		keys.add(("email", email))
	for field in ("phone", "mobile_no"):
		if phone := phone_key(row.get(field)):
			keys.add(("phone", phone))
	return keys


def make_index(rows, email_field):
	index = defaultdict(set)
	for row in rows:
		for key in identities(row, email_field):
			index[key].add(row["name"])
	return index


def plan_leads(
	sources,
	targets,
	users,
	statuses,
	source_site,
	*,
	status_map=None,
	user_map=None,
	batch=None,
	inventory_complete=True,
):
	"""A candidate is a proposal only; none of these dictionaries are insert commands.

	Sources include the bounded inventory (not just the requested page), so duplicates
	elsewhere in that inventory are reported. Contact/relationship migration is separate.
	"""
	status_map = DEFAULT_STATUSES | (status_map or {})
	user_map = user_map or {}
	source_index = make_index(sources, "email_id")
	target_index = make_index(targets, "email")
	result = []
	for source in batch if batch is not None else sources:
		issues = []
		values = {target: source.get(origin) for origin, target in FIELD_MAP.items() if source.get(origin)}
		if not str(values.get("first_name") or "").strip():
			issues.append("missing_first_name")
		if values.get("email") and not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", values["email"].strip()):
			issues.append("invalid_email")
		source_status = source.get("status")
		if source_status in SENSITIVE_STATUSES or source.get("disabled") or source.get("unsubscribed"):
			issues.append("lifecycle_or_contact_consent_requires_review")
		target_status = status_map.get(source_status)
		if not target_status:
			issues.append("unmapped_status")
		elif target_status not in statuses:
			issues.append("target_status_missing")
		else:
			values["status"] = target_status
		creator = user_map.get(source.get("owner"), source.get("owner"))
		if not creator or not users.get(creator, {}).get("enabled") or creator == "Guest":
			issues.append("creator_missing_or_disabled")
		salesperson = user_map.get(source.get("lead_owner"), source.get("lead_owner"))
		if salesperson:
			user = users.get(salesperson, {})
			if not user.get("enabled") or user.get("user_type") != "System User" or user.get("is_agent"):
				issues.append("salesperson_requires_review")
			else:
				values["lead_owner"] = salesperson
		elif not users.get(creator, {}).get("is_agent"):
			issues.append("staff_salesperson_missing")
		duplicates = set()
		source_duplicates = set()
		for key in identities(source, "email_id"):
			duplicates.update(target_index.get(key, ()))
			source_duplicates.update(source_index.get(key, ()))
		source_duplicates.discard(source["name"])
		if duplicates:
			issues.append("crm_duplicate_candidates")
		if source_duplicates:
			issues.append("source_duplicate_candidates")
		if source.get("contacts"):
			issues.append("shared_contact_links_require_review")
		if not inventory_complete:
			issues.append("duplicate_inventory_incomplete")
		result.append(
			{
				"source_key": [source_site, "Lead", source["name"]],
				"action": "review" if issues else "create_candidate",
				"proposed_fields": values,
				"proposed_creator": creator,
				"provenance": {
					"owner": source.get("owner"),
					"creation": source.get("creation"),
					"modified": source.get("modified"),
					"status": source_status,
				},
				"duplicate_crm_leads": sorted(duplicates),
				"duplicate_source_leads": sorted(source_duplicates),
				"shared_contacts": sorted(set(source.get("contacts") or [])),
				"issues": issues,
			}
		)
	return result
