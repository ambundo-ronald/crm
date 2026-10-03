# Calendar appointments and meetings before leads

Available locally on dev2:

- Staff and Administrator: **My calendar** in the CRM sidebar, or http://localhost:18000/crm/appointments.
- Staff lead page: **Book appointment** opens the calendar with that lead selected.
- Commission agents: http://localhost:18000/crm-agent, **My calendar**, or **Book meeting (no lead)**.

## Meet someone before creating a lead

1. Choose **Book appointment** in the staff calendar, or **Book meeting (no lead)** in the agent workspace.
2. Use a title such as "Introduction with walk-in visitor". A name, email address and lead are not required at booking time.
3. Enter the start/end and optional location or meeting URL, then save.
4. After the meeting, choose **Complete appointment**.
5. Choose **Create lead from meeting**, enter the person's name and any contact details, and save.

The original Event remains in the calendar with its title, times and completed status. Its reference points to the new CRM Lead, and **Open lead** opens that lead. Conversion sets the lead creator to the booking user. Repeating conversion on the same meeting returns the existing lead; a row lock prevents concurrent conversion from creating another lead. Different meetings are not automatically deduplicated into one person. Linking to an already-existing lead after a meeting is a separate future improvement.

To book against an existing lead, use **Book appointment** on that lead instead.

## Calendar behavior

The staff calendar has Google Calendar-inspired Month, Week, Day and Schedule views. Use the mini calendar, Today button and arrows to navigate. Click a date or half-hour slot to book; click an event for its details and actions. Search and status filters apply to the loaded period. Linked-lead meetings are blue, introductions purple, completed meetings green and cancelled meetings grey. The agent workspace retains its simpler day/week/31-day agenda. Open appointments can be edited/rescheduled, completed or cancelled. Cancelled/completed appointments remain visible as history.

All inputs and displayed times use the site's timezone shown on the page, even if your device uses another timezone. Ambiguous/nonexistent daylight-saving times are rejected. End must follow start, within seven days; new open appointments must start in the future.

Overlap warnings appear after saving and concern only the user's permitted open appointments. They are advisory, not a reservation lock or a check of colleagues' availability. Queries cover at most 32 days and are capped at 500 candidates with a truncation notice; choose a shorter range when needed.

## Permissions and compatibility

The calendar is personal: it shows private Frappe Events created by the signed-in user, either without a reference or linked to a permitted CRM Lead. Staff still require normal Event permissions and lead access, and lead creation permissions during conversion. This is not a team-wide scheduling view.

Agents can see their own unlinked meetings and appointments linked to leads they created. Changes to lead ownership are checked on every request. Assignment, sharing and other users' calendars do not expand access. Agent APIs return only explicit appointment fields; participants and internal history are omitted.

Events expanded by staff into shared, recurring or externally synchronized events cannot be edited or converted here. Existing staff Event workflows remain available. No custom schema is required.

Pending: drag-and-drop rescheduling, My Day aggregation, attendees/invitations, no-show outcomes, configurable reminders, recurring appointments, and Google/Outlook synchronization. New events disable standard morning reminders and provider sync; local mail and scheduler remain disabled. Review site-specific automation in staging.

## Validation

18 backend tests cover existing agent access, appointment lifecycle, ownership, forged fields, date ranges, overlaps, DST, unlinked meetings, conversion, retries and staff permission checks. The existing 253 frontend tests and production build pass.

Browser checks:

```powershell
node docker/local/meeting-browser.cjs
node docker/local/agent-browser.cjs
```

The first exercises meeting-to-lead conversion as Administrator, a salesperson and an agent, plus the staff lead-page booking entry point. See [agent validation](commission-agents.md) for backend and HTTP regression commands.

Production deployment still requires separate staging and restore verification. The implementation is tracked on dev2; production deployment has not occurred.

Lead Activity now reads linked appointments directly from Event records. Existing bookings and meetings converted to leads appear with their current title, times, location and status. Each Event has one card; both Lead and Event permissions are checked. Rescheduling or cancellation updates that card on the next activity refresh. The browser regression verifies converted meetings and direct bookings in Administrator and salesperson timelines. No backfill is required.

The staff month grid spans six weeks. It loads two bounded 21-day requests without expanding server access or date-range limits, and deduplicates events spanning both requests. Day/week columns separate overlapping appointments. Five unit tests cover calendar boundaries, leap dates, multi-day events and overlap placement. Run `node docker/local/calendar-design-browser.cjs` for view navigation, click-to-book, details, search, status filtering, overlap rendering and mobile checks. This is a design update, not Google Calendar synchronization.
