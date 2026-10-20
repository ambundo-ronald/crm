<template>
  <section class="space-y-3 rounded-lg border border-outline-gray-2 p-4">
    <h2 class="text-lg font-semibold">{{ __('ERPNext appointments') }}</h2>
    <p class="text-sm text-ink-gray-6">
      {{
        __(
          'Preview Appointment records and link ready records to My Calendar. Linked appointments are read-only and refresh from ERPNext automatically. Only the creator can see them, subject to lead access. Closed retains its ERPNext meaning; it is not treated as completed or cancelled. Duration comes from ERPNext Appointment Booking Settings.',
        )
      }}
    </p>
    <div class="flex flex-wrap gap-2">
      <Button :disabled="busy" @click="preview('')">{{
        __('Preview appointments')
      }}</Button>
      <Button
        v-if="report?.has_more"
        :disabled="busy"
        @click="preview(report.next_after)"
        >{{ __('Preview next batch') }}</Button
      >
      <Button
        v-if="ready.length"
        :disabled="busy"
        variant="solid"
        @click="sync"
        >{{ __('Sync ready appointments in this batch') }}</Button
      >
    </div>
    <p v-if="error" role="alert" class="text-ink-red-5">{{ error }}</p>
    <p v-if="message" role="status">{{ message }}</p>
    <p v-if="report && !report.rows.length">
      {{ __('No appointments found.') }}
    </p>
    <ul v-if="report" class="space-y-2">
      <li
        v-for="row in report.rows"
        :key="row.name"
        class="border-t border-outline-gray-2 pt-2 text-sm"
      >
        <strong>{{ row.name }}</strong> ·
        {{ row.linked ? __('Linked') : __(row.status) }}
        <p v-if="row.appointment">
          {{ row.appointment.starts_on }} · {{ row.appointment.status }}
        </p>
        <p v-if="row.issue" class="text-ink-red-5">{{ row.issue }}</p>
        <Button v-if="row.linked" :disabled="busy" @click="unlink(row.name)">
          {{ __('Unlink from CRM calendar') }}
        </Button>
      </li>
    </ul>
  </section>
</template>

<script setup>
import { computed, ref } from 'vue'
import { Button, call } from 'frappe-ui'

const report = ref(null)
const busy = ref(false)
const error = ref('')
const message = ref('')
const cursor = ref('')
const ready = computed(() =>
  (report.value?.rows || [])
    .filter((row) => row.status === 'Ready' && !row.linked)
    .map((row) => row.name),
)
const api = 'crm.migration.appointments.'

async function perform(fn) {
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    await fn()
  } catch (e) {
    error.value =
      e.messages?.join(' ') || e.message || __('Appointment sync failed')
  } finally {
    busy.value = false
  }
}

async function preview(after) {
  await perform(async () => {
    report.value = await call(api + 'preview', { after })
    cursor.value = after
  })
}

async function sync() {
  await perform(async () => {
    const result = await call(api + 'sync', { names: ready.value })
    report.value = await call(api + 'preview', { after: cursor.value })
    message.value = __('Appointments linked: {0}', [result.linked])
  })
}

async function unlink(name) {
  await perform(async () => {
    await call(api + 'unlink', { name })
    report.value = await call(api + 'preview', { after: cursor.value })
    message.value = __(
      'Calendar link removed. The ERPNext appointment is unchanged.',
    )
  })
}
</script>
