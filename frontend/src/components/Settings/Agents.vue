<template>
  <section class="h-full space-y-5 overflow-auto p-6 text-ink-gray-8">
    <h2 class="text-2xl font-semibold">{{ __('Agents') }}</h2>
    <p class="text-sm text-ink-gray-6">
      {{
        __(
          'Manage external agents who can access only their own leads, linked contacts and follow-ups. Finance manages commissions separately.',
        )
      }}
    </p>
    <p v-if="error" role="alert" class="text-ink-red-5">{{ error }}</p>
    <p v-if="message" role="status">{{ message }}</p>
    <form class="space-y-3 rounded border p-4" @submit.prevent="create">
      <h3 class="font-medium">{{ __('Create agent account') }}</h3>
      <div class="grid gap-3 sm:grid-cols-2">
        <label class="text-sm"
          >{{ __('First name')
          }}<input
            v-model="firstName"
            required
            maxlength="140"
            class="mt-1 w-full rounded border p-2"
        /></label>
        <label class="text-sm"
          >{{ __('Last name')
          }}<input
            v-model="lastName"
            maxlength="140"
            class="mt-1 w-full rounded border p-2"
        /></label>
      </div>
      <label class="block text-sm"
        >{{ __('Agent email')
        }}<input
          v-model="email"
          required
          type="email"
          maxlength="140"
          class="mt-1 w-full rounded border p-2"
      /></label>
      <p class="text-sm text-ink-gray-6">
        {{
          __(
            'Creates a new restricted account without sending email. Existing staff accounts cannot be converted here. Send a setup email separately when ready.',
          )
        }}
      </p>
      <Button type="submit" variant="solid" :disabled="busy">{{
        __('Create agent')
      }}</Button>
    </form>
    <p v-if="data?.mail_muted" class="rounded bg-surface-amber-1 p-3 text-sm">
      {{
        __(
          'Email is muted on this site. Setup invitations cannot be sent here.',
        )
      }}
    </p>
    <form class="flex gap-2" @submit.prevent="load('')">
      <input
        v-model="search"
        :aria-label="__('Search agents')"
        :placeholder="__('Search agents')"
        class="min-w-0 flex-1 rounded border p-2"
        maxlength="140"
      />
      <Button type="submit" :disabled="busy">{{ __('Search') }}</Button>
      <Button :disabled="busy" @click="load('')">{{ __('Refresh') }}</Button>
    </form>
    <p v-if="data && !data.agents.length">{{ __('No agents found.') }}</p>
    <article
      v-for="agent in data?.agents || []"
      :key="agent.name"
      :data-agent="agent.name"
      class="space-y-3 rounded border p-4"
    >
      <div>
        <strong>{{ agent.full_name }}</strong>
        <p class="break-words text-sm">{{ agent.name }}</p>
      </div>
      <p class="text-sm">
        {{ agent.enabled ? __('Active') : __('Suspended') }}
      </p>
      <p
        v-for="issue in agent.issues"
        :key="issue"
        class="text-sm text-ink-red-5"
      >
        {{ issue }}
      </p>
      <div class="flex flex-wrap gap-2">
        <Button
          :disabled="busy || (!agent.enabled && agent.issues.length > 0)"
          @click="select(agent, agent.enabled ? 'suspend' : 'reactivate')"
          >{{
            agent.enabled ? __('Suspend access') : __('Reactivate access')
          }}</Button
        >
        <Button
          :disabled="
            busy || !agent.enabled || agent.issues.length > 0 || data.mail_muted
          "
          @click="select(agent, 'invite')"
          >{{ __('Send setup email') }}</Button
        >
        <Button :disabled="busy" @click="history(agent)">{{
          __('Access history')
        }}</Button>
      </div>
      <div
        v-if="selected?.name === agent.name"
        class="space-y-3 rounded bg-surface-gray-2 p-3"
      >
        <p class="text-sm">
          {{
            action === 'suspend'
              ? __(
                  'Suspend this agent and revoke sessions, API credentials and pending setup links? Their leads and contacts will be preserved.',
                )
              : action === 'reactivate'
                ? __(
                    'Restore access to this agent’s existing leads and contacts? Previous sessions and API credentials will remain revoked.',
                  )
                : __(
                    'Send a password-setup email to this agent? A new link replaces previous setup links.',
                  )
          }}
        </p>
        <label v-if="action !== 'invite'" class="block text-sm"
          >{{ __('Reason')
          }}<textarea
            v-model="reason"
            maxlength="500"
            rows="2"
            class="mt-1 w-full rounded border p-2"
          />
        </label>
        <div class="flex gap-2">
          <Button
            :disabled="busy || (action !== 'invite' && !reason.trim())"
            @click="confirm"
            >{{ __('Confirm action') }}</Button
          ><Button :disabled="busy" @click="selected = null">{{
            __('Cancel')
          }}</Button>
        </div>
      </div>
      <div v-if="historyUser === agent.name && logs" class="space-y-2 text-sm">
        <p v-if="!logs.rows.length">
          {{ __('No actions recorded through agent administration yet.') }}
        </p>
        <div
          v-for="row in logs.rows"
          :key="row.name"
          class="rounded border p-2"
        >
          <p>{{ row.creation }} · {{ row.action }} · {{ row.actor }}</p>
          <p class="whitespace-pre-wrap break-words">{{ row.reason }}</p>
        </div>
        <Button
          v-if="logs.has_more"
          :disabled="busy"
          @click="history(agent, logs.next_after)"
          >{{ __('Next history page') }}</Button
        >
      </div>
    </article>
    <Button
      v-if="data?.has_more"
      :disabled="busy"
      @click="load(data.next_after)"
      >{{ __('Next agent page') }}</Button
    >
  </section>
