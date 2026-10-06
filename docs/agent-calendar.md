# Calendar appointments and meetings before leads

Available locally on dev2:

- Staff and Administrator: **My calendar** in the CRM sidebar, or http://localhost:18000/crm/appointments.
- Staff lead page: **Book appointment** opens the calendar with that lead selected.
- Agents: the same **My calendar** screen at http://localhost:18000/crm/appointments, scoped to their own permitted appointments.

## Meet someone before creating a lead

1. Choose **Book appointment** in My calendar and leave the lead unselected.
2. Use a title such as "Introduction with walk-in visitor". A name, email address and lead are not required at booking time.
3. Enter the start/end and optional location or meeting URL, then save.
4. After the meeting, choose **Complete appointment**.
5. Choose **Create lead from meeting**, enter the person's name and any contact details, and save.

The original Event remains in the calendar with its title, times and completed status. Its reference points to the new CRM Lead, and **Open lead** opens that lead. Conversion sets the lead creator to the booking user. Repeating conversion on the same meeting returns the existing lead; a row lock prevents concurrent conversion from creating another lead. Different meetings are not automatically deduplicated into one person. Linking to an already-existing lead after a meeting is a separate future improvement.

To book against an existing lead, use **Book appointment** on that lead instead.

## Calendar behavior

The shared CRM calendar has Google Calendar-inspired Month, Week, Day and Schedule views. Use the mini calendar, Today button and arrows to navigate. Click a date or half-hour slot to book; click an event for its details and actions. Search and status filters apply to the loaded period. Linked-lead meetings are blue, introductions purple, completed meetings green and cancelled meetings grey. Agents use these same views with server-enforced personal scope. Open appointments can be edited/rescheduled, completed or cancelled. Cancelled/completed appointments remain visible as history.

All inputs and displayed times use the site's timezone shown on the page, even if your device uses another timezone. Ambiguous/nonexistent daylight-saving times are rejected. End must follow start, within seven days; new open appointments must start in the future.

Overlap warnings appear after saving and concern only the user's permitted open appointments. They are advisory, not a reservation lock or a check of colleagues' availability. Queries cover at most 32 days and are capped at 500 candidates with a truncation notice; choose a shorter range when needed.

## Permissions and compatibility

The calendar is personal: it shows private Frappe Events created by the signed-in user, either without a reference or linked to a permitted CRM Lead. Staff still require normal Event permissions and lead access, and lead creation permissions during conversion. This is not a team-wide scheduling view.

Agents can see their own unlinked meetings and appointments linked to leads they created. Changes to lead ownership are checked on every request. Assignment, sharing and other users' calendars do not expand access. Agent APIs return only explicit appointment fields; participants and internal history are omitted.

Events expanded by staff into shared, recurring or externally synchronized events cannot be edited or converted here. Existing staff Event workflows remain available. No custom schema is required.

Pending: drag-and-drop rescheduling, attendees/invitations, no-show outcomes, configurable reminders, recurring appointments, and Google/Outlook synchronization. New events disable standard morning reminders and provider sync; local mail and scheduler remain disabled. Review site-specific automation in staging.

## Validation

35 focused backend tests cover My Day, agent administration, existing agent access, appointment lifecycle, ownership, forged fields, date ranges, overlaps, DST, unlinked meetings, conversion, retries and staff permission checks. The existing 253 frontend tests and production build pass.

Browser checks:

```powershell
node docker/local/meeting-browser.cjs
node docker/local/agent-browser.cjs
```

The first exercises meeting-to-lead conversion as Administrator, a salesperson and an agent, plus the staff lead-page booking entry point. See [agent validation](commission-agents.md) for backend and HTTP regression commands.

Production deployment still requires separate staging and restore verification. The implementation is tracked on dev2; production deployment has not occurred.

Lead Activity now reads linked appointments directly from Event records. Existing bookings and meetings converted to leads appear with their current title, times, location and status. Each Event has one card; both Lead and Event permissions are checked. Rescheduling or cancellation updates that card on the next activity refresh. The browser regression verifies converted meetings and direct bookings in Administrator and salesperson timelines. No backfill is required.

