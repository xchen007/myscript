<template>
  <span class="badge" :class="status">{{ labels[status] ?? `⚠ ${status}` }}</span>
</template>

<script setup>
defineProps({ status: { type: String, required: true } })

const labels = {
  running: '● Running',
  done:    '✓ Done',
  stopped: '⏹ Stopped',
  error:   '✕ Error',
}
</script>

<style scoped>
.badge {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 10px;
  white-space: nowrap;
}
.running { color: var(--accent); animation: pulse 1.4s ease-in-out infinite; }
.done    { color: var(--green); }
.stopped { color: var(--text2); }
.error   { color: var(--red); }

@keyframes pulse { 0%, 100% { opacity: 1 } 50% { opacity: 0.45 } }
</style>
