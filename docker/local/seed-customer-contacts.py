def run():
    """Synthetic Customer/Contact review fixtures, only on the muted local site."""
    import frappe

    if frappe.local.site != "crm.localhost" or not frappe.conf.get("mute_emails"):
        raise RuntimeError("Only muted local crm.localhost is supported")
    frappe.set_user("Administrator")
    title = "Dev2 Relationship Browser Company"
    customer = frappe.db.get_value("Customer", {"customer_name": title}, "name")
    if not customer:
        customer = frappe.get_doc({"doctype": "Customer", "customer_name": title, "customer_type": "Company", "customer_group": frappe.get_all("Customer Group", pluck="name", limit_page_length=1)[0], "territory": frappe.get_all("Territory", pluck="name", limit_page_length=1)[0]}).insert().name
    lead = frappe.db.get_value("Lead", {"email_id": "dev2.opportunity.browser.v2@example.invalid"}, "name")
    if not lead:
        raise RuntimeError("Run the local Opportunity seed first")
    if not frappe.db.exists("Contact", {"first_name": "Dev2 Shared Review Browser"}):
        frappe.get_doc({"doctype": "Contact", "first_name": "Dev2 Shared Review Browser", "email_ids": [{"email_id": "dev2.shared.review@example.invalid", "is_primary": 1}], "links": [{"link_doctype": "Lead", "link_name": lead}, {"link_doctype": "Customer", "link_name": customer}]}).insert()
    frappe.db.commit()
    print("Synthetic business Customer and shared Contact are ready; sync stays opt-in.")
