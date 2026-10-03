<template>
  <LayoutHeader>
    <template #left-header
      ><div class="calendar-brand">
        <span class="calendar-mark">{{ today.slice(8) }}</span>
        <h1>{{ __('My calendar') }}</h1>
      </div></template
    >
    <template #right-header
      ><Button
        variant="solid"
        :label="__('Book appointment')"
        :disabled="!timezone"
        iconLeft="plus"
        @click="edit()"
    /></template>
  </LayoutHeader>
  <div class="calendar-shell">
    <aside class="calendar-sidebar" aria-label="Calendar navigation">
      <div class="mini-heading">
        <strong>{{ title }}</strong
        ><button
          aria-label="Previous month"
          @click="chooseDate(shiftMonth(date, -1))"
        >
          ‹</button
        ><button
          aria-label="Next month"
          @click="chooseDate(shiftMonth(date, 1))"
        >
          ›
        </button>
      </div>
      <div class="mini-grid">
        <span v-for="day in weekdays" :key="day" class="mini-weekday">{{
          day[0]
        }}</span>
        <button
          v-for="day in miniDates"
          :key="day"
          :class="{
            muted: day.slice(0, 7) !== date.slice(0, 7),
            today: day === today,
            chosen: day === date,
          }"
          :aria-label="day"
          :aria-current="day === today ? 'date' : undefined"
          @click="chooseDate(day)"
        >
          {{ Number(day.slice(8)) }}
        </button>
      </div>
      <label class="date-picker"
        >{{ __('Go to date')
        }}<input v-model="date" type="date" required @change="load"
      /></label>
      <div class="calendar-legend">
        <h2>{{ __('Show appointments') }}</h2>
        <label
          v-for="status in ['Open', 'Completed', 'Cancelled']"
          :key="status"
          ><input v-model="visibleStatuses" type="checkbox" :value="status" />{{
            __(status)
          }}</label
        >
      </div>
      <div class="calendar-key">
        <p><i class="key-dot linked" />{{ __('Linked to a lead') }}</p>
        <p><i class="key-dot intro" />{{ __('Introduction / no lead yet') }}</p>
      </div>
      <p class="sidebar-tip">
        {{
          __(
            'Meet first, create a lead later. Book an introduction without contact details.',
          )
        }}
      </p>
      <div class="timezone">
        <span class="lucide-globe size-4" />{{
          timezone || __('Loading timezone...')
        }}
      </div>
    </aside>
    <section class="calendar-main" aria-label="Appointments calendar">
      <div class="calendar-toolbar">
        <Button :label="__('Today')" @click="goToday" />
        <div class="nav-arrows">
          <button aria-label="Previous" @click="navigate(-1)">‹</button
          ><button aria-label="Next" @click="navigate(1)">›</button>
        </div>
        <h2>{{ title }}</h2>
        <label class="calendar-search"
          ><span class="lucide-search size-4" /><input
            v-model="search"
            type="search"
            :placeholder="__('Search appointments')"
            :aria-label="__('Search appointments')"
        /></label>
        <label class="view-picker"
          ><span class="sr-only">{{ __('View') }}</span
          ><select v-model="view" :aria-label="__('View')" @change="load">
            <option
              v-for="item in ['Day', 'Week', 'Month', 'Schedule']"
              :key="item"
              :value="item"
            >
              {{ __(item) }}
            </option>
          </select></label
        >
      </div>
      <p
        v-if="error && !mode"
        role="alert"
        class="calendar-banner calendar-error"
      >
        {{ error }}
      </p>
      <p v-if="notice" role="status" class="calendar-banner">{{ notice }}</p>
      <p v-if="truncated" class="calendar-banner">
        {{ __('More appointments exist. Choose a shorter date range.') }}
      </p>
      <div class="calendar-content" :aria-busy="loading">
        <div
          v-if="loading"
          class="loading-line"
          role="status"
          :aria-label="__('Loading appointments')"
        ></div>
        <div v-if="view === 'Month'" class="month-view">
          <div class="month-weekdays">
            <span v-for="day in weekdays" :key="day">{{ __(day) }}</span>
          </div>
          <div class="month-grid">
            <div
              v-for="day in gridDates"
              :key="day"
              class="month-cell"
              :class="{ 'other-month': day.slice(0, 7) !== date.slice(0, 7) }"
            >
              <div class="day-heading">
                <button
                  :class="{ 'today-number': day === today }"
                  :aria-label="__('View day') + ' ' + day"
                  @click="showDay(day)"
                >
                  {{ Number(day.slice(8)) }}</button
                ><button
                  class="add-day"
                  :aria-label="__('Book appointment on') + ' ' + day"
                  @click="bookSlot(day)"
                >
                  +
                </button>
              </div>
              <button
                v-for="row in itemsForDay(day).slice(0, 3)"
                :key="row.name"
                class="month-event"
                :class="eventClass(row)"
                :title="row.subject + ' · ' + row.status"
                @click="openEvent(row)"
              >
                <span>{{
                  row.starts_on.slice(0, 10) === day
                    ? clock(row.starts_on)
                    : '↳'
                }}</span
                ><strong>{{ row.subject }}</strong>
              </button>
              <button
                v-if="itemsForDay(day).length > 3"
                class="more-events"
                @click="showDay(day)"
              >
                +{{ itemsForDay(day).length - 3 }} {{ __('more') }}
              </button>
              <button
                v-if="!itemsForDay(day).length"
                class="empty-day"
                :aria-label="__('Book appointment on') + ' ' + day"
                @click="bookSlot(day)"
              ></button>
            </div>
          </div>
        </div>
        <div v-else-if="view === 'Week' || view === 'Day'" class="time-view">
          <div
            class="time-heading"
            :style="{
              gridTemplateColumns:
                '58px repeat(' + gridDates.length + ', minmax(0, 1fr))',
            }"
          >
            <span class="time-zone-label">{{ __('Time') }}</span
            ><button v-for="day in gridDates" :key="day" @click="showDay(day)">
              <span>{{ weekday(day) }}</span
              ><strong :class="{ 'today-number': day === today }">{{
                Number(day.slice(8))
              }}</strong>
            </button>
          </div>
          <div ref="timeScroller" class="time-scroll">
            <div
              class="time-grid"
              :style="{
                gridTemplateColumns:
                  '58px repeat(' + gridDates.length + ', minmax(0, 1fr))',
              }"
            >
              <div class="hour-labels">
                <span
                  v-for="hour in 24"
                  :key="hour"
                  :style="{ top: (hour - 1) * 60 + 'px' }"
                  >{{ String(hour - 1).padStart(2, '0') }}:00</span
                >
              </div>
              <div v-for="day in gridDates" :key="day" class="time-day">
                <button
                  v-for="slot in 48"
                  :key="slot"
                  class="time-slot"
                  :aria-label="
                    __('Book appointment on') +
                    ' ' +
                    day +
                    ' ' +
                    Math.floor((slot - 1) / 2) +
                    ':' +
                    ((slot - 1) % 2 ? '30' : '00')
                  "
                  @click="
                    bookSlot(
                      day,
                      Math.floor((slot - 1) / 2),
                      ((slot - 1) % 2) * 30,
                    )
                  "
                ></button>
                <button
                  v-for="item in blocks(day)"
                  :key="item.row.name"
                  class="time-event"
                  :class="eventClass(item.row)"
                  :style="item.style"
                  :aria-label="
                    item.row.subject +
                    ' ' +
                    clock(item.row.starts_on) +
                    ' ' +
                    item.row.status
                  "
                  @click="openEvent(item.row)"
                >
                  <strong>{{ item.row.subject }}</strong
                  ><span
                    >{{ clock(item.row.starts_on) }} -
                    {{ clock(item.row.ends_on) }}</span
                  >
                </button>
              </div>
            </div>
          </div>
        </div>
        <div v-else class="schedule-view">
          <p v-if="!visible.length" class="empty-state">
            {{ __('No appointments in this period.') }}
          </p>
          <template v-for="day in gridDates" :key="day"
            ><div v-if="itemsForDay(day).length" class="schedule-day">
              <div class="schedule-date">
                <span>{{ weekday(day) }}</span
                ><strong>{{ day.slice(8) }}</strong
                ><small>{{ day.slice(0, 7) }}</small>
              </div>
              <div class="schedule-entries">
                <article
                  v-for="row in itemsForDay(day)"
                  :key="row.name"
                  class="appointment-card"
                  :class="eventClass(row)"
                >
                  <h2>{{ row.subject }}</h2>
                  <p>
                    {{ row.starts_on }} - {{ row.ends_on }} ·
                    {{ __(row.status) }}
                  </p>
                  <p v-if="row.location">{{ row.location }}</p>
                  <p v-if="!row.reference_docname">{{ __('No lead yet') }}</p>
                  <div class="calendar-controls">
                    <Button
                      :label="__('Details')"
                      @click="openEvent(row)"
                    /><Button
                      v-if="row.reference_docname"
                      :label="__('Open lead')"
                      @click="
                        router.push({
                          name: 'Lead',
                          params: { leadId: row.reference_docname },
                        })
                      "
                    /><template v-if="row.status === 'Open'"
                      ><Button
                        :label="__('Reschedule / edit')"
                        @click="edit(row)" /><Button
                        :label="__('Complete appointment')"
                        :disabled="busy"
                        @click="setStatus(row, 'Completed')" /><Button
                        :label="__('Cancel appointment')"
                        :disabled="busy"
                        @click="setStatus(row, 'Cancelled')" /></template
                    ><Button
                      v-if="
                        !row.reference_docname && row.status === 'Completed'
                      "
                      :label="__('Create lead from meeting')"
                      @click="convert(row)"
                    />
                  </div>
                </article>
              </div></div
          ></template>
        </div>
      </div>
    </section>
    <dialog
      ref="detail"
      class="calendar-dialog event-detail"
      :aria-label="__('Appointment details')"
    >
      <template v-if="detailRow"
        ><div class="detail-top">
          <span class="status-pill" :class="eventClass(detailRow)">{{
            __(detailRow.status)
          }}</span
          ><button :aria-label="__('Close details')" @click="detail.close()">
            ×
          </button>
        </div>
        <h2>{{ detailRow.subject }}</h2>
        <p>{{ detailRow.starts_on }} - {{ detailRow.ends_on }}</p>
        <p class="timezone">{{ timezone }}</p>
        <p v-if="detailRow.location">{{ detailRow.location }}</p>
        <p v-if="!detailRow.reference_docname">{{ __('No lead yet') }}</p>
        <div class="calendar-controls">
          <Button
            v-if="detailRow.reference_docname"
            :label="__('Open lead')"
            @click="
              router.push({
                name: 'Lead',
                params: { leadId: detailRow.reference_docname },
              })
            "
          /><template v-if="detailRow.status === 'Open'"
            ><Button
              :label="__('Reschedule / edit')"
              @click="edit(detailRow)" /><Button
              :label="__('Complete appointment')"
              :disabled="busy"
              @click="setStatus(detailRow, 'Completed')" /><Button
              :label="__('Cancel appointment')"
              :disabled="busy"
              @click="setStatus(detailRow, 'Cancelled')" /></template
          ><Button
            v-if="
              !detailRow.reference_docname && detailRow.status === 'Completed'
            "
            :label="__('Create lead from meeting')"
            @click="convert(detailRow)"
          />
        </div>
        <p v-if="error" role="alert" class="calendar-error">
          {{ error }}
        </p></template
      >
    </dialog>
    <dialog ref="editor" class="calendar-dialog" @close="mode = ''">
      <form @submit.prevent="save">
        <h2 class="text-lg font-semibold">
          {{
            mode === 'convert'
              ? __('Create lead from meeting')
              : __('Book appointment')
          }}
        </h2>
        <p v-if="mode !== 'convert'">
          {{ __('Times in') }} {{ timezone }}.
          {{
            lead ? __('Linked to lead:') + ' ' + lead : __('No lead required.')
          }}
        </p>
        <template v-if="mode === 'convert'">
          <label
            >{{ __('First name')
            }}<input v-model="form.first_name" required maxlength="140"
          /></label>
          <label
            >{{ __('Last name')
            }}<input v-model="form.last_name" maxlength="140"
          /></label>
          <label
            >{{ __('Email')
            }}<input v-model="form.email" type="email" maxlength="140"
          /></label>
          <label
            >{{ __('Mobile') }}<input v-model="form.mobile_no" maxlength="140"
          /></label>
          <label
            >{{ __('Company')
            }}<input v-model="form.organization" maxlength="140"
          /></label>
          <p>
            {{ __('The original meeting will be linked to the new lead.') }}
          </p>
        </template>
        <template v-else>
          <label
            >{{ __('Appointment title')
            }}<input
              v-model="form.subject"
              placeholder="Introduction with walk-in visitor"
              required
              maxlength="140"
          /></label>
          <label
            >{{ __('Starts')
            }}<input v-model="form.starts_on" type="datetime-local" required
          /></label>
          <label
            >{{ __('Ends')
            }}<input v-model="form.ends_on" type="datetime-local" required
          /></label>
          <label
            >{{ __('Location or meeting URL')
            }}<input v-model="form.location" maxlength="140"
          /></label>
        </template>
        <p v-if="error" role="alert" class="calendar-error">{{ error }}</p>
        <div class="calendar-controls">
          <Button
            type="button"
            :label="__('Close')"
            :disabled="busy"
            @click="editor.close()"
          /><Button
            type="submit"
            variant="solid"
            :loading="busy"
            :label="__('Save')"
          />
        </div>
      </form>
    </dialog>
  </div>