</template>
<script setup>
import { onMounted, ref } from 'vue'
import { Button, call } from 'frappe-ui'
const api = 'crm.api.agent_admin.'
const data = ref(null),
  busy = ref(false),
  error = ref(''),
  message = ref('')
const firstName = ref(''),
  lastName = ref(''),
  email = ref(''),
  search = ref('')
const selected = ref(null),
  action = ref(''),
  reason = ref(''),
  historyUser = ref(''),
  logs = ref(null)
async function perform(fn) {
  busy.value = true
  error.value = ''
  message.value = ''
  try {
    await fn()
  } catch (e) {
    error.value =
      e.messages?.join(' ') || e.message || __('Agent administration failed')
  } finally {
    busy.value = false
  }
}
async function refresh(after = '') {
  data.value = await call(api + 'list_agents', { after, search: search.value })
}
async function load(after = '') {
  await perform(async () => {
    selected.value = null
    await refresh(after)
  })
}
async function create() {
  await perform(async () => {
    const result = await call(api + 'create_agent', {
      email: email.value,
      first_name: firstName.value,
      last_name: lastName.value,
    })
    search.value = result.name
    firstName.value = ''
    lastName.value = ''
    email.value = ''
    await refresh()
    message.value = __('Agent created. No email has been sent.')
  })
}
function select(agent, kind) {
  selected.value = agent
  action.value = kind
  reason.value = ''
  error.value = ''
  message.value = ''
}
async function confirm() {
  await perform(async () => {
    const agent = selected.value
    if (action.value === 'invite') {
      await call(api + 'invite_agent', {
        user: agent.name,
        modified: agent.modified,
      })
      message.value = __(
        'Setup email requested. Delivery depends on the site email service.',
      )
    } else {
      await call(api + 'set_agent_enabled', {
        user: agent.name,
        enabled: action.value === 'reactivate',
        reason: reason.value,
        modified: agent.modified,
      })
      message.value =
        action.value === 'reactivate'
          ? __('Agent access restored. Previous credentials remain revoked.')
          : __('Agent suspended. Their CRM records were preserved.')
    }
    selected.value = null
    logs.value = null
    await refresh()
  })
}
async function history(agent, after = '') {
  await perform(async () => {
    logs.value = await call(api + 'access_history', { user: agent.name, after })
    historyUser.value = agent.name
  })
}
onMounted(() => load())
</script>
