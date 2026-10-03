def run():
    """Synthetic fixtures for the isolated local site only."""
    import frappe

    if frappe.local.site != "crm.localhost" or not frappe.conf.get("mute_emails"):
        raise RuntimeError("Seed is restricted to the muted local crm.localhost test site")

    for label in ("a", "b"):
        email = f"dev2.sales.{label}@example.invalid"
        if not frappe.db.exists("User", email):
            frappe.get_doc({
                "doctype": "User", "email": email,
                "first_name": f"Local Sales {label.upper()}",
                "enabled": 1, "user_type": "System User",
                "send_welcome_email": 0,
                "new_password": "Local-Dev2-Only-2026",
                "roles": [{"role": "Sales User"}],
            }).insert(ignore_permissions=True)
        lead_email = f"dev2.lead.{label}@example.invalid"
        if not frappe.db.exists("CRM Lead", {"email": lead_email}):
            frappe.get_doc({
                "doctype": "CRM Lead", "first_name": f"Synthetic Lead {label.upper()}",
                "email": lead_email, "lead_owner": email, "owner": email,
                "status": "New",
            }).insert(ignore_permissions=True)
        if not frappe.db.exists("Contact", {"first_name": f"Dev2 Synthetic Contact {label.upper()}"}):
            frappe.get_doc({
                "doctype": "Contact", "first_name": f"Dev2 Synthetic Contact {label.upper()}",
                "owner": email,
                "email_ids": [{"email_id": f"dev2.contact.{label}@example.invalid", "is_primary": 1}],
            }).insert(ignore_permissions=True)
    frappe.db.commit()
    print("Synthetic local users, leads and contacts created. Commission-agent restrictions are not implemented.")
