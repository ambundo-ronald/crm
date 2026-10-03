def run():
    import frappe
    from frappe.custom.doctype.custom_field.custom_field import create_custom_fields
    if frappe.local.site != "crm.localhost" or not frappe.conf.get("mute_emails"):
        raise RuntimeError("Only muted crm.localhost is supported")
    frappe.set_user("Administrator")
    field = "custom_dev2_demo_reference"
    for doctype in ("Prospect", "CRM Organization"):
        if not frappe.db.exists("Custom Field", {"dt": doctype, "fieldname": field}):
            create_custom_fields({doctype: [{"fieldname": field, "label": "Local demo reference", "fieldtype": "Data"}]})
    title = "Dev2 Prospect Browser Company"
    if not frappe.db.exists("Prospect", title):
        doc = frappe.get_doc({"doctype": "Prospect", "company_name": title, "company": frappe.get_all("Company", pluck="name", limit_page_length=1)[0], field: "ERPNext demo reference"}).insert()
        doc.add_comment("Comment", "Historical Prospect browser note")
    if not frappe.db.exists("Address", {"address_title": "Dev2 Additional Browser Address"}):
        frappe.get_doc({"doctype": "Address", "address_title": "Dev2 Additional Browser Address", "address_type": "Shipping", "address_line1": "Synthetic address only", "city": "Nairobi", "country": "Kenya", "links": [{"link_doctype": "Prospect", "link_name": title}]}).insert()
    from frappe.utils.file_manager import save_file
    for private, filename in ((0, "dev2-restore-public.txt"), (1, "dev2-restore-private.txt")):
        if not frappe.db.exists("File", {"file_name": filename, "attached_to_doctype": "Prospect", "attached_to_name": title}):
            save_file(filename, b"Synthetic local restore fixture", "Prospect", title, is_private=private)
    frappe.db.commit()
    print("Local Prospect, additional Address, history and custom-field fixtures ready")
