<template>
  <section class="space-y-4 rounded-lg border border-outline-gray-2 p-4">
    <h2 class="text-lg font-semibold">
      {{ __('Source history and custom fields') }}
    </h2>
    <p class="text-sm text-ink-gray-6">
      {{
        __(
          'Inspect original ERPNext history without moving records or sending messages. Select an already-synced source. This review is administrator-only.',
        )
      }}
    </p>
    <div class="grid gap-3 sm:grid-cols-2">
      <label class="text-sm"
        >{{ __('Source type')
        }}<select
          v-model="sourceType"
          :aria-label="__('Source type')"
          class="mt-1 w-full rounded border p-2"
        >
          <option v-for="type in types" :key="type">{{ type }}</option>
        </select></label
      >
      <label class="text-sm"
        >{{ __('ERPNext record ID')
        }}<input v-model="sourceName" class="mt-1 w-full rounded border p-2"
      /></label>
    </div>
    <p v-if="error" role="alert" class="text-ink-red-5">{{ error }}</p>
    <p v-if="message" role="status">{{ message }}</p>
    <div class="flex flex-wrap items-end gap-2">
      <label class="text-sm"
        >{{ __('History type')
        }}<select
          v-model="kind"
          :aria-label="__('History type')"
          class="ml-2 rounded border p-2"
        >
          <option v-for="type in kinds" :key="type">{{ type }}</option>
        </select></label
      >
      <Button :disabled="busy || !sourceName" @click="loadHistory('')">{{
        __('View source history')
      }}</Button>
      <Button :disabled="busy" @click="loadInventory">{{
        __('Inspect custom fields')
      }}</Button>
    </div>
    <template v-if="history">
      <p class="text-sm">
        {{
          __(
            'Original timestamps and ownership are shown. Attachments open their protected source record. These entries are not copied into the CRM timeline.',
          )
        }}
      </p>
      <p v-if="!history.rows.length">
        {{ __('No accessible history on this page.') }}
      </p>
      <article
        v-for="row in history.rows"
        :key="row.name"
        class="space-y-2 rounded border p-3 text-sm"
      >
        <a :href="row.source_url" class="underline">{{ row.subject }}</a>
        <p>{{ row.creation }} · {{ row.owner }}</p>
        <p class="whitespace-pre-wrap break-words">{{ row.content }}</p>
        <p v-if="row.content_truncated">
          {{
            __(
              'Preview shortened. Open the source record for the full content.',
            )
          }}
        </p>
      </article>
      <Button
        v-if="history.has_more"
        :disabled="busy"
        @click="loadHistory(history.next_after)"
        >{{ __('Next history page') }}</Button
      >
    </template>
    <template v-if="inventory">
      <p class="text-sm">
        {{
          __(
            'Only compatible scalar custom fields can be mapped. Create destination custom fields in Customize Form first. Standard workflow fields, links, tables and restricted fields are excluded.',
          )
        }}
      </p>
      <div class="grid gap-3 sm:grid-cols-2">
        <div v-for="side in ['source', 'target']" :key="side" class="text-sm">
          <strong>{{
            side === 'source' ? sourceType : inventory.target_doctype
          }}</strong>
          <p v-if="!inventory[side].length">
            {{ __('No custom fields found.') }}
          </p>
          <p
            v-for="field in inventory[side]"
            :key="field.fieldname"
            class="break-words"
          >
            {{ field.fieldname }} ({{ field.fieldtype }}) ·
            {{
              field.supported
                ? __('Supported')
                : __('Requires separate mapping')
            }}
          </p>
        </div>
      </div>
      <label class="block text-sm"
        >{{ __('Field mapping JSON: source field to destination field')
        }}<textarea
          v-model="mapping"
          rows="4"
          class="mt-1 w-full rounded border p-2 font-mono"
          placeholder='{"custom_reference": "custom_reference"}'
        />
      </label>
      <Button :disabled="busy || !sourceName" @click="previewFields">{{
        __('Preview custom field changes')
      }}</Button>
    </template>
    <template v-if="proposal">
      <p v-for="issue in proposal.issues" :key="issue" class="text-ink-red-5">
        {{ issue }}
      </p>
      <article
        v-for="row in proposal.rows"
        :key="row.target_field"
        class="rounded border p-3 text-sm break-words"
      >
        <p>{{ row.source_field }} → {{ row.target_field }}</p>
        <p>{{ __('ERPNext') }}: {{ row.source_value }}</p>
        <p>{{ __('CRM') }}: {{ row.target_value }}</p>
        <p>
          {{
            row.issue || (row.will_update ? __('Will update') : __('Preserved'))
          }}
        </p>
      </article>
      <Button
        :disabled="busy || proposal.issues.length > 0"
        @click="applyFields"
        >{{ __('Apply reviewed custom fields') }}</Button
      >
    </template>
  </section>
</template>
<script setup>
import { ref, watch } from 'vue'
import { Button, call } from 'frappe-ui'
const emit = defineEmits(['changed'])
const types = ['Lead', 'Opportunity', 'Customer', 'Prospect']
const kinds = ['Comment', 'CRM Note', 'Communication', 'File', 'ToDo', 'Event']
const sourceType = ref('Lead'),
  sourceName = ref(''),
  kind = ref('Comment'),
  mapping = ref('{}')
const history = ref(null),
  inventory = ref(null),
  proposal = ref(null),
  busy = ref(false),
  error = ref(''),
  message = ref('')
const api = 'crm.migration.extensions.'
watch([sourceType, sourceName], () => {
  history.value = null
  inventory.value = null
  proposal.value = null
  message.value = ''
})
watch(kind, () => {
  history.value = null
})
watch(mapping, () => {
  proposal.value = null
})
async function perform(action) {
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    await action()
  } catch (e) {
    error.value = e.messages?.join(' ') || e.message || __('Review failed')
  } finally {
    busy.value = false
  }
}
function params() {
  return { source_doctype: sourceType.value, source_name: sourceName.value }
}
async function loadHistory(after) {
  await perform(async () => {
    history.value = await call(api + 'source_history', {
      ...params(),
      kind: kind.value,
      after,
    })
  })
}
async function loadInventory() {
  await perform(async () => {
    inventory.value = await call(api + 'field_inventory', {
      source_doctype: sourceType.value,
    })
  })
}
async function previewFields() {
  proposal.value = null
  await perform(async () => {
    proposal.value = await call(api + 'preview_custom_fields', {
      ...params(),
      fields: JSON.parse(mapping.value),
    })
  })
}
async function applyFields() {
  await perform(async () => {
    await call(api + 'apply_custom_fields', {
      ...params(),
      fields: JSON.parse(mapping.value),
      preview_token: proposal.value.preview_token,
    })
    proposal.value = null
    message.value = __(
      'Reviewed custom fields applied. Source data was preserved.',
    )
    emit('changed')
  })
}
</script>
