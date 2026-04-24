<template>
  <div class="sprint-report">
    <form class="op-form" @submit.prevent="run">
      <div class="form-group">
        <label>Jira user</label>
        <input v-model="user" placeholder="xchen17" required />
      </div>
      <div class="form-group">
        <label>Sprint label</label>
        <input v-model="label" placeholder="SDS-CP-Sprint08-2026" required />
      </div>
      <div class="form-group">
        <label class="checkbox-label"><input type="checkbox" v-model="all" /> --all (full detail)</label>
        <label class="checkbox-label"><input type="checkbox" v-model="report" /> --report (table)</label>
      </div>
      <div class="config-hint">{{ configHint }}</div>
      <button type="submit" class="btn btn-primary" :disabled="running">
        {{ running ? '⏳ Running…' : '▶ Run' }}
      </button>
    </form>

    <div class="op-output">
      <LogViewer v-if="lines.length > 0" :lines="lines" />
      <div v-else class="output-empty">Results will appear here.</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import LogViewer from '../../shared/LogViewer.vue'

const user    = ref('')
const label   = ref('')
const all     = ref(false)
const report  = ref(false)
const running = ref(false)
const lines   = ref([])
const jobId   = ref(null)

const configHint = ref('')

onMounted(() => {
  const cfg  = window.myscriptAPI?.loadJiraConfig() ?? {}
  const home = window.myscriptAPI?.getHomeDir() ?? '~'
  if (cfg.user)  user.value  = cfg.user
  if (cfg.label) label.value = cfg.label
  configHint.value = cfg.found
    ? `Config loaded from ${home}/.my_jira_config`
    : `No config at ${home}/.my_jira_config`
})

function run() {
  if (!user.value || !label.value) return
  const args = ['--user', user.value, '--label', label.value]
  if (all.value)    args.push('--all')
  if (report.value) args.push('--report')

  // Stop previous job if still running
  if (jobId.value && running.value) {
    window.myscriptAPI.stopTool(jobId.value)
  }

  lines.value = []
  running.value = true
  jobId.value = crypto.randomUUID()

  window.myscriptAPI.runTool(
    jobId.value,
    'jira-analyzer',
    args,
    (line) => lines.value.push(line),
    (_code) => { running.value = false },
  )
}
</script>

<style scoped>
.sprint-report {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.op-form {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.form-group { display: flex; flex-direction: column; gap: 4px; }

.config-hint { font-size: 10px; color: var(--text2); font-style: italic; }

.op-output {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 8px;
}

.output-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text2);
  font-size: 12px;
}

:deep(.log-viewer) { border-radius: var(--radius); }
</style>
