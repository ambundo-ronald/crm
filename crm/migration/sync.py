"""Opt-in, same-site ERPNext Lead and Opportunity sync. Transactions belong to the caller/job."""

import json
from collections import Counter
from contextlib import contextmanager

import frappe
from frappe.utils import now_datetime

from crm.migration.erpnext import preview
from crm.migration.planner import FIELD_MAP
from crm.permissions.commission_agent import is_agent

SETTINGS = "CRM ERPNext Sync Settings"
LINK = "CRM ERPNext Sync Link"
RUN = "CRM ERPNext Sync Run"


def require_admin():
	if is_agent() or (frappe.session.user != "Administrator" and "System Manager" not in frappe.get_roles()):
		frappe.throw("Only administrators can manage ERPNext sync", frappe.PermissionError)


def parse_mapping(value):
	value = frappe.parse_json(value) if isinstance(value, str) and value.strip() else value or {}
	if not isinstance(value, dict) or any(
		not isinstance(k, str) or not isinstance(v, str) for k, v in value.items()
	):
		frappe.throw("Mappings must be JSON objects with text keys and values")
	return value


def initialize():
	# Persist a lockable row even when the disabled singleton has never been opened.
	if not frappe.db.sql("SELECT field FROM `tabSingles` WHERE doctype=%s AND field='enabled'", SETTINGS):
		frappe.db.set_single_value(SETTINGS, "enabled", 0)


@frappe.whitelist(methods=["GET", "POST"])
def status():
	require_admin()
	settings = frappe.get_single(SETTINGS)
	return {
		"available": "erpnext" in frappe.get_installed_apps(),
		"enabled": settings.enabled,
		"automatic": settings.automatic,
		"cursor": settings.cursor,
		"last_run": settings.last_run,
		"linked_leads": frappe.db.count(LINK),
		"linked_organizations": frappe.db.count("CRM ERPNext Customer Link"),
		"sync_customers": settings.sync_customers,
		"customer_cursor": settings.customer_cursor,
		"linked_deals": frappe.db.count("CRM ERPNext Opportunity Link"),
		"sync_opportunities": settings.sync_opportunities,
		"opportunity_cursor": settings.opportunity_cursor,
		"runs": frappe.get_all(
			RUN,
			fields=["name", "creation", "summary", "results"],
			order_by="creation desc",
			limit_page_length=10,
		),
	}


@frappe.whitelist(methods=["POST"])
def configure(enabled: bool = False, automatic: bool = False):
	require_admin()
	_lock()
	settings = frappe.get_single(SETTINGS)
	settings.enabled = int(enabled)
	settings.automatic = int(automatic) if enabled else 0
	settings.save()
	return status()


@frappe.whitelist(methods=["POST"])
def configure_opportunities(enabled: bool = False):
	require_admin()
	_lock()
	settings = frappe.get_single(SETTINGS)
	settings.sync_opportunities = int(enabled)
	settings.save()
	return status()


@frappe.whitelist(methods=["POST"])
def configure_customers(enabled: bool = False):
	require_admin()
	_lock()
	settings = frappe.get_single(SETTINGS)
	settings.sync_customers = int(enabled)
	settings.save()
	return status()


def _lock():
	# Held until request/job commit, serializing manual and scheduled batches.
	rows = frappe.db.sql(
		"SELECT field FROM `tabSingles` WHERE doctype=%s AND field='enabled' FOR UPDATE", SETTINGS
	)
	if not rows:
		frappe.throw("Run bench migrate to initialize ERPNext sync settings")


@frappe.whitelist(methods=["POST"])
def sync_now():
	require_admin()
	return run_batch()


def scheduled_sync():
	if "erpnext" not in frappe.get_installed_apps():
		return
	if frappe.db.get_single_value(SETTINGS, "enabled") and frappe.db.get_single_value(SETTINGS, "automatic"):
		return run_batch(automatic=True)


