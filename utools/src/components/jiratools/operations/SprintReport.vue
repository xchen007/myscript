<template>
  <div class="sprint-report">
    <!-- Form -->
    <form class="op-form" @submit.prevent="run">
      <div v-if="!jiraBin" class="config-warn">
        ⚠️ Jira CLI path not configured. Go to <a href="#" @click.prevent="$router.push('/settings')">⚙️ Settings</a> to set it.
      </div>
      <div class="form-row">
        <div class="form-group">
          <label>Jira user</label>
          <InputWithHistory ref="userRef" v-model="user" storageKey="sprint-user" placeholder="xchen17" required />
        </div>
        <div class="form-group">
          <label>Sprint label</label>
          <InputWithHistory ref="labelRef" v-model="label" storageKey="sprint-label" placeholder="SDS-CP-Sprint08-2026" required />
        </div>
      </div>
      <div class="form-footer">
        <span class="config-hint">{{ configHint }}</span>
        <div class="form-actions">
          <button type="submit" class="btn btn-primary" :disabled="appState === 'loading'">
            {{ appState === 'loading' ? '⏳ Running…' : '▶ Run' }}
          </button>
          <button v-if="appState === 'loading'" type="button" class="btn btn-danger" @click="stop">■ Stop</button>
        </div>
      </div>
    </form>

    <!-- Tab bar -->
    <div class="tab-bar">
      <button class="tab-btn" :class="{ active: activeTab === 'tickets' }" @click="setTab('tickets')">📊 Tickets</button>
      <button class="tab-btn" :class="{ active: activeTab === 'dashboard' }" @click="setTab('dashboard')">📈 Dashboard</button>
    </div>

    <!-- Table area -->
    <div v-show="activeTab === 'tickets'" class="table-area">
      <TicketTable :data="tableData ?? emptyData" :appState="appState" />
    </div>

    <!-- Dashboard area -->
    <div v-show="activeTab === 'dashboard'" class="table-area">
      <WorklogChart v-if="dailyLog.length" :dailyLog="dailyLog" />
      <div v-else class="output-empty">
        <template v-if="appState === 'idle'">Run a sprint report to see the dashboard.</template>
        <template v-else-if="appState === 'loading'">⏳ Fetching worklog data…</template>
        <template v-else>No worklog data found for this sprint.</template>
      </div>
    </div>

    <!-- Collapsible log area -->
    <div class="log-section" :class="{ collapsed: logCollapsed }">
      <div class="log-header" @click="toggleLog">
        <span class="log-title">
          📋 Logs
          <span class="log-count">({{ lines.length }})</span>
          <span v-if="appState === 'loading'" class="log-running">●</span>
        </span>
        <span class="log-toggle">{{ logCollapsed ? '▲' : '▼' }}</span>
      </div>
      <div class="log-body">
        <LogViewer :lines="lines" />
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import LogViewer from '../../shared/LogViewer.vue'
import TicketTable from './TicketTable.vue'
import WorklogChart from './WorklogChart.vue'
import InputWithHistory from '../../shared/InputWithHistory.vue'

const jiraBin  = ref('')
const user     = ref('')
const label    = ref('')
const jobId    = ref(null)

const userRef  = ref(null)
const labelRef = ref(null)

// 'idle' | 'loading' | 'done' | 'no-data' | 'error'
const appState    = ref('idle')
const tableData   = ref(null)
const dailyLog    = ref([])
const lines       = ref([])
const configHint  = ref('')
const logCollapsed = ref(false)
const activeTab   = ref('tickets')

const LOG_KEY = 'sprint-log-expanded:v1'
const TAB_KEY = 'sprint-active-tab:v1'
const LOG_LIMIT = 500

const emptyData = { tickets: [], stats: { total_tickets: 0, total_log_seconds: 0, total_points: 0, status_counts: {}, type_counts: {} }, meta: {} }

function setTab(tab) {
  activeTab.value = tab
  window.myscriptAPI?.setPref(TAB_KEY, tab)
}

onMounted(() => {
  // Read all jira config from uTools DB settings
  jiraBin.value = window.myscriptAPI?.getSetting('jira_bin') ?? ''
  user.value    = window.myscriptAPI?.getSetting('jira_user') ?? ''
  label.value   = window.myscriptAPI?.getSetting('jira_label') ?? ''

  const configured = jiraBin.value && user.value && label.value
  configHint.value = configured
    ? 'Config loaded from ⚙️ Settings'
    : 'Configure Jira settings in ⚙️ Settings page'

  // Restore log collapsed state and active tab
  const saved = window.myscriptAPI?.getPref(LOG_KEY)
  if (saved !== null) logCollapsed.value = !saved
  const savedTab = window.myscriptAPI?.getPref(TAB_KEY)
  if (savedTab) activeTab.value = savedTab
})

function toggleLog() {
  logCollapsed.value = !logCollapsed.value
  window.myscriptAPI?.setPref(LOG_KEY, !logCollapsed.value)
}

