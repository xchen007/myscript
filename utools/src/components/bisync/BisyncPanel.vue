<template>
  <div class="panel">
    <!-- LEFT: job list -->
    <JobList
      :jobs="jobs"
      :selectedId="selectedId"
      @select="selectJob"
      @new-job="showForm = true"
    />

    <!-- RIGHT: form OR detail -->
    <div class="panel-right">
      <!-- New job form -->
      <template v-if="showForm">
        <div class="panel-header">New bisync job</div>
        <BisyncForm
          @submit="onSubmit"
          @cancel="showForm = false"
        />
      </template>

      <!-- Job detail -->
      <template v-else-if="currentJob">
        <div class="panel-header">
          <span class="job-title">{{ currentJob.label }}</span>
          <StatusBadge :status="currentJob.status" />
          <button
            v-if="currentJob.status === 'running'"
            class="btn btn-danger btn-sm"
            @click="stopJob(currentJob.id)"
          >Stop</button>
          <button
            v-else
            class="btn btn-ghost btn-sm"
            @click="removeJob(currentJob.id)"
          >✕</button>
        </div>
        <div class="args-line">{{ currentJob.args.join(' ') }}</div>
        <LogViewer :lines="currentJob.lines" />
      </template>

      <!-- Empty state -->
      <template v-else>
        <div class="empty-state">Click "＋ New job" to start a bisync.</div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useJobs }    from '../../composables/useJobs.js'
import JobList        from '../shared/JobList.vue'
import LogViewer      from '../shared/LogViewer.vue'
import StatusBadge    from '../shared/StatusBadge.vue'
import BisyncForm     from './BisyncForm.vue'

const { jobs, selectedId, selectedJob, addJob, stopJob, removeJob, selectJob } = useJobs('bisync')

const showForm   = ref(false)
const currentJob = computed(() => selectedJob())

function onSubmit({ label, args }) {
  addJob(label, args)
  showForm.value = false
}
</script>

<style scoped>
.panel {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.panel-right {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 0;
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--bg2);
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 600;
}

.job-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.args-line {
  padding: 4px 12px;
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text2);
  background: var(--bg2);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text2);
  font-size: 13px;
}

.btn-sm { padding: 3px 8px; font-size: 11px; }

/* LogViewer needs padding from parent */
:deep(.log-viewer) { margin: 8px; border-radius: var(--radius); }
</style>
