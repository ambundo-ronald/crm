<template>
  <section class="space-y-4 rounded-lg border border-outline-gray-2 p-4">
    <h2 class="text-lg font-semibold">{{ __('Shared contact links') }}</h2>
    <p class="text-sm text-ink-gray-6">
      {{
        __(
          'ERPNext and CRM use the same Contact records. Review each new link before adding it. Contact details and existing links are preserved; shared contacts stay read-only for agents.',
        )
      }}
    </p>
    <div class="flex flex-wrap gap-2">
      <Button :disabled="busy" @click="review('')">{{
        __('Review contact links')
      }}</Button>
      <Button :disabled="busy" @click="loadManaged('')">{{
        __('Show managed links')
      }}</Button>
    </div>
    <p v-if="error" role="alert" class="text-ink-red-5">{{ error }}</p>
    <p v-if="message" role="status">{{ message }}</p>
    <template v-if="preview">
      <p v-if="!preview.proposals.length">
        {{ __('No source contact links on this page.') }}
      </p>
      <article
        v-for="row in preview.proposals"
        :key="row.key"
        :data-contact="row.contact"
        :data-source-type="row.source_doctype"
        class="space-y-2 rounded border border-outline-gray-2 p-3 text-sm"
      >
        <RouterLink
          :to="{ name: 'Contact', params: { contactId: row.contact } }"
          class="font-medium underline"
          >{{ row.contact_label || row.contact }}</RouterLink
        >
        <p>{{ row.source_doctype }}: {{ row.source_name }}</p>
        <p v-if="row.target_name">
          {{ __('Destination') }}: {{ row.target_doctype }} —
          {{ row.target_name }}
        </p>
        <p v-if="row.target_owner">
          {{ __('Destination owner') }}: {{ row.target_owner }}
        </p>
        <p v-if="row.agent_visibility" class="rounded bg-surface-amber-1 p-2">
          {{
            __(
              'Linking lets this lead owner see the contact in their agent workspace. Other linked records remain hidden.',
            )
          }}
        </p>
        <details v-if="row.other_links?.length">
          <summary class="cursor-pointer">
            {{ __('Existing links') }} ({{ row.other_link_count }})
          </summary>
          <ul class="mt-2 space-y-1">
            <li v-for="(link, index) in row.other_links" :key="index">
              {{ link.doctype }}: {{ link.name }}
            </li>
          </ul>
          <p v-if="row.other_link_count > row.other_links.length">
            {{ __('Open the Contact to inspect all remaining links.') }}
          </p>
        </details>
        <p v-if="row.issues?.length" class="text-ink-gray-6">
          {{ row.issues.join(', ').replaceAll('_', ' ') }}
        </p>
        <p v-else-if="row.already_linked">
          {{
            row.managed_link
              ? __('Already linked through this review')
              : __('Already linked outside this review')
          }}
        </p>
        <Button v-else :disabled="busy" @click="approve(row)">{{
          row.agent_visibility
            ? __('Link and grant lead owner access')
            : __('Link contact')
        }}</Button>
      </article>
      <Button
        v-if="preview.has_more"
        :disabled="busy"
        @click="review(preview.next_after)"
        >{{ __('Next contact page') }}</Button
      >
    </template>
    <template v-if="managed">
      <h3 class="font-medium">{{ __('Links created through this review') }}</h3>
      <p class="text-sm text-ink-gray-6">
        {{
          __(
            'Removing a link preserves the Contact and its ERPNext links. Access through other links or contact ownership is unaffected. Links are maintained here; removing a source ERPNext link does not automatically remove an approved CRM link.',
          )
        }}
      </p>
      <p v-if="!managed.links.length">
        {{ __('No active managed links on this page.') }}
      </p>
      <div
        v-for="row in managed.links"
        :key="row.name"
        :data-managed-contact="row.contact"
        class="space-y-2 rounded border border-outline-gray-2 p-3 text-sm"
      >
        <p>
          {{ row.contact }} → {{ row.target_doctype }}: {{ row.target_name }}
        </p>
        <p>{{ __('Approved by') }}: {{ row.approved_by }}</p>
        <Button :disabled="busy" @click="remove(row)">{{
          __('Remove CRM link')
        }}</Button>
      </div>
      <Button
        v-if="managed.has_more"
        :disabled="busy"
        @click="loadManaged(managed.next_after)"
        >{{ __('Next managed-link page') }}</Button
      >
    </template>
  </section>
</template>

<script setup>
import { ref } from 'vue'
import { Button, call } from 'frappe-ui'

const emit = defineEmits(['changed'])
const preview = ref(null)
const managed = ref(null)
const busy = ref(false)
const error = ref('')
const message = ref('')
const cursor = ref('')
const managedCursor = ref('')
const api = 'crm.migration.contacts.'

async function perform(action) {
  busy.value = true
  error.value = ''
  try {
    await action()
  } catch (e) {
    error.value =
      e.messages?.join(' ') || e.message || __('Contact link action failed')
  } finally {
    busy.value = false
  }
}

async function review(after) {
  await perform(async () => {
    preview.value = await call(api + 'preview_contact_links', { after })
    cursor.value = after
  })
}

async function loadManaged(after) {
  await perform(async () => {
    managed.value = await call(api + 'managed_contact_links', { after })
    managedCursor.value = after
  })
}

async function refresh() {
  if (preview.value)
    preview.value = await call(api + 'preview_contact_links', {
      after: cursor.value,
    })
  if (managed.value)
    managed.value = await call(api + 'managed_contact_links', {
      after: managedCursor.value,
    })
  emit('changed')
}

async function approve(row) {
  await perform(async () => {
    await call(api + 'approve_contact_link', {
      contact: row.contact,
      source_doctype: row.source_doctype,
      source_name: row.source_name,
      preview_token: row.preview_token,
    })
    message.value = __(
      'Contact linked. Existing details and links were preserved.',
    )
    await refresh()
  })
}

async function remove(row) {
  await perform(async () => {
    await call(api + 'remove_contact_link', { name: row.name })
    message.value = __(
      'The CRM link was removed. The shared Contact was preserved.',
    )
    await refresh()
  })
}
</script>
