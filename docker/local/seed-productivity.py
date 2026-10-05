"""Synthetic My Day browser fixtures, restricted to the muted local site."""
def run():
    from datetime import datetime, time, timedelta
    import frappe
    from frappe.utils import now_datetime
    if frappe.local.site != "crm.localhost" or not frappe.conf.get("mute_emails"):
        raise RuntimeError("Local muted test site only")
    start = datetime.combine(now_datetime().date(), time.min)
    for label, user in (("admin", "Administrator"), ("staff", "dev2.sales.a@example.invalid"), ("agent-a", "dev2.agent.a@example.invalid"), ("agent-b", "dev2.agent.b@example.invalid")):
        frappe.set_user(user)
        email = "daily.browser." + label + "@example.invalid"
        lead = frappe.db.get_value("CRM Lead", {"owner": user, "email": email}, "name")
        if not lead:
            lead = frappe.get_doc({"doctype": "CRM Lead", "first_name": "My Day Browser " + label, "email": email, "status": "New", "lead_owner": None if label.startswith("agent") else user}).insert(ignore_permissions=True).name
        for bucket, due in (("overdue", start - timedelta(hours=1)), ("today", start + timedelta(hours=23)), ("upcoming", start + timedelta(days=1, hours=12)), ("undated", None)):
            title = "My Day Browser " + label + " " + bucket
            name = frappe.db.get_value("CRM Task", {"owner": user, "title": title}, "name")
            doc = frappe.get_doc("CRM Task", name) if name else frappe.new_doc("CRM Task")
            doc.update({"title": title, "status": "Todo", "priority": "High", "due_date": due, "reference_doctype": "CRM Lead", "reference_docname": lead})
            doc.save(ignore_permissions=True)
        subject = "My Day Browser " + label + " meeting"
        name = frappe.db.get_value("Event", {"owner": user, "subject": subject}, "name")
        event = frappe.get_doc("Event", name) if name else frappe.new_doc("Event")
        event.update({"subject": subject, "event_type": "Private", "status": "Open", "starts_on": start + timedelta(hours=14), "ends_on": start + timedelta(hours=15), "reference_doctype": "CRM Lead", "reference_docname": lead, "send_reminder": 0, "sync_with_google_calendar": 0})
        event.save(ignore_permissions=True)
    frappe.set_user("Administrator")
    frappe.db.commit()
    print("Synthetic My Day fixtures ready; no outgoing mail.")
