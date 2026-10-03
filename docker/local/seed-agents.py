def run():
    import frappe
    from frappe.utils.password import update_password
    from crm.api import agent
    from crm.permissions.commission_agent import install_role
    if frappe.local.site != "crm.localhost" or not frappe.conf.get("mute_emails"):
        raise RuntimeError("Local muted test site only")
    frappe.set_user("Administrator")
    install_role()
    for label in ("a", "b"):
        email = f"dev2.agent.{label}@example.invalid"
        if not frappe.db.exists("User", email):
            frappe.get_doc({"doctype": "User", "email": email, "first_name": f"Local Agent {label.upper()}",
                "user_type": "Website User", "send_welcome_email": 0,
                "roles": [{"role": "Commission Agent"}]}).insert(ignore_permissions=True)
        update_password(email, "Local-Dev2-Only-2026")
        if label == "a":
            user = frappe.get_doc("User", email)
            user.api_key = "local-dev2-agent-a"
            user.api_secret = "Local-Dev2-Token-Only-2026"
            user.save(ignore_permissions=True)
        frappe.set_user(email)
        lead_email = f"agent.lead.{label}@example.invalid"
        if not frappe.db.exists("CRM Lead", {"email": lead_email}):
            agent.save_lead({"first_name": f"Agent {label.upper()} sample lead", "email": lead_email})
        frappe.set_user("Administrator")
    frappe.db.commit()
    print("Local Commission Agent demo accounts ready.")
