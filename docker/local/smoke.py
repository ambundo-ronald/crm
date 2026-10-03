"""HTTP smoke check for the isolated local backend; never accepts a remote URL."""
import http.cookiejar
import json
import urllib.parse
import urllib.request

base = "http://127.0.0.1:18000"
cookies = http.cookiejar.CookieJar()
client = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookies))
login = urllib.parse.urlencode({
    "usr": "Administrator", "pwd": "Local-Dev2-Only-2026"
}).encode()
with client.open(base + "/api/method/login", data=login, timeout=60) as response:
    assert response.status == 200
with client.open(base + "/api/method/frappe.auth.get_logged_user", timeout=60) as response:
    assert json.load(response)["message"] == "Administrator"
with client.open(base + "/crm", timeout=60) as response:
    html = response.read().decode()
    assert response.status == 200
    assert "/assets/crm/frontend/" in html, "CRM asset references missing"
for doctype in ("CRM Lead", "Contact", "Customer"):
    path = "/api/resource/" + urllib.parse.quote(doctype) + "?limit_page_length=1"
    with client.open(base + path, timeout=60) as response:
        assert isinstance(json.load(response)["data"], list)
print("PASS: local login, authenticated CRM HTML, and CRM/ERPNext resource APIs")

# Verify existing sales-user lead isolation independently of test-fixture generation.
query = urllib.parse.urlencode({
    "fields": json.dumps(["name", "email"]),
    "filters": json.dumps([["email", "in", [
        "dev2.lead.a@example.invalid", "dev2.lead.b@example.invalid"
    ]]]),
})
with client.open(base + "/api/resource/CRM%20Lead?" + query, timeout=60) as response:
    leads = {row["email"]: row["name"] for row in json.load(response)["data"]}
assert len(leads) == 2, "Synthetic leads missing"
agent_cookies = http.cookiejar.CookieJar()
agent = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(agent_cookies))
data = urllib.parse.urlencode({
    "usr": "dev2.sales.a@example.invalid", "pwd": "Local-Dev2-Only-2026"
}).encode()
with agent.open(base + "/api/method/login", data=data, timeout=60) as response:
    assert response.status == 200
with agent.open(base + "/api/resource/CRM%20Lead?" + query, timeout=60) as response:
    visible = json.load(response)["data"]
    assert [row["email"] for row in visible] == ["dev2.lead.a@example.invalid"]
other = urllib.parse.quote(leads["dev2.lead.b@example.invalid"], safe="")
try:
    agent.open(base + "/api/resource/CRM%20Lead/" + other, timeout=60)
except urllib.error.HTTPError as error:
    assert error.code in (403, 404), error.code
else:
    raise AssertionError("Sales user A could read sales user B's lead")
print("PASS: existing sales-user lead list filtering and direct-document denial")

