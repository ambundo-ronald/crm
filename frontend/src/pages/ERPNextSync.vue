<template>
  <div class="h-full overflow-auto p-5 sm:p-8">
    <div class="mx-auto max-w-4xl space-y-5">
      <h1 class="text-2xl font-semibold">{{ __('ERPNext sync') }}</h1>
      <p class="text-ink-gray-6">
        {{
          __(
            'Bring ERPNext Leads into Frappe CRM on this site. Follow-ups, appointments, CRM status and salesperson changes stay in CRM. Optional Opportunity sync creates Deals for imported leads. Optional Customer sync creates Organizations. Shared contact links require individual review below.',
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
            {{ data.linked_deals }} {{ __('linked deals') }} ·
            {{ data.linked_organizations }} {{ __('linked organizations') }}
          </p>
          <p class="text-sm text-ink-gray-6">
            {{
              __(
                'Each run checks up to 50 records of each enabled type. Review and failed records are retried on the next full pass. Conflicts never overwrite CRM edits.',
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
                data.cursor ||
                data.opportunity_cursor ||
                data.customer_cursor ||
                data.prospect_cursor
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
                  'Opportunity sync supports open opportunities linked to imported leads or business customers or prospects, in the CRM base currency. Products, other currencies and closed records require review.',
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
          <div class="space-y-2 border-t border-outline-gray-2 pt-3">
            <p class="text-sm text-ink-gray-6">
              {{
                __(
                  'Customer sync creates Organizations for active companies and partnerships. Individuals, disabled or frozen customers, and duplicate names require review. Financial records are not copied.',
                )
              }}
            </p>
            <Button :disabled="busy" @click="toggleCustomers">{{
              data.sync_customers
                ? __('Disable Customer sync')
                : __('Enable Customer sync')
            }}</Button>
            <p v-if="data.sync_customers && !data.enabled" class="text-sm">
              {{
                __(
                  'Customer sync is selected. Enable Lead sync to run selected types.',
                )
              }}
            </p>
          </div>
          <div class="space-y-2 border-t border-outline-gray-2 pt-3">
            <p class="text-sm text-ink-gray-6">
              {{
                __(
                  'Primary Address sync reuses each Customer’s verified primary Address on its Organization. Address details are shared with ERPNext; existing CRM choices and conflicting edits require review. This needs both Lead sync and Customer sync enabled.',
                )
              }}
            </p>
            <Button :disabled="busy" @click="toggleCustomerAddresses">{{
              data.sync_customer_addresses
                ? __('Disable primary Address sync')
                : __('Enable primary Address sync')
            }}</Button>
          </div>
          <div class="space-y-2 border-t border-outline-gray-2 pt-3">
            <p class="text-sm text-ink-gray-6">
              {{
                __(
                  'Prospect sync creates Organizations for companies and supports their Opportunities. Matching Customers or existing Organizations require review. Lead relationships and salesperson assignments are not changed.',
                )
              }}
            </p>
            <Button :disabled="busy" @click="toggleProspects">{{
              data.sync_prospects
                ? __('Disable Prospect sync')
                : __('Enable Prospect sync')
            }}</Button>
            <p v-if="data.sync_prospects && !data.enabled" class="text-sm">
              {{ __('Enable Lead sync to run selected types.') }}
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
        <ERPNextContactReview v-if="data.available" @changed="load" />
        <ERPNextAddressReview v-if="data.available" @changed="load" />
        <ERPNextExtensions v-if="data.available" @changed="load" />
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
              <a
                v-if="row.target && row.target_doctype === 'Address'"
                :href="'/app/address/' + encodeURIComponent(row.target)"
                class="ml-2 underline"
                >{{ __('Open address') }}</a
              >
              <RouterLink
                v-else-if="row.target"
                :to="targetRoute(row)"
                class="ml-2 underline"
                >{{
                  row.target_doctype === 'CRM Deal'
                    ? __('Open deal')
                    : row.target_doctype === 'CRM Organization'
                      ? __('Open organization')
                      : row.target_doctype === 'Contact'
                        ? __('Open contact')
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
import ERPNextExtensions from '@/components/ERPNextExtensions.vue'
import ERPNextAddressReview from '@/components/ERPNextAddressReview.vue'
import ERPNextContactReview from '@/components/ERPNextContactReview.vue'
import { Button, call } from 'frappe-ui'

const data = ref(null)
const error = ref('')
const message = ref('')
const busy = ref(false)
const api = 'crm.migration.sync.'

function targetRoute(row) {
  if (row.target_doctype === 'CRM Deal')
    return { name: 'Deal', params: { dealId: row.target } }
  if (row.target_doctype === 'CRM Organization')
    return { name: 'Organization', params: { organizationId: row.target } }
  if (row.target_doctype === 'Contact')
    return { name: 'Contact', params: { contactId: row.target } }
  return { name: 'Lead', params: { leadId: row.target } }
}

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

async function toggleCustomerAddresses() {
  busy.value = true
  error.value = ''
  try {
    data.value = await call(api + 'configure_customer_addresses', {
      enabled: !data.value.sync_customer_addresses,
    })
  } catch (e) {
    error.value =
      e.messages?.join(' ') || e.message || __('Unable to save settings')
  } finally {
    busy.value = false
  }
}

async function toggleProspects() {
  busy.value = true
  error.value = ''
  try {
    data.value = await call(api + 'configure_prospects', {
      enabled: !data.value.sync_prospects,
    })
  } catch (e) {
    error.value =
      e.messages?.join(' ') || e.message || __('Unable to save settings')
  } finally {
    busy.value = false
  }
}

async function toggleCustomers() {
  busy.value = true
  error.value = ''
  try {
    data.value = await call(api + 'configure_customers', {
      enabled: !data.value.sync_customers,
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
