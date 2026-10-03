"""Local-only HTTP security checks. Credentials are synthetic development fixtures."""
import http.cookiejar
import json
import re
import urllib.error
import urllib.parse
import urllib.request

BASE = "http://127.0.0.1:18000"
TOKEN = "token local-dev2-agent-a:Local-Dev2-Token-Only-2026"
api = "/api/method/crm.api.agent."
opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))


def request(path, data=None, csrf=None, token=False):
    headers = {}
    if csrf:
        headers["X-Frappe-CSRF-Token"] = csrf
    if token:
        headers["Authorization"] = TOKEN
    if data is not None:
        headers["Content-Type"] = "application/json"
        data = json.dumps(data).encode()
    req = urllib.request.Request(BASE + path, data=data, headers=headers)
    client = urllib.request.build_opener() if token else opener
    try:
        with client.open(req, timeout=30) as response:
            return response.status, response.read().decode()
    except urllib.error.HTTPError as error:
        return error.code, error.read().decode()


status, body = request("/api/method/login", {"usr": "dev2.agent.a@example.invalid", "pwd": "Local-Dev2-Only-2026"})
assert status == 200, (status, body[:400])
status, html = request("/crm-agent")
assert status == 200 and "Agent workspace" in html, (status, html[:400])
csrf = re.search(r'name="csrf-token" content="([^"]+)"', html).group(1)
for asset in ("/assets/crm/js/agent.js", "/assets/crm/css/agent.css"):
    status, _ = request(asset)
    assert status == 200, (asset, status)
status, body = request(api + "list_leads")
assert status == 200, (status, body[:400])
rows = json.loads(body)["message"]
assert any(row["email"] == "agent.lead.a@example.invalid" for row in rows)
assert not any(row["email"] == "agent.lead.b@example.invalid" for row in rows)
assert all("owner" not in row for row in rows)
for path in ("/api/resource/Customer", "/api/resource/CRM%20Lead",
             "/api/method/frappe.client.get_list?doctype=Contact",
             "/api/method/crm.api.session.get_users",
             "/api/method/crm.api.contact.get_linked_deals?contact=anything",
             "/api/v2/document/Contact", "/private/files/secret.pdf", "/printview",
             api + "list_leads?cmd=frappe.client.get_list"):
    for token in (False, True):
        status, body = request(path, token=token)
        assert status in (403, 404), (path, token, status, body[:300])
status, body = request(api + "list_leads", token=True)
assert status == 200, (status, body[:300])
status, body = request(api + "save_lead", {"data": {"first_name": "HTTP Smoke Lead"}}, csrf)
assert status == 200, (status, body[:400])
lead = json.loads(body)["message"]["name"]
status, body = request(api + "save_lead", {"name": lead, "data": {"owner": "Administrator"}}, csrf)
assert status >= 400, (status, body[:400])
status, body = request(api + "save_contact", {"data": {"first_name": "HTTP Smoke Contact"}, "lead": lead}, csrf)
assert status == 200, (status, body[:400])
status, body = request(api + "add_follow_up", {"lead": lead, "title": "Call synthetic prospect"}, csrf)
assert status == 200, (status, body[:400])
task = json.loads(body)["message"]["name"]
status, body = request(api + "complete_follow_up", {"name": task}, csrf)
assert status == 200, (status, body[:400])
# Guest has no agent privileges.
status, body = request("/api/method/logout", {}, csrf)
assert status == 200
status, body = request(api + "list_leads")
assert status in (401, 403)
print("PASS: agent login/page/assets, session and token isolation, protected writes, follow-ups and logout.")