The staff month grid spans six weeks. It loads two bounded 21-day requests without expanding server access or date-range limits, and deduplicates events spanning both requests. Day/week columns separate overlapping appointments. Five unit tests cover calendar boundaries, leap dates, multi-day events and overlap placement. Run `node docker/local/calendar-design-browser.cjs` for view navigation, click-to-book, details, search, status filtering, overlap rendering and mobile checks. This is a design update, not Google Calendar synchronization.


## My Day

Staff: select **My Day** in the CRM sidebar (`/crm/my-day`). Agents: select **My Day** in `/crm-agent`.

- **Today's appointments**: permitted, personal, open meetings overlapping today, including overnight meetings. Open calendar details to reschedule, complete or cancel. Staff can book a new appointment directly from My Day.
- **Overdue follow-ups**: open CRM Tasks due before today. Tasks due earlier today remain in **Due today**.
- **Next 7 days**: tasks due tomorrow through the following seven calendar days. **No due date** keeps unscheduled work visible.
- **New leads**: personal leads still in New status, oldest first. This is based on lead status; it does not infer whether emails or messages were answered.
- **Mark done** completes a task after rechecking access and its last-modified version. **Open lead/deal** opens the permitted linked record. Refresh reloads all groups, counts and the current site date; the page does not update automatically in the background.

Dates and times use the **site timezone** displayed on the page, independently of the browser's timezone. Staff tasks must be assigned to the current user, or created by them with no assignee, and must pass Task and linked Lead/Deal read permissions. Unlinked personal staff tasks are included. Task completion also requires write permission. Staff new leads use `lead_owner` plus normal document permissions.

Agents see only tasks they created that reference leads they created. Assignment alone does not grant access. The restricted API projects only the fields required by My Day, excludes descriptions and unrelated data, and denies suspended users. Existing converted-lead and appointment rules still apply.

Each task group and the lead list checks up to 100 candidates and reports when the scan is limited; appointment queries retain their existing 500-candidate cap. Counts describe displayed permitted records, not global totals. Complete old work or use Tasks, Leads, individual agent lead views and the calendar to access additional records.

My Day requires no new schema, scheduler or outgoing email. Reminders, attendees/invitations, no-show outcomes, drag-and-drop and Google/Outlook synchronization remain separate work. Deploy updated Python/agent assets and rebuild the frontend; reverting those files removes My Day without deleting tasks or appointments. Completed tasks remain completed.

Local validation (2026-10-05): 9 My Day tests plus 18 agent/calendar and 8 administration tests pass; 253 frontend tests, lint (one existing router warning) and production build pass. Browser checks cover Administrator, salesperson and agent task completion, appointment details/booking links, agent API isolation and mobile overflow. Synthetic fixtures are restricted to the muted `crm.localhost` site.

```powershell
docker compose -f docker/local/compose.yaml exec -T backend bash /source/crm/docker/local/test-productivity.sh
docker cp docker/local/seed-productivity.py crm-dev2-backend-1:/workspace/frappe-bench/apps/crm/crm/_dev2_productivity_fixture.py
docker exec -w /workspace/frappe-bench crm-dev2-backend-1 bench --site crm.localhost execute crm._dev2_productivity_fixture.run
node docker/local/productivity-browser.cjs
```

Existing calendar design and agent workspace browser regressions also pass. The calendar smoke check now waits for the save dialog and reload to finish before entering its search filter.


## Light and dark appearance

My Calendar (all views, event states and booking/details dialogs), My Day, agent administration and ERPNext sync use the CRM appearance setting under **Settings > Preferences > Theme**. Native date, select and text controls follow the selected theme too.

Agents choose **Light**, **Dark** or **System** from their account menu in the original CRM interface. The preference persists across reloads and follows operating-system changes when System is selected.

The earlier `node docker/local/theme-browser.cjs` standalone-agent checks need adapting to the shared interface. That script was used to check light/dark surfaces and primary text contrast, calendar event colours and native controls, agent theme persistence/system switching and mobile width. This check reads local synthetic data without saving appointments or changing account access.
