"""Secret-free invitation diagnostics that survive request rollback."""

from contextlib import contextmanager, suppress
from traceback import walk_tb
from uuid import uuid4

import frappe


@contextmanager
def invitation_step(stage):
	try:
		yield
	except Exception as exc:
		reference = uuid4().hex[:12]
		# Never serialize exception messages, source lines, locals, users or requests.
		frames = [
			f"{frame.f_code.co_filename}:{line} in {frame.f_code.co_name}"
			for frame, line in walk_tb(exc.__traceback__)
		]
		message = "\n".join([
			"Diagnostic version: 2026-10-23",
			f"Reference: {reference}", f"Stage: {stage}",
			f"Exception: {type(exc).__name__}", *frames,
		])
		title = f"CRM invitation failure {reference}"
		# log_error() adds request metadata and may capture the invitation key in
		# a referrer. Construct the sanitized record directly instead.
		with suppress(Exception):
			frappe.get_doc({"doctype": "Error Log", "method": title, "error": message}).deferred_insert()
		with suppress(Exception):
			frappe.logger("crm.invitation", allow_site=True, with_more_info=False).error(message)
		raise