</template>

<script setup>
import { ref, computed, nextTick, onMounted } from 'vue'
import {
  shiftDate,
  shiftMonth,
  calendarRange,
  datesBetween,
  dayEvents,
  timeLayout,
} from '@/utils/calendar'
import { useRoute, useRouter } from 'vue-router'
import { Button, call } from 'frappe-ui'
import LayoutHeader from '@/components/LayoutHeader.vue'

const router = useRouter()
const route = useRoute()
const appointments = ref([])
const date = ref(new Date().toISOString().slice(0, 10))
const view = ref('Month')
const search = ref('')
const visibleStatuses = ref(['Open', 'Completed', 'Cancelled'])
const today = ref(date.value)
const detail = ref(null)
const detailRow = ref(null)
const timeScroller = ref(null)
let loadId = 0
const range = computed(() => calendarRange(date.value, view.value))
const gridDates = computed(() =>
  datesBetween(range.value.start, range.value.end),
)
const miniDates = computed(() => {
  const r = calendarRange(date.value, 'Month')
  return datesBetween(r.start, r.end)
})
const weekdays = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']
const visible = computed(() =>
  appointments.value.filter(
    (row) =>
      visibleStatuses.value.includes(row.status) &&
      [row.subject, row.location]
        .join(' ')
        .toLowerCase()
        .includes(search.value.toLowerCase()),
  ),
)
const title = computed(() =>
  new Intl.DateTimeFormat(undefined, {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(new Date(date.value + 'T12:00:00Z')),
)
const itemsForDay = (value) => dayEvents(visible.value, value)
const blocks = (value) => timeLayout(visible.value, value)
const clock = (value) => value?.slice(11, 16) || ''
const weekday = (value) =>
  new Intl.DateTimeFormat(undefined, {
    weekday: 'short',
    timeZone: 'UTC',
  }).format(new Date(value + 'T12:00:00Z'))
const eventClass = (row) =>
  row.status === 'Cancelled'
    ? 'cancelled'
    : row.status === 'Completed'
      ? 'completed'
      : row.reference_docname
        ? 'linked'
        : 'intro'
function openEvent(row) {
  detailRow.value = row
  detail.value.showModal()
}
async function chooseDate(value) {
  date.value = value
  await load()
}
async function showDay(value) {
  view.value = 'Day'
  await chooseDate(value)
}
async function goToday() {
  await chooseDate(today.value)
}
function bookSlot(value, hour = 9, minute = 0) {
  edit()
  const start = `${value}T${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`
  form.value.starts_on = start
  form.value.ends_on =
    hour === 23 && minute === 30
      ? `${shiftDate(value, 1)}T00:00`
      : `${value}T${String(hour + (minute === 30 ? 1 : 0)).padStart(2, '0')}:${minute === 30 ? '00' : '30'}`
}
const timezone = ref('')
const loading = ref(false)
const busy = ref(false)
const error = ref('')
const notice = ref('')
const truncated = ref(false)
const editor = ref(null)
const mode = ref('')
const form = ref({})
const selected = ref(null)
const lead = ref(null)
const api = (method, args) => call('crm.api.appointments.' + method, args)
function failed(err) {
  error.value =
    err.messages?.[0] ||
    err.message ||
    __('Unable to save or load this appointment.')
}
async function load() {
  if (!date.value) return
  const id = ++loadId
  loading.value = true
  error.value = ''
  try {
    // Full month grids span 42 days; retain the server's 32-day request limit.
    const { start, end } = range.value
    const ranges = []
    for (let cursor = start; cursor < end; cursor = shiftDate(cursor, 21)) {
      const next = shiftDate(cursor, 21)
      ranges.push({
        start: cursor + 'T00:00:00',
        end: (next < end ? next : end) + 'T00:00:00',
      })
    }
    const results = await Promise.all(
      ranges.map((args) => api('list_appointments', args)),
    )
    if (id !== loadId) return
    appointments.value = [
      ...new Map(
        results
          .flatMap((result) => result.appointments)
          .map((row) => [row.name, row]),
      ).values(),
    ]
    timezone.value = results[0].time_zone
    truncated.value = results.some((result) => result.truncated)
    if (detailRow.value)
      detailRow.value =
        appointments.value.find((row) => row.name === detailRow.value.name) ||
        detailRow.value
    await nextTick()
    if (timeScroller.value) timeScroller.value.scrollTop = 8 * 60
  } catch (err) {
    if (id === loadId) {
      appointments.value = []
      failed(err)
    }
  } finally {
    if (id === loadId) loading.value = false
  }
}
async function navigate(direction) {
  date.value =
    view.value === 'Month'
      ? shiftMonth(date.value, direction)
      : shiftDate(
          date.value,
          direction *
            (view.value === 'Day' ? 1 : view.value === 'Week' ? 7 : 31),
        )
  await load()
}
function edit(row = null) {
  detail.value?.close()
  selected.value = row
  lead.value =
    row?.reference_docname ||
    (typeof route.query.lead === 'string' ? route.query.lead : null)
  form.value = {
    subject: row?.subject || '',
    starts_on: row?.starts_on?.replace(' ', 'T').slice(0, 16) || '',
    ends_on: row?.ends_on?.replace(' ', 'T').slice(0, 16) || '',
    location: row?.location || '',
  }
  error.value = ''
  mode.value = 'appointment'
  editor.value.showModal()
}
function convert(row) {
  detail.value?.close()
  selected.value = row
  form.value = {
    first_name: '',
    last_name: '',
    email: '',
    mobile_no: '',
    organization: '',
  }
  error.value = ''
  mode.value = 'convert'
  editor.value.showModal()
}
async function save() {
  if (busy.value) return
  busy.value = true
  error.value = ''
  try {
    if (mode.value === 'convert') {
      const result = await api('convert_to_lead', {
        name: selected.value.name,
        data: form.value,
      })
      notice.value = __('Meeting linked to lead:') + ' ' + result.lead
    } else {
      const result = await api('save_appointment', {
        name: selected.value?.name || null,
        lead: lead.value,
        data: form.value,
      })
      date.value = form.value.starts_on.slice(0, 10)
      notice.value = result.conflict
        ? __('Saved. This overlaps another appointment in your calendar.')
        : __('Appointment saved.')
    }
    editor.value.close()
    await load()
  } catch (err) {
    failed(err)
  } finally {
    busy.value = false
  }
}
async function setStatus(row, status) {
  busy.value = true
  error.value = ''
  try {
    await api('save_appointment', {
      name: row.name,
      lead: row.reference_docname || null,
      data: { status },
    })
    await load()
  } catch (err) {
    failed(err)
  } finally {
    busy.value = false
  }
}
onMounted(async () => {
  await load()
  if (timezone.value) {
    const parts = new Intl.DateTimeFormat('en-CA', {
      timeZone: timezone.value,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).formatToParts(new Date())
    date.value = ['year', 'month', 'day']
      .map((type) => parts.find((part) => part.type === type).value)
      .join('-')
    today.value = date.value
    await load()
  }
  if (route.query.lead && !error.value) edit()
})
</script>

<style scoped>
.calendar-brand {
  display: flex;
  gap: 10px;
  align-items: center;
  font-size: 18px;
  font-weight: 500;
}
.calendar-mark {
  display: grid;
  place-items: center;
  width: 28px;
  height: 28px;
  border-radius: 6px;
  border-top: 6px solid #4285f4;
  color: #1967d2;
  background: #e8f0fe;
  font-size: 15px;
}
.calendar-shell {
  --cal-border: var(--outline-gray-2, #e2e5e9);
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
  color: var(--ink-gray-8, #343941);
  background: var(--surface-white, #fff);
}
.calendar-sidebar {
  width: 220px;
  flex-shrink: 0;
  padding: 24px 18px;
  border-right: 1px solid var(--cal-border);
  overflow: auto;
}
.mini-heading {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-bottom: 16px;
  font-size: 13px;
}
.mini-heading strong {
  flex: 1;
}
.mini-heading button,
.nav-arrows button {
  width: 28px;
  height: 30px;
  border-radius: 50%;
  font-size: 24px;
}
.mini-heading button:hover,
.nav-arrows button:hover {
  background: var(--surface-gray-2, #f1f3f4);
}
.mini-grid {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  gap: 3px;
  text-align: center;
  font-size: 11px;
}
.mini-grid button {
  height: 24px;
  border-radius: 50%;
}
.mini-weekday {
  color: var(--ink-gray-5, #69717b);
  padding: 4px 0;
}
.mini-grid .chosen {
  background: #d3e3fd;
  color: #174ea6;
}
.mini-grid .today {
  background: #1967d2;
  color: white;
}
.mini-grid .muted {
  opacity: 0.45;
}
.date-picker {
  margin: 24px 0;
}
.calendar-legend {
  border-top: 1px solid var(--cal-border);
  padding-top: 20px;
}
.calendar-legend h2 {
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 16px;
}
.calendar-legend label {
  display: flex;
  align-items: center;
  gap: 10px;
  margin: 14px 0;
}
.calendar-legend input {
  appearance: auto;
  padding: 0;
  background: revert;
  accent-color: #1967d2;
  width: 15px;
  height: 15px;
}
.calendar-key {
  margin-top: 24px;
  font-size: 11px;
}
.calendar-key p {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: 12px 0;
}
.key-dot {
  width: 9px;
  height: 9px;
  border-radius: 50%;
}
.key-dot.linked {
  background: #4285f4;
}
.key-dot.intro {
  background: #8b5cf6;
}
.sidebar-tip {
  font-size: 12px;
  line-height: 1.6;
  color: var(--ink-gray-5, #69717b);
  margin: 24px 0;
}
.timezone {
  display: flex;
  gap: 7px;
  align-items: center;
  font-size: 11px;
  color: var(--ink-gray-5, #69717b);
}
.calendar-main {
  flex: 1;
  min-width: 0;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.calendar-toolbar {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 12px;
  padding: 18px 20px;
  border-bottom: 1px solid var(--cal-border);
}
.calendar-toolbar h2 {
  font-size: 22px;
  font-weight: 500;
  letter-spacing: -0.4px;
  margin-right: auto;
}
.nav-arrows {
  display: flex;
}
.calendar-search {
  display: flex;
  align-items: center;
  gap: 8px;
  max-width: 190px;
}
.calendar-search input {
  border: 0;
  min-width: 0;
  width: 100%;
  background: transparent;
}
.view-picker select {
  min-width: 100px;
}
.calendar-banner {
  font-size: 13px;
  padding: 10px 20px;
  background: var(--surface-gray-1, #f8fafd);
}
.calendar-content {
  position: relative;
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
}
.loading-line {
  height: 3px;
  width: 100%;
  position: absolute;
  z-index: 5;
  top: 0;
  background: linear-gradient(90deg, transparent, #4285f4, transparent);
}
.month-view {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  overflow: auto;
}
.month-weekdays {
  display: grid;
  grid-template-columns: repeat(7, 1fr);
  text-align: center;
  font-size: 11px;
  text-transform: uppercase;
  color: var(--ink-gray-5, #69717b);
  padding: 12px 0;
}
.month-grid {
  display: grid;
  grid-template-columns: repeat(7, minmax(0, 1fr));
  grid-template-rows: repeat(6, minmax(95px, 1fr));
  flex: 1;
}
.month-cell {
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--cal-border);
  border-right: 1px solid var(--cal-border);
  padding: 4px;
  min-width: 0;
}
.month-cell:nth-child(7n) {
  border-right: 0;
}
.other-month {
  background: var(--surface-gray-1, #fafbfc);
}
.other-month .day-heading {
  opacity: 0.45;
}
.day-heading {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 4px;
}
.day-heading button {
  width: 26px;
  height: 26px;
  border-radius: 50%;
  font-size: 12px;
}
.today-number {
  background: #1967d2;
  color: white;
  border-radius: 50%;
}
.add-day {
  opacity: 0;
}
.month-cell:hover .add-day,
.add-day:focus-visible {
  opacity: 1;
}
.empty-day {
  flex: 1;
  min-height: 26px;
  border-radius: 4px;
}
.empty-day:hover {
  background: #4285f40a;
}
.month-event {
  display: flex;
  align-items: center;
  gap: 5px;
  width: 100%;
  margin: 2px 0;
  padding: 4px 6px;
  border-radius: 4px;
  font-size: 11px;
  text-align: left;
}
.month-event span {
  font-size: 10px;
  flex-shrink: 0;
}
.month-event strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-weight: 500;
}
.linked {
  background: #d3e3fd;
  color: #174ea6;
}
.intro {
  background: #ede2fc;
  color: #6236a0;
}
.completed {
  background: #d5eddf;
  color: #17633f;
}
.cancelled {
  background: var(--surface-gray-2, #edf0f2);
  color: var(--ink-gray-5, #69717b);
  text-decoration: line-through;
}
.more-events {
  text-align: left;
  font-size: 11px;
  padding: 4px 6px;
  color: var(--ink-gray-5, #69717b);
}
.time-view {
  display: flex;
  flex: 1;
  min-height: 0;
  flex-direction: column;
}
.time-heading {
  display: grid;
  border-bottom: 1px solid var(--cal-border);
  padding-right: 12px;
}
.time-heading button {
  display: grid;
  justify-items: center;
  gap: 5px;
  padding: 12px;
  border-left: 1px solid var(--cal-border);
}
.time-heading button span {
  font-size: 11px;
  text-transform: uppercase;
}
.time-heading strong {
  font-size: 24px;
  font-weight: 400;
  display: grid;
  place-items: center;
  width: 38px;
  height: 38px;
}
.time-zone-label {
  align-self: end;
  font-size: 10px;
  padding: 8px;
}
.time-scroll {
  overflow: auto;
  flex: 1;
  min-height: 0;
}
.time-grid {
  display: grid;
  height: 1440px;
}
.hour-labels {
  position: relative;
}
.hour-labels span {
  position: absolute;
  right: 8px;
  font-size: 10px;
  color: var(--ink-gray-5, #69717b);
}
.time-day {
  position: relative;
  border-left: 1px solid var(--cal-border);
}
.time-slot {
  display: block;
  width: 100%;
  height: 30px;
  border-top: 1px dotted var(--cal-border);
}
.time-slot:nth-child(odd) {
  border-top-style: solid;
}
.time-slot:hover {
  background: #4285f410;
}
.time-event {
  position: absolute;
  border-radius: 5px;
  padding: 3px 6px;
  text-align: left;
  overflow: hidden;
  border-left: 3px solid currentColor;
  display: flex;
  flex-direction: column;
  gap: 4px;
  font-size: 11px;
}
.time-event strong {
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex-shrink: 0;
  font-weight: 600;
}
.time-event span {
  font-size: 10px;
}
.schedule-view {
  overflow: auto;
  padding: 12px 24px;
}
.schedule-day {
  display: flex;
  gap: 24px;
  border-bottom: 1px solid var(--cal-border);
  padding: 20px 0;
}
.schedule-date {
  min-width: 64px;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 4px;
  font-size: 11px;
}
.schedule-date strong {
  font-size: 28px;
  font-weight: 400;
}
.schedule-entries {
  flex: 1;
  min-width: 0;
}
.appointment-card {
  padding: 16px;
  margin-bottom: 10px;
  border-radius: 10px;
  display: grid;
  gap: 10px;
  font-size: 13px;
  text-decoration: none;
}
.appointment-card h2 {
  font-weight: 600;
}
.empty-state {
  text-align: center;
  padding: 60px 0;
  color: var(--ink-gray-5, #69717b);
}
.calendar-controls {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
  align-items: center;
}
label {
  display: grid;
  gap: 6px;
  font-size: 13px;
}
input,
select {
  border: 1px solid var(--cal-border, var(--outline-gray-2, #ddd));
  border-radius: 6px;
  padding: 8px;
  color: inherit;
  background: var(--surface-white, #fff);
}
button:focus-visible {
  outline: 2px solid #4285f4;
  outline-offset: 2px;
}
.calendar-dialog {
  width: min(440px, 94vw);
  max-height: 90vh;
  overflow: auto;
  padding: 24px;
  border-radius: 14px;
  color: var(--ink-gray-8, #343941);
  background: var(--surface-white, #fff);
  box-shadow: 0 12px 50px #0003;
}
.calendar-dialog::backdrop {
  background: #15223855;
}
.calendar-dialog form {
  display: grid;
  gap: 16px;
}
.calendar-dialog p {
  font-size: 13px;
  line-height: 1.6;
}
.calendar-error {
  color: var(--ink-red-5, #b91c1c);
}
.event-detail h2 {
  font-size: 22px;
  font-weight: 500;
  margin: 16px 0;
}
.event-detail p {
  margin: 12px 0;
}
.detail-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.detail-top button {
  font-size: 24px;
  width: 30px;
}
.status-pill {
  padding: 5px 10px;
  border-radius: 20px;
  font-size: 11px;
}
.event-detail .calendar-controls {
  margin-top: 22px;
}
@media (max-width: 1100px) {
  .calendar-sidebar {
    width: 184px;
    padding: 20px 12px;
  }
  .calendar-search {
    max-width: 150px;
  }
  .calendar-toolbar {
    gap: 8px;
    padding: 14px;
  }
  .calendar-toolbar h2 {
    font-size: 18px;
  }
}
@media (max-width: 800px) {
  .calendar-sidebar {
    display: none;
  }
  .calendar-toolbar h2 {
    order: -1;
    width: 100%;
  }
  .calendar-search {
    margin-left: auto;
  }
  .month-grid {
    grid-template-rows: repeat(6, minmax(100px, 1fr));
  }
  .month-event {
    gap: 2px;
    padding: 4px 2px;
    font-size: 10px;
  }
  .month-event span {
    display: none;
  }
  .month-cell {
    padding: 2px;
  }
  .add-day {
    opacity: 1;
  }
  .time-heading button {
    padding: 8px 0;
  }
  .time-heading strong {
    font-size: 20px;
  }
  .time-event {
    padding: 2px;
    font-size: 10px;
  }
  .schedule-view {
    padding: 12px;
  }
  .schedule-day {
    gap: 10px;
  }
}
</style>
