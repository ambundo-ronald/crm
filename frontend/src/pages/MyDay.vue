<template>
  <LayoutHeader>
    <template #left-header
      ><h1 class="text-lg font-semibold text-ink-gray-9">
        {{ __('My Day') }}
      </h1></template
    >
    <template #right-header
      ><Button :disabled="busy" @click="load">{{
        __('Refresh')
      }}</Button></template
    >
  </LayoutHeader>
  <main
    class="flex-1 overflow-auto text-ink-gray-8 bg-surface-gray-1 p-4 sm:p-6"
  >
    <div class="mx-auto max-w-6xl space-y-6">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h2 class="text-2xl font-semibold text-ink-gray-9">
            {{ __('Your daily focus') }}
          </h2>
          <p v-if="data" class="mt-2 text-sm text-ink-gray-6">
            {{ data.date }} · {{ data.time_zone }}
          </p>
        </div>
        <div class="flex flex-wrap gap-2">
          <Button @click="router.push({ name: 'Appointments' })">{{
            __('My calendar')
          }}</Button
          ><Button
            variant="solid"
            @click="router.push({ name: 'Appointments', query: { book: '1' } })"
            >{{ __('Book appointment') }}</Button
          >
        </div>
      </div>
      <p v-if="error" role="alert" class="text-ink-red-5">{{ error }}</p>
      <p v-if="message" role="status" class="text-ink-gray-7">{{ message }}</p>
      <p v-if="!data && busy" role="status">{{ __('Loading your day…') }}</p>
      <template v-if="data">
        <div class="grid grid-cols-2 gap-3 lg:grid-cols-4">
          <a
            v-for="tile in tiles"
            :key="tile.key"
            :href="'#daily-' + tile.key"
            class="rounded-xl border border-outline-gray-2 bg-surface-elevation-1 p-4"
            ><span class="text-sm text-ink-gray-6">{{ tile.label }}</span
            ><strong class="mt-2 block text-3xl text-ink-gray-9"
              >{{ tile.group.items.length
              }}{{ tile.group.truncated ? '+' : '' }}</strong
            ></a
          >
        </div>
        <p class="text-sm text-ink-gray-6">
          {{
            __(
              'Personal tasks and appointments only. Overdue tasks are due before today. Counts reflect the records shown; refresh to see changes.',
            )
          }}
        </p>
        <div class="grid items-start gap-5 lg:grid-cols-2">
          <section
            id="daily-appointments"
            class="rounded-xl border border-outline-gray-2 p-4"
          >
            <h2 class="text-lg font-semibold">
              {{ __("Today's appointments") }}
            </h2>
            <p v-if="data.appointments.truncated" class="mt-2 text-sm">
              {{
                __(
                  'This list is limited. Open the calendar for a narrower view.',
                )
              }}
            </p>
            <p
              v-if="!data.appointments.items.length"
              class="py-4 text-sm text-ink-gray-6"
            >
              {{ __('No open appointments today.') }}
            </p>
            <article
              v-for="event in data.appointments.items"
              :key="event.name"
              :data-event="event.name"
              class="mt-3 space-y-2 rounded-lg bg-surface-gray-2 p-3"
            >
              <h3 class="font-medium">{{ event.subject }}</h3>
              <p class="text-sm text-ink-gray-6">
                {{ event.starts_on }} – {{ event.ends_on }}
              </p>
              <p v-if="event.location" class="break-words text-sm">
                {{ event.location }}
              </p>
              <Button
                @click="
                  router.push({
                    name: 'Appointments',
                    query: { event: event.name },
                  })
                "
                >{{ __('View appointment') }}</Button
              >
            </article>
          </section>
          <section
            v-for="group in groups"
            :id="'daily-' + group.key"
            :key="group.key"
            class="rounded-xl border border-outline-gray-2 p-4"
          >
            <h2 class="text-lg font-semibold">{{ group.label }}</h2>
            <p v-if="data.tasks[group.key].truncated" class="mt-2 text-sm">
              {{ __('This list is limited. Open Tasks to see more.') }}
            </p>
            <p
              v-if="!data.tasks[group.key].items.length"
              class="py-4 text-sm text-ink-gray-6"
            >
              {{ __('No tasks to show.') }}
            </p>
            <article
              v-for="task in data.tasks[group.key].items"
              :key="task.name"
              :data-task="task.name"
              class="mt-3 space-y-2 rounded-lg bg-surface-gray-2 p-3"
            >
              <h3 class="break-words font-medium">{{ task.title }}</h3>
              <p class="text-sm text-ink-gray-6">
                {{ task.due_date || __('No due date')
                }}<span v-if="task.priority"> · {{ __(task.priority) }}</span>
              </p>
              <div class="flex flex-wrap gap-2">
                <Button
                  v-if="task.can_complete"
                  :disabled="busy"
                  @click="complete(task)"
                  >{{ __('Mark done') }}</Button
                ><Button
                  v-if="task.reference_docname"
                  @click="openRecord(task)"
                  >{{
                    task.reference_doctype === 'CRM Lead'
                      ? __('Open lead')
                      : __('Open deal')
                  }}</Button
                >
              </div>
            </article>
          </section>
          <section
            id="daily-leads"
            class="rounded-xl border border-outline-gray-2 p-4"
          >
            <h2 class="text-lg font-semibold">{{ __('New leads') }}</h2>
            <p class="mt-2 text-sm text-ink-gray-6">
              {{ __('Your leads still in New status, oldest first.') }}
            </p>
            <p v-if="data.new_leads.truncated" class="mt-2 text-sm">
              {{ __('This list is limited. Open Leads for more records.') }}
            </p>
            <p
              v-if="!data.new_leads.items.length"
              class="py-4 text-sm text-ink-gray-6"
            >
              {{ __('No new leads to show.') }}
            </p>
            <article
              v-for="lead in data.new_leads.items"
              :key="lead.name"
              :data-lead="lead.name"
              class="mt-3 space-y-2 rounded-lg bg-surface-gray-2 p-3"
            >
              <h3 class="font-medium">
                {{
                  [lead.first_name, lead.last_name].filter(Boolean).join(' ')
                }}
              </h3>
              <div class="flex flex-wrap gap-2">
                <Button
                  @click="
                    router.push({ name: 'Lead', params: { leadId: lead.name } })
                  "
                  >{{ __('Open lead') }}</Button
                ><Button
                  @click="
                    router.push({
                      name: 'Appointments',
                      query: { lead: lead.name },
                    })
                  "
                  >{{ __('Book appointment') }}</Button
                >
              </div>
            </article>
          </section>
        </div>
        <Button @click="router.push({ name: 'Tasks' })">{{
          __('Open Tasks')
        }}</Button>
      </template>
    </div>
  </main>
