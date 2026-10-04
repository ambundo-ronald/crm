"""Synthetic credentials for the isolated agent administration browser check only."""
def run(email):
    import frappe
    from frappe.utils.password import update_password
    if frappe.local.site != "crm.localhost" or not frappe.conf.get("mute_emails"):
        raise RuntimeError("Local muted test site only")
    if not email.startswith("dev2.admin-browser.") or not email.endswith("@example.invalid"):
        raise RuntimeError("Synthetic browser agent only")
    frappe.set_user("Administrator")
    doc = frappe.get_doc("User", email)
    if doc.user_type != "Website User" or {r.role for r in doc.roles} != {"Commission Agent"}:
        raise RuntimeError("Restricted fixture account required")
    update_password(email, "Local-Dev2-Only-2026")
    doc.api_key = "local-admin-browser-" + email.split("@")[0].split(".")[-1]
    doc.api_secret = "Local-Dev2-Browser-Token-Only-2026"
    doc.save(ignore_permissions=True)
    frappe.db.commit()