def run_batch(automatic=False):
	require_admin()
	_lock()
	settings = frappe.get_single(SETTINGS)
	if not settings.enabled:
		frappe.throw("Enable ERPNext Lead sync before running it")
	if automatic and not settings.automatic:
		return
	report = preview(
		limit=50,
		after=settings.cursor,
		status_map=parse_mapping(settings.status_map),
		user_map=parse_mapping(settings.user_map),
	)
	results = []
	for proposal in report["proposals"]:
		source_name = proposal["source_key"][2]
		frappe.db.savepoint("sync_record")
		try:
			result = _apply(proposal)
		except Exception as exc:
			frappe.db.rollback(save_point="sync_record")
			# Log exception class only; custom validators may embed sensitive data.
			result = {"status": "Failed", "issues": [type(exc).__name__]}
		results.append(
			{"source": source_name, "source_doctype": "Lead", "target_doctype": "CRM Lead", **result}
		)
	customers = {"has_more": False, "next_after": settings.customer_cursor}
	if settings.sync_customers:
		from crm.migration.customer import sync_batch as sync_customers

		customers = sync_customers(settings)
		results.extend(customers["results"])
	opportunities = {"has_more": False, "next_after": settings.opportunity_cursor}
	if settings.sync_opportunities:
		from crm.migration.opportunity import sync_batch

		opportunities = sync_batch(settings)
		results.extend(opportunities["results"])
	has_more = report["has_more"] or customers["has_more"] or opportunities["has_more"]
	counts = Counter(row["status"] for row in results)
	run = frappe.get_doc(
		{
			"doctype": RUN,
			"summary": ", ".join(f"{key}: {value}" for key, value in sorted(counts.items()))
			or "No source leads",
			"results": json.dumps(results),
			"next_cursor": report["next_after"],
			"has_more": has_more,
		}
	).insert(ignore_permissions=True)
	frappe.db.set_single_value(
		SETTINGS,
		{
			"cursor": report["next_after"] or "",
			"opportunity_cursor": opportunities["next_after"] or "",
			"customer_cursor": customers["next_after"] or "",
			"last_run": now_datetime(),
		},
	)
	return {"run": run.name, "results": results, "has_more": has_more, "summary": run.summary}


@contextmanager
def creator_context(creator):
	"""Preserve the authenticated HTTP session while Frappe sets insert ownership."""
	if creator == frappe.session.user:
		yield
		return
	session = frappe.local.session.copy()
	form_dict = frappe.local.form_dict
	try:
		frappe.set_user(creator)
		yield
	finally:
		frappe.set_user(session["user"])
		# set_user resets sid/data as well as user. Restoring just the username
		# would invalidate the caller's cookie on the next browser request.
		frappe.local.session.clear()
		frappe.local.session.update(session)
		frappe.local.form_dict = form_dict


def _apply(proposal):
	source = frappe.get_doc("Lead", proposal["source_key"][2], for_update=True)
	# Preview and locking are separate reads: never apply stale proposals.
	if str(source.modified) != str(proposal["provenance"]["modified"]):
		return {"status": "Review", "issues": ["source_changed_during_preview"]}
	link_name = frappe.db.get_value(LINK, {"source_name": source.name}, "name")
	link = frappe.get_doc(LINK, link_name) if link_name else None
	# Contacts stay unlinked: their existence must not block a Lead-only sync.
	issues = [issue for issue in proposal["issues"] if issue != "shared_contact_links_require_review"]
	if link and set(proposal["duplicate_crm_leads"]) <= {link.target_name}:
		issues = [issue for issue in issues if issue != "crm_duplicate_candidates"]
	if issues:
		return {"status": "Review", "issues": issues}
	incoming = {target: source.get(origin) or "" for origin, target in FIELD_MAP.items()}
	if not link:
		# Frappe v16 takes owner from the session on insert. Use the explicitly
		# validated creator only for this insert, restoring the admin in all cases.
		with creator_context(proposal["proposed_creator"]):
			target = frappe.get_doc({"doctype": "CRM Lead", **proposal["proposed_fields"]}).insert(
				ignore_permissions=True
			)
		frappe.get_doc(
			{
				"doctype": LINK,
				"source_name": source.name,
				"target_name": target.name,
				"source_snapshot": json.dumps(incoming),
				"target_snapshot": json.dumps({field: target.get(field) or "" for field in incoming}),
				"source_creator": source.owner,
				"source_created": source.creation,
				"source_modified": source.modified,
			}
		).insert(ignore_permissions=True)
		return {"status": "Created", "target": target.name}
	if not frappe.db.exists("CRM Lead", link.target_name):
		return {"status": "Review", "issues": ["target_missing"]}
	target = frappe.get_doc("CRM Lead", link.target_name, for_update=True)
	if (
		target.converted
		or target.owner != proposal["proposed_creator"]
		or source.owner != link.source_creator
	):
		return {"status": "Review", "issues": ["creator_or_conversion_changed"]}
	from crm.migration.sync_merge import merge_changes

	changes, conflicts = merge_changes(
		incoming,
		json.loads(link.source_snapshot),
		{field: target.get(field) or "" for field in incoming},
		json.loads(link.target_snapshot),
	)
	if conflicts:
		return {
			"status": "Review",
			"issues": ["field_conflict:" + field for field in conflicts],
			"target": target.name,
		}
	if changes:
		target.update(changes)
		target.save(ignore_permissions=True)
	# Keep the original CRM baseline for fields unchanged upstream, protecting local edits.
	baseline = json.loads(link.target_snapshot)
	old_source = json.loads(link.source_snapshot)
	for field in incoming:
		if incoming[field] != old_source.get(field, ""):
			baseline[field] = target.get(field) or ""
	link.source_snapshot = json.dumps(incoming)
	link.target_snapshot = json.dumps(baseline)
	link.source_modified = source.modified
	link.save(ignore_permissions=True)
	return {"status": "Updated" if changes else "Unchanged", "target": target.name}
