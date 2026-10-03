/* global document, window, fetch */
const apiRoot = "/api/method/crm.api.agent.";
const csrf = document.querySelector('meta[name="csrf-token"]').content;
const byId = (id) => document.getElementById(id);
let view = "leads";
let offset = 0;
let currentLead = null;
let saveEditor = null;

function text(tag, value, parent, className) {
  const el = document.createElement(tag);
  el.textContent = value ?? "";
  if (className) el.className = className;
  parent?.append(el);
  return el;
}
function action(label, fn, parent) {
  const button = text("button", label, parent);
  button.type = "button";
  button.onclick = () => run(fn);
  return button;
}
async function call(method, values = {}, write = false) {
  const response = await fetch(
    apiRoot + method + (write ? "" : "?" + new URLSearchParams(values)),
    {
      method: write ? "POST" : "GET",
      headers: {
        "Content-Type": "application/json",
        "X-Frappe-CSRF-Token": csrf,
      },
      ...(write ? { body: JSON.stringify(values) } : {}),
    },
  );
  const result = await response.json();
  if (!response.ok)
    throw new Error(
      response.status === 403
        ? "You do not have access to this record or action."
        : "Unable to save or load. Check the fields and try again.",
    );
  return result.message;
}
async function run(fn) {
  byId("message").textContent = "";
  byId("message").className = "";
  try {
    await fn();
  } catch (error) {
    byId("message").textContent = error.message;
    byId("editor-error").textContent = error.message;
    byId("message").className = "error";
  }
}
async function loadList() {
  if (view === "calendar") return loadCalendar();
  const rows = await call(view === "leads" ? "list_leads" : "list_contacts", {
    start: offset,
    query: byId("search").value,
  });
  byId("list-title").textContent =
    view === "leads" ? "My leads" : "My contacts";
  byId("search-form").hidden = view !== "leads";
  byId("records").replaceChildren();
  rows.forEach((row) => {
    const label = [row.first_name, row.last_name].filter(Boolean).join(" ");
    const button = action(
      label + (row.status ? " · " + row.status : ""),
      () => (view === "leads" ? loadLead(row.name) : showContact(row)),
      byId("records"),
    );
    button.className = "record";
  });
  if (!rows.length) text("p", "No records found.", byId("records"));
  byId("previous").disabled = offset === 0;
  byId("next").disabled = rows.length < 25;
}
function details(row, fields, parent) {
  const list = text("dl", "", parent);
  fields.forEach(([key, label]) => {
    text("dt", label, list);
    text("dd", row[key] || "—", list);
  });
}
function showContact(row) {
  currentLead = null;
  const panel = byId("detail");
  panel.replaceChildren();
  text("h2", [row.first_name, row.last_name].filter(Boolean).join(" "), panel);
  details(
    row,
    [
      ["email_id", "Email"],
      ["mobile_no", "Mobile"],
      ["phone", "Phone"],
    ],
    panel,
  );
}
async function loadLead(name) {
  const data = await call("get_lead", { name });
  currentLead = name;
  const panel = byId("detail");
  panel.replaceChildren();
  text(
    "h2",
    [data.lead.first_name, data.lead.last_name].filter(Boolean).join(" "),
    panel,
  );
  details(
    data.lead,
    [
      ["status", "Status"],
      ["organization", "Company"],
      ["email", "Email"],
      ["mobile_no", "Mobile"],
    ],
    panel,
  );
  if (!data.lead.converted)
    action("Edit lead", () => editLead(data.lead, data.statuses), panel);
  action("Book appointment", () => editAppointment(name), panel);
  text("h3", "Linked contacts", panel);
  data.contacts.forEach((row) =>
    text(
      "p",
      [row.first_name, row.last_name, row.email_id, row.mobile_no]
        .filter(Boolean)
        .join(" · "),
      panel,
    ),
  );
  if (!data.contacts.length)
    text("p", "No contacts linked yet.", panel, "muted");
  action("Add contact", () => editContact(name), panel);
  text("h3", "My follow-ups", panel);
  data.follow_ups.forEach((task) => {
    const item = text(
      "p",
      task.title +
        " · " +
        task.status +
        (task.due_date ? " · " + task.due_date : ""),
      panel,
    );
    if (task.status !== "Done")
      action(
        "Mark done",
        async () => {
          await call("complete_follow_up", { name: task.name }, true);
          await loadLead(name);
        },
        item,
      );
  });
  action(
    "Add follow-up",
    () =>
      openEditor(
        "New follow-up",
        [
          ["title", "What needs doing?", "text", true],
          ["due_date", "Due (site timezone)", "datetime-local"],
        ],
        {},
        async (values) => {
          await call("add_follow_up", { lead: name, ...values }, true);
          await loadLead(name);
        },
      ),
    panel,
  );
}
function openEditor(title, fields, values, save) {
  byId("editor-title").textContent = title;
  byId("editor-error").textContent = "";
  byId("editor-fields").replaceChildren();
  fields.forEach(([key, label, type = "text", required = false, options]) => {
    const wrapper = text("label", label, byId("editor-fields"));
    const input = document.createElement(options ? "select" : "input");
    input.name = key;
    if (options)
      options.forEach((option) => {
        const el = text("option", option, input);
        el.value = option;
      });
    else {
      input.type = type;
      input.maxLength = key === "title" ? 140 : 500;
    }
    input.required = required;
    input.value = values[key] || "";
    wrapper.append(input);
  });
  saveEditor = save;
  byId("editor").showModal();
}
function editLead(
  row = {},
  statuses = ["New", "Contacted", "Nurture", "Qualified"],
) {
  openEditor(
    row.name ? "Edit lead" : "New lead",
    [
      ["first_name", "First name", "text", true],
      ["last_name", "Last name"],
      ["email", "Email", "email"],
      ["mobile_no", "Mobile"],
      ["organization", "Company"],
      ["job_title", "Job title"],
      ["status", "Status", "text", true, statuses],
    ],
    { status: "New", ...row },
    async (values) => {
      const saved = await call(
        "save_lead",
        { data: values, name: row.name || null },
        true,
      );
      view = "leads";
      offset = 0;
      await loadList();
      await loadLead(saved.name);
    },
  );
}
function editContact(lead = null) {
  openEditor(
    "New contact",
    [
      ["first_name", "First name", "text", true],
      ["last_name", "Last name"],
      ["email", "Email", "email"],
      ["mobile_no", "Mobile"],
    ],
    {},
    async (values) => {
      await call("save_contact", { data: values, lead }, true);
      if (lead) await loadLead(lead);
      await loadList();
    },
  );
}
byId("edit-form").onsubmit = (event) => {
  event.preventDefault();
  run(async () => {
    byId("save").disabled = true;
    try {
      await saveEditor(Object.fromEntries(new FormData(event.target)));
      byId("editor").close();
    } finally {
      byId("save").disabled = false;
    }
  });
};
byId("cancel").onclick = () => byId("editor").close();
byId("new-lead").onclick = () => editLead();
byId("new-contact").onclick = () => editContact(currentLead);
byId("leads-tab").onclick = () =>
  run(async () => {
    view = "leads";
    offset = 0;
    await loadList();
  });
