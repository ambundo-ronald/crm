# ERPNext migration mapping and read-only preview

Status (2026-10-03): the completed CRM milestone is pushed to dev2. Migration is at the mapping and preview stage. No production access or imports have occurred.

## First supported slice

`crm.migration.erpnext.preview` reads ERPNext Leads and proposes CRM Lead fields on the same site. It is a Bench-only administrative function, not a public/whitelisted API, and has no apply mode. System Manager or Administrator is required; Commission Agent accounts are denied even with additional roles.

It inventories source/target counts, lists custom fields, preserves source identity in the report, and flags duplicate candidates, missing/disabled creators, unsuitable salesperson assignments, missing names, invalid email, unmapped statuses, shared contacts and unmapped mandatory target fields. It does not create or alter records, links, permissions, schema, source mappings or checkpoints.

### Lead mapping checked against local v16 schemas

| ERPNext Lead | CRM Lead / report | Rule |
| --- | --- | --- |
| first_name, middle_name, last_name | same fields | Missing first name requires review; do not invent a person's name from company_name |
| email_id | email | Case/whitespace-normalized comparison for duplicate candidates |
| mobile_no, phone | same fields | Digit-normalized comparison; country codes are not guessed |
| company_name | organization (Data) | No CRM Organization record is created by this preview |
| website, job_title, no_of_employees | same fields | Proposed values only |
| status | CRM Lead Status | Proposed map below; target status must exist |
| owner | proposed_creator + original-owner provenance | Preserve verified creator for agent access; explicit user mapping when identity changes |
| lead_owner | lead_owner | Must resolve to an enabled staff System User, not an external Commission Agent |
| name + current site | source_key [site, Lead, name] | Identity proposal; persisted unique mapping/checkpoints still need implementation |
| creation, modified | provenance | Preserve source history separately in the future importer; no timestamp rewriting now |
| existing Contact.links -> Lead | shared_contacts | Report existing identities; review before adding CRM Lead links because this changes agent visibility |

Proposed status mapping: Lead/Open -> New; Replied -> Contacted; Interested -> Nurture; Opportunity/Quotation -> Qualified. These are suggestions requiring business review; they do not move an Opportunity or Quotation document. Custom statuses need explicit mapping. Converted, Lost Quotation, Do Not Contact, disabled and unsubscribed leads always require lifecycle/consent review, even if a status override is supplied.

A `create_candidate` is not approval or proof that a document can be inserted. Dynamic required fields, server scripts, workflow rules, custom validations, source history, consent and relationship mappings still need a controlled importer and staging checks. Matching email or phone is a duplicate candidate, never an automatic merge. Source duplicates are checked across the bounded source inventory, not only the requested page.

### Remaining object mappings

| Source | Proposed destination | Work still required |
| --- | --- | --- |
| Opportunity | CRM Deal | Map party type/identity; source Lead to CRM Lead; opportunity_owner to deal_owner; opportunity_amount to deal_value; currency/exchange rate; expected_closing to expected_closure_date; sales_stage/status to approved CRM Deal Status; contacts/products and lifecycle review |
| Customer / Prospect | CRM Organization where appropriate | Distinguish organizations from individuals; preserve ERPNext identity; avoid duplicate organizations |
| Contact / Address | Reuse shared records | Review added links and resulting visibility; do not copy contacts just because the CRM app is new |
| Industry Type / Territory | CRM Industry / CRM Territory | These are different linked DocTypes; do not copy source names blindly |
| Notes / communications / files / ToDo / Event | Appropriate CRM activity/reference | Preserve ownership, timestamps, visibility and attachments; explicitly reconcile excluded history |

## Local usage

After syncing the module into the isolated local bench:

```powershell
docker compose -f docker/local/compose.yaml exec -T backend bash /source/crm/docker/local/test-migration.sh
docker compose -f docker/local/compose.yaml exec -T backend bash -lc "cd /workspace/frappe-bench && bench --site crm.localhost execute crm.migration.erpnext.preview"
```

The local report is saved under `test-results/migration-preview.json` (gitignored). Reports can contain personal/contact data; keep reports out of GitHub. This local report is not a production inventory.

Python call parameters: `preview(limit=100, after=None, status_map=None, user_map=None)`. Mapping arguments accept dictionaries or JSON objects. Batch size is 1-500. Use the returned `next_after` only when `has_more` is true. Pagination uses source names and must be rerun against a stable snapshot before cutover.

Duplicate scans are bounded to 10,000 source and 10,000 target leads. Larger inventories set `duplicate_inventory_complete=false` and force all candidates into review; page traversal still continues beyond that bound. The preview does not perform fuzzy/company-name matching or normalize international phone prefixes. Mandatory fields with defaults and custom validation logic are not fully simulated.

## Validation and next gate

Nine pure planner tests and three same-site integration tests pass. The integration suite wraps SQL during preview to reject write statements and verifies source timestamps/target records remain unchanged. It also tests pagination, malformed inputs, role restrictions and consent exceptions using temporary synthetic ERPNext Leads. Test setup creates fixtures; the preview itself does not.

Next: review real source customizations and status/identity mapping using an isolated staging copy or sanitized export; implement persisted unique source mappings and a local sample importer; prove reruns do not duplicate records and rollback affects only the migration batch. Opportunity/history migration and continuous synchronization are separate remaining phases. No production import or sync is configured.