function pushLog(line) {
  if (lines.value.length < LOG_LIMIT) {
    lines.value.push(line)
  } else if (lines.value.length === LOG_LIMIT) {
    lines.value.push(`… (log truncated at ${LOG_LIMIT} lines)`)
  }
}

function run() {
  if (!jiraBin.value || !user.value || !label.value) return

  userRef.value?.push(user.value)
  labelRef.value?.push(label.value)

  if (!window.myscriptAPI?.isReady()) {
    lines.value = ['[error] Project root not found. Run: make install inside the myscript directory.']
    appState.value = 'error'
    return
  }

  if (jobId.value && appState.value === 'loading') {
    window.myscriptAPI.stopTool(jobId.value)
  }

  lines.value   = []
  tableData.value = null
  dailyLog.value  = []
  appState.value  = 'loading'
  jobId.value   = crypto.randomUUID()

  const jiraUrl = window.myscriptAPI?.getSetting('jira_url') ?? ''
  const args = ['--jira-bin', jiraBin.value, '--user', user.value, '--label', label.value, '--json']
  if (jiraUrl) args.push('--jira-url', jiraUrl)

  try {
    window.myscriptAPI.runTool(
      jobId.value,
      'jira-analyzer',
      args,
      // onData: stderr + command echo → log
      (line) => pushLog(line),
      // onExit
      (code) => {
        if (appState.value === 'loading') {
          appState.value = code === 0 ? 'no-data' : 'error'
        }
      },
      // onStdout: detect structured JSON sentinel
      (line) => {
        if (line.startsWith('__SPRINT_TABLE_JSON__:')) {
          try {
            const parsed = JSON.parse(line.slice('__SPRINT_TABLE_JSON__:'.length))
            tableData.value = parsed
            dailyLog.value  = parsed.daily_log ?? []
            appState.value  = (parsed.stats?.total_tickets ?? 0) > 0 ? 'done' : 'no-data'
          } catch (e) {
            pushLog(`[error] Failed to parse table data: ${e.message}`)
            appState.value = 'error'
          }
        } else {
          pushLog(line)
        }
      },
    )
  } catch (err) {
    pushLog(`[error] Failed to start jira-analyzer: ${err.message}`)
    appState.value = 'error'
  }
}

function stop() {
  if (jobId.value) window.myscriptAPI.stopTool(jobId.value)
  appState.value = 'idle'
}
</script>

<style scoped>
.sprint-report {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

/* ── Form ─────────────────────────────────────────────────────────────────── */
.op-form {
  padding: 10px 12px;
  display: flex;
  flex-direction: column;
  gap: 8px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.form-group { display: flex; flex-direction: column; gap: 4px; }

.form-row { display: flex; gap: 10px; }
.form-row .form-group { flex: 1; }

.config-warn {
  font-size: 11px;
  color: var(--yellow);
  padding: 4px 8px;
  background: color-mix(in srgb, var(--yellow) 10%, transparent);
  border-radius: var(--radius);
}
.config-warn a { color: var(--accent); text-decoration: underline; cursor: pointer; }

.form-footer { display: flex; align-items: center; gap: 8px; }
.config-hint { font-size: 10px; color: var(--text2); font-style: italic; flex: 1; }
.form-actions { display: flex; gap: 6px; flex-shrink: 0; }

/* ── Tab bar ─────────────────────────────────────────────────────────────── */
.tab-bar {
  display: flex;
  gap: 2px;
  padding: 6px 12px 0;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.tab-btn {
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  padding: 5px 14px 7px;
  font-size: 12px;
  color: var(--text2);
  cursor: pointer;
  margin-bottom: -1px;
  transition: color 0.15s, border-color 0.15s;
}
.tab-btn:hover { color: var(--fg); }
.tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }

/* ── Table area ───────────────────────────────────────────────────────────── */
.table-area {
  flex: 2;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

.output-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 1;
  color: var(--text2);
  font-size: 13px;
  padding: 40px;
}

/* ── Log section ──────────────────────────────────────────────────────────── */
.log-section {
  flex: 1 0 0;
  display: flex;
  flex-direction: column;
  border-top: 1px solid var(--border);
  min-height: 0;
  overflow: hidden;
}

/* When collapsed: shrink to header only so table reclaims the space */
.log-section.collapsed {
  flex: 0 0 auto;
}

.log-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 4px 10px;
  cursor: pointer;
  font-size: 11px;
  color: var(--text2);
  background: var(--bg2);
  user-select: none;
  flex-shrink: 0;
}
.log-header:hover { background: var(--bg3); }

.log-title { display: flex; align-items: center; gap: 5px; }
.log-count { opacity: 0.7; }
.log-running { color: var(--accent); animation: blink 1s infinite; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.2} }

.log-toggle { font-size: 10px; }

.log-body {
  flex: 1;
  overflow: hidden;
  max-height: 1000px;
  transition: max-height 0.2s ease-in-out;
}
.log-section.collapsed .log-body { max-height: 0; }

:deep(.log-viewer) {
  border-radius: 0;
  height: 100%;
}
</style>
