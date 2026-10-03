def run():
    """Create one explicitly synthetic Opportunity for the isolated browser smoke."""
    import frappe

    if frappe.local.site != "crm.localhost" or not frappe.conf.get("mute_emails"):
        raise RuntimeError("Only the muted local crm.localhost site is supported")
    frappe.set_user("Administrator")
    email = "dev2.opportunity.browser.v2@example.invalid"
    agent = "dev2.agent.a@example.invalid"
    if not frappe.db.exists("User", agent):
        raise RuntimeError("Run the standard local agent seed first")
    lead = frappe.db.get_value("Lead", {"email_id": email}, "name")
    if not lead:
        lead = frappe.get_doc({"doctype": "Lead", "first_name": "Synthetic Opportunity Browser", "email_id": email, "status": "Lead", "lead_owner": "Administrator"}).insert().name
        frappe.db.set_value("Lead", lead, "owner", agent)
    title = "Dev2 synthetic Opportunity sync browser v2"
    if not frappe.db.exists("Opportunity", {"title": title}):
        company = frappe.get_all("Company", pluck="name", limit_page_length=1)[0]
        currency = frappe.db.get_single_value("FCRM Settings", "currency") or "USD"
        # Explicit synthetic rate prevents external rate lookup in this fixture.
        opportunity = frappe.get_doc({"doctype": "Opportunity", "title": title, "opportunity_from": "Lead", "party_name": lead, "company": company, "currency": currency, "conversion_rate": 2, "opportunity_amount": 1200, "expected_closing": "2035-06-30", "opportunity_owner": "Administrator", "status": "Open"}).insert()
        opportunity.db_set("owner", agent)
    frappe.db.commit()
    print("Synthetic local Opportunity is ready; sync remains opt-in.")