</template>
<script setup>
import { computed, onMounted, ref } from 'vue'
import { useRouter } from 'vue-router'
import { Button, call } from 'frappe-ui'
import LayoutHeader from '@/components/LayoutHeader.vue'
const router = useRouter()
const data = ref(null),
  busy = ref(false),
  error = ref(''),
  message = ref('')
const groups = [
  { key: 'overdue', label: __('Overdue follow-ups') },
  { key: 'today', label: __('Due today') },
  { key: 'upcoming', label: __('Next 7 days') },
  { key: 'undated', label: __('No due date') },
]
const tiles = computed(() =>
  data.value
    ? [
        {
          key: 'appointments',
          label: __("Today's appointments"),
          group: data.value.appointments,
        },
        {
          key: 'overdue',
          label: __('Overdue follow-ups'),
          group: data.value.tasks.overdue,
        },
        { key: 'today', label: __('Due today'), group: data.value.tasks.today },
        { key: 'leads', label: __('New leads'), group: data.value.new_leads },
      ]
    : [],
)
async function perform(fn) {
  if (busy.value) return
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    await fn()
  } catch (e) {
    error.value =
      e.messages?.join(' ') || e.message || __('Unable to load your day')
  } finally {
    busy.value = false
  }
}
async function refresh() {
  data.value = await call('crm.api.productivity.my_day')
}
async function load() {
  await perform(refresh)
}
async function complete(task) {
  await perform(async () => {
    await call('crm.api.productivity.complete_task', {
      name: String(task.name),
      modified: task.modified,
    })
    await refresh()
    message.value = __('Task completed.')
  })
}
function openRecord(task) {
  router.push(
    task.reference_doctype === 'CRM Lead'
      ? { name: 'Lead', params: { leadId: task.reference_docname } }
      : { name: 'Deal', params: { dealId: task.reference_docname } },
  )
}
onMounted(load)
</script>