byId("contacts-tab").onclick = () =>
  run(async () => {
    view = "contacts";
    offset = 0;
    currentLead = null;
    await loadList();
  });
byId("search-form").onsubmit = (event) => {
  event.preventDefault();
  offset = 0;
  run(loadList);
};
byId("previous").onclick = () => {
  offset = Math.max(0, offset - 25);
  run(loadList);
};
byId("next").onclick = () => {
  offset += 25;
  run(loadList);
};
byId("logout").onclick = () =>
  run(async () => {
    const response = await fetch("/api/method/logout", {
      method: "POST",
      headers: { "X-Frappe-CSRF-Token": csrf },
    });
    if (!response.ok) throw new Error("Sign out failed. Please try again.");
    window.location.assign("/login");
  });
run(loadList);

const siteTimezone = document.querySelector(
  'meta[name="site-timezone"]',
).content;
// Calendar arithmetic uses date-only UTC values; displayed appointment times are site-local.
const siteToday = new Intl.DateTimeFormat("en-CA", {
  timeZone: siteTimezone,
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
}).formatToParts(new Date());
const datePart = (type) => siteToday.find((part) => part.type === type).value;
let calendarDate = `${datePart("year")}-${datePart("month")}-${datePart("day")}`;
let calendarDays = 7;
function shiftDate(value, days) {
  const date = new Date(value + "T12:00:00Z");
  date.setUTCDate(date.getUTCDate() + days);
  return date.toISOString().slice(0, 10);
}
async function loadCalendar() {
  currentLead = null;
  byId("search-form").hidden = true;
  byId("list-title").textContent = "My calendar";
  byId("previous").disabled = false;
  byId("next").disabled = false;
  const records = byId("records");
  records.replaceChildren();
  const label = text("label", "Starting date", records);
  const input = document.createElement("input");
  input.type = "date";
  input.value = calendarDate;
  input.onchange = () => {
    if (!input.value) return;
    calendarDate = input.value;
    run(loadCalendar);
  };
  label.append(input);
  const controls = text("div", "", records);
  for (const [label, days] of [
    ["Day", 1],
    ["Week", 7],
    ["Month (31 days)", 31],
  ]) {
    action(
      label,
      async () => {
        calendarDays = days;
        await loadCalendar();
      },
      controls,
    );
  }
  const end = shiftDate(calendarDate, calendarDays);
  const data = await call("list_appointments", {
    start: calendarDate + "T00:00:00",
    end: end + "T00:00:00",
  });
  text(
    "p",
    `Times in ${data.time_zone}. ${calendarDate} to ${shiftDate(end, -1)}.`,
    records,
  );
  text(
    "p",
    "Book a meeting without a lead, or open a lead and choose Book appointment. After completing a meeting, you can create its lead.",
    records,
  );
  if (data.truncated)
    text("p", "More than 500 appointments: select a shorter range.", records);
  const panel = byId("detail");
  panel.replaceChildren();
  text("h2", "Appointments", panel);
  if (!data.appointments.length)
    text("p", "No appointments in this period.", panel);
  data.appointments.forEach((row) => {
    const card = text("article", "", panel, "appointment");
    text("h3", row.subject, card);
    text("p", `${row.starts_on} - ${row.ends_on} (${row.status})`, card);
    if (row.location) text("p", row.location, card);
    if (row.reference_docname)
      action(
        "Open lead",
        async () => {
          view = "leads";
          offset = 0;
          await loadList();
          await loadLead(row.reference_docname);
        },
        card,
      );
    if (!row.reference_docname) {
      text("p", "No lead yet", card);
      if (row.status === "Completed")
        action("Create lead from meeting", () => convertMeeting(row), card);
    }
    if (row.status === "Open") {
      action(
        "Reschedule / edit",
        () => editAppointment(row.reference_docname, row),
        card,
      );
      for (const [label, status] of [
        ["Complete appointment", "Completed"],
        ["Cancel appointment", "Cancelled"],
      ]) {
        action(
          label,
          async () => {
            await call(
              "save_appointment",
              { lead: row.reference_docname, name: row.name, data: { status } },
              true,
            );
            await loadCalendar();
          },
          card,
        );
      }
    }
  });
}
function editAppointment(lead, row = {}) {
  openEditor(
    row.name ? "Edit appointment" : "New appointment",
    [
      ["subject", "Appointment title", "text", true],
      ["starts_on", `Starts (${siteTimezone})`, "datetime-local", true],
      ["ends_on", `Ends (${siteTimezone})`, "datetime-local", true],
      ["location", "Location or meeting URL"],
    ],
    {
      ...row,
      starts_on: row.starts_on?.replace(" ", "T").slice(0, 16),
      ends_on: row.ends_on?.replace(" ", "T").slice(0, 16),
    },
    async (values) => {
      const result = await call(
        "save_appointment",
        { lead, name: row.name || null, data: values },
        true,
      );
      view = "calendar";
      calendarDate = values.starts_on.slice(0, 10);
      await loadCalendar();
      if (result.conflict)
        byId("message").textContent =
          "Appointment saved. It overlaps another appointment in your calendar.";
    },
  );
}
byId("calendar-tab").onclick = () =>
  run(async () => {
    view = "calendar";
    await loadCalendar();
  });
const previousPage = byId("previous").onclick;
const nextPage = byId("next").onclick;
byId("previous").onclick = () => {
  if (view !== "calendar") return previousPage();
  calendarDate = shiftDate(calendarDate, -calendarDays);
  run(loadCalendar);
};
byId("next").onclick = () => {
  if (view !== "calendar") return nextPage();
  calendarDate = shiftDate(calendarDate, calendarDays);
  run(loadCalendar);
};

byId("new-meeting").onclick = () => editAppointment(null);
function convertMeeting(row) {
  openEditor(
    "Create lead from meeting",
    [
      ["first_name", "First name", "text", true],
      ["last_name", "Last name"],
      ["email", "Email", "email"],
      ["mobile_no", "Mobile"],
      ["organization", "Company"],
    ],
    {},
    async (values) => {
      const result = await call(
        "convert_appointment_to_lead",
        { name: row.name, data: values },
        true,
      );
      await loadCalendar();
      byId("message").textContent = "Meeting linked to lead: " + result.lead;
    },
  );
}
