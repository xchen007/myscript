<template>
  <div class="panel">
    <JobList
      :jobs="jobs"
      :selectedId="selectedId"
      :showNewBtn="false"
      @select="selectJob"
    />

    <div class="panel-right">
      <!-- Top: always-visible form -->
      <div class="form-section">
        <div class="section-label-bar">New bisync job</div>
        <BisyncForm @submit="onSubmit" />
      </div>

      <!-- Bottom: log output -->
      <div class="log-section">
        <div class="log-header" :class="{ empty: !currentJob }">
          <template v-if="currentJob">
            <span class="job-title">{{ currentJob.label }}</span>
            <StatusBadge :status="currentJob.status" />
            <button
              v-if="currentJob.status === 'running'"
              class="btn btn-danger btn-sm"
              @click="stopJob(currentJob.id)"
            >Stop</button>
            <button v-else class="btn btn-ghost btn-sm" @click="removeJob(currentJob.id)">✕</button>
          </template>
          <template v-else>
            <span>Select a job or run a new one</span>
          </template>
        </div>
        <LogViewer :lines="currentJob?.lines ?? []" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import { useJobs }  from '../../composables/useJobs.js'
import JobList      from '../shared/JobList.vue'
import LogViewer    from '../shared/LogViewer.vue'
import StatusBadge  from '../shared/StatusBadge.vue'
import BisyncForm   from './BisyncForm.vue'

const { jobs, selectedId, selectedJob, addJob, stopJob, removeJob, selectJob } = useJobs('bisync')
const currentJob = computed(() => selectedJob())

function onSubmit({ label, args }) {
  addJob(label, args)
}
</script>

<style scoped>
.panel { display: flex; flex: 1; overflow: hidden; }

.panel-right {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ── Form section (top, natural height) ─────────── */
.form-section {
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  border-bottom: 2px solid var(--border);
  overflow-y: auto;
  max-height: 58%;
}

.section-label-bar {
  padding: 5px 12px;
  font-size: 11px;
  font-weight: 600;
  color: var(--text2);
  background: var(--bg2);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  text-transform: uppercase;
  letter-spacing: 0.06em;
}

/* ── Log section (bottom, fills remaining space) ── */
.log-section {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 90px;
}

.log-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 5px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--bg2);
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 600;
}
.log-header.empty { color: var(--text2); font-weight: 400; font-style: italic; }

.job-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.btn-sm { padding: 3px 8px; font-size: 11px; }

:deep(.log-viewer) { margin: 6px; border-radius: var(--radius); }
</style>
