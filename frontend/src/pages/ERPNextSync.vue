<template>
  <div class="h-full overflow-auto p-5 sm:p-8">
    <div class="mx-auto max-w-4xl space-y-5">
      <h1 class="text-2xl font-semibold">{{ __('ERPNext sync') }}</h1>
      <p class="text-ink-gray-6">
        {{
          __(
            'Bring ERPNext Leads into Frappe CRM on this site. Follow-ups, appointments, CRM status and salesperson changes stay in CRM. Optional Opportunity sync creates Deals for imported leads. Contact links are not synced yet.',
          )
        }}
      </p>
      <p v-if="error" role="alert" class="text-ink-red-5">{{ error }}</p>
      <template v-if="data">
        <p v-if="!data.available">
          {{ __('ERPNext must be installed on this site.') }}
        </p>
        <div
          v-else
          class="space-y-4 rounded-lg border border-outline-gray-2 p-4"
        >
          <p>
            {{
              data.enabled ? __('Lead sync enabled') : __('Lead sync disabled')
            }}
            · {{ data.linked_leads }} {{ __('linked leads') }} ·
            {{ data.linked_deals }} {{ __('linked deals') }}
          </p>
          <p class="text-sm text-ink-gray-6">
            {{
              __(
                'Each run checks up to 50 leads and, when enabled, 50 opportunities. Review and failed records are retried on the next full pass. Conflicts never overwrite CRM edits.',
              )
            }}
          </p>
          <div class="flex flex-wrap gap-2">
            <Button :disabled="busy" @click="configure(!data.enabled, false)">{{
              data.enabled ? __('Disable sync') : __('Enable Lead sync')
            }}</Button>
            <Button
              v-if="data.enabled"
              :disabled="busy"
              @click="configure(true, !data.automatic)"
              >{{
                data.automatic
                  ? __('Turn off automatic sync')
                  : __('Turn on automatic sync')
              }}</Button
            >
            <Button
              v-if="data.enabled"
              variant="solid"
              :loading="busy"
              @click="run"
              >{{
                data.cursor || data.opportunity_cursor
                  ? __('Sync next batch')
                  : __('Sync now')
              }}</Button
            >
            <Button :disabled="busy" @click="load">{{ __('Refresh') }}</Button>
          </div>
          <div class="space-y-2 border-t border-outline-gray-2 pt-3">
            <p class="text-sm text-ink-gray-6">
              {{
                __(
                  'Opportunity sync supports open opportunities linked to imported leads, in the CRM base currency. Customer/prospect opportunities, products, other currencies and closed records require review.',
                )
              }}
            </p>
            <Button :disabled="busy" @click="toggleOpportunities">{{
              data.sync_opportunities
                ? __('Disable Opportunity sync')
                : __('Enable Opportunity sync')
            }}</Button>
            <p v-if="data.sync_opportunities && !data.enabled" class="text-sm">
              {{
                __(
                  'Opportunity sync is selected. Enable Lead sync to run both.',
                )
              }}
            </p>
          </div>
          <p v-if="data.automatic" class="text-sm text-ink-gray-6">
            {{
              __(
                'Automatic sync is configured. It runs only while the site scheduler and background workers are active.',
              )
            }}
          </p>
          <a href="/app/crm-erpnext-sync-settings" class="text-sm underline">{{
            __('Review status and user mappings in settings')
          }}</a>
        </div>
        <p v-if="message" role="status">{{ message }}</p>
        <h2 class="text-lg font-semibold">{{ __('Recent runs') }}</h2>
        <p v-if="!data.runs.length" class="text-ink-gray-6">
          {{ __('No sync runs yet.') }}
        </p>
        <details
          v-for="item in data.runs"
          :key="item.name"
          class="rounded-lg border border-outline-gray-2 p-4"
        >
          <summary class="cursor-pointer">
            {{ item.creation }} · {{ item.summary }}
          </summary>
          <ul class="mt-3 space-y-3 text-sm">
            <li
              v-for="row in results(item)"
              :key="(row.source_doctype || 'Lead') + row.source"
            >
              <span class="font-medium"
                >{{ row.source }}: {{ row.status }}</span
              >
              <RouterLink
                v-if="row.target"
                :to="
                  row.target_doctype === 'CRM Deal'
                    ? { name: 'Deal', params: { dealId: row.target } }
                    : { name: 'Lead', params: { leadId: row.target } }
                "
                class="ml-2 underline"
                >{{
                  row.target_doctype === 'CRM Deal'
                    ? __('Open deal')
                    : __('Open lead')
                }}</RouterLink
              >
              <p
                v-if="row.issues?.length"
                class="mt-1 break-words text-ink-gray-6"
              >
                {{ row.issues.join(', ').replaceAll('_', ' ') }}
              </p>
            </li>
          </ul>
        </details>
      </template>
    </div>
  </div>
</template>

<script setup>
import { onMounted, ref } from 'vue'
import { Button, call } from 'frappe-ui'

const data = ref(null)
const error = ref('')
const message = ref('')
const busy = ref(false)
const api = 'crm.migration.sync.'

function results(run) {
  try {
    return JSON.parse(run.results || '[]')
  } catch {
    return []
  }
}

async function load() {
  error.value = ''
  try {
    data.value = await call(api + 'status')
  } catch (e) {
    error.value =
      e.messages?.join(' ') || e.message || __('Unable to load sync status')
  }
}

async function configure(enabled, automatic) {
  busy.value = true
  error.value = ''
  try {
    data.value = await call(api + 'configure', { enabled, automatic })
  } catch (e) {
    error.value =
      e.messages?.join(' ') || e.message || __('Unable to save settings')
  } finally {
    busy.value = false
  }
}

async function toggleOpportunities() {
  busy.value = true
  error.value = ''
  try {
    data.value = await call(api + 'configure_opportunities', {
      enabled: !data.value.sync_opportunities,
    })
  } catch (e) {
    error.value =
      e.messages?.join(' ') || e.message || __('Unable to save settings')
  } finally {
    busy.value = false
  }
}

async function run() {
  busy.value = true
  error.value = ''
  try {
    const report = await call(api + 'sync_now')
    message.value =
      report.summary +
      (report.has_more
        ? ' · ' + __('More records remain. Run the next batch to continue.')
        : ' · ' + __('Pass complete.'))
    await load()
  } catch (e) {
    error.value = e.messages?.join(' ') || e.message || __('Sync failed')
  } finally {
    busy.value = false
  }
}

onMounted(load)
</script>
