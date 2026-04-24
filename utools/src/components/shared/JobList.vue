<template>
  <div class="job-list">
    <button class="btn btn-primary new-job-btn" @click="$emit('new-job')">＋ New job</button>

    <div v-if="jobs.length === 0" class="empty">No jobs yet.</div>

    <div
      v-for="job in jobs"
      :key="job.id"
      class="job-card"
      :class="[job.status, { selected: job.id === selectedId }]"
      @click="$emit('select', job.id)"
    >
      <div class="job-top">
        <span class="job-label">{{ job.label }}</span>
        <StatusBadge :status="job.status" />
      </div>
      <div class="job-meta">
        {{ formatTime(job.startedAt) }}
        <span v-if="job.lines.length"> · {{ job.lines.length }} lines</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import StatusBadge from './StatusBadge.vue'

defineProps({
  jobs:       { type: Array,  required: true },
  selectedId: { type: String, default: null  },
})
defineEmits(['select', 'new-job'])

function formatTime(date) {
  if (!date) return ''
  const d = new Date(date)
  return isNaN(d.getTime()) ? '' : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}
</script>

<style scoped>
.job-list {
  width: 180px;
  flex-shrink: 0;
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 6px;
  overflow-y: auto;
  background: var(--bg2);
}

.new-job-btn { width: 100%; justify-content: center; margin-bottom: 4px; }

.empty { font-size: 11px; color: var(--text2); text-align: center; padding: 20px 0; }

.job-card {
  padding: 7px 8px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--bg);
  cursor: pointer;
  transition: border-color 0.12s;
  border-left-width: 3px;
}
.job-card:hover { border-color: var(--accent); }
.job-card.selected { background: var(--bg3); border-color: var(--accent); }
.job-card.running { border-left-color: var(--accent); }
.job-card.done    { border-left-color: var(--green); }
.job-card.stopped { border-left-color: var(--text2); }
.job-card.error   { border-left-color: var(--red); }

.job-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 4px; }
.job-label { font-size: 11px; font-weight: 600; color: var(--text); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.job-meta { font-size: 10px; color: var(--text2); margin-top: 2px; }
</style>
