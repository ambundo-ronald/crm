<template>
  <article
    class="rounded-lg border border-outline-gray-2 p-4 text-base"
    :aria-label="__('Appointment activity')"
  >
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h3 class="font-medium text-ink-gray-9">{{ activity.data.subject }}</h3>
      <Badge :label="__(activity.data.status)" />
    </div>
    <p class="mt-2 text-ink-gray-7">
      {{ activity.data.starts_on
      }}<template v-if="activity.data.ends_on">
        - {{ activity.data.ends_on }}</template
      >
      ({{ activity.data.time_zone }})
    </p>
    <p v-if="activity.data.location" class="mt-2 text-ink-gray-7">
      {{ activity.data.location }}
    </p>
    <p class="mt-2 text-sm text-ink-gray-5">
      {{ __('Appointment') }} · {{ activity.name }}
    </p>
  </article>
</template>

<script setup>
import { Badge } from 'frappe-ui'

defineProps({ activity: { type: Object, required: true } })
</script>
