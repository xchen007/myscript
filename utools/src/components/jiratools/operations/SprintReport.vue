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
          <label>Sprint label(s)</label>
          <InputWithHistory ref="labelRef" v-model="label" storageKey="sprint-label" placeholder="Sprint08-2026,Sprint07-2026" required />
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

    <!-- Dashboard (always visible above tabs) -->
    <WorklogDashboard :dailyLog="dailyLog" :weeklyLog="weeklyLog" :labels="labels" :appState="appState" />

    <!-- Tab bar -->
    <div class="tab-bar">
      <button class="tab-btn" :class="{ active: activeTab === 'tickets' }" @click="setTab('tickets')">📊 Tickets</button>
      <button class="tab-btn" :class="{ active: activeTab === 'logs' }" @click="setTab('logs')">
        📋 Logs
        <span class="tab-count">({{ lines.length }})</span>
        <span v-if="appState === 'loading'" class="tab-running">●</span>
      </button>
    </div>

    <!-- Table area -->
    <div v-show="activeTab === 'tickets'" class="table-area">
      <TicketTable :data="tableData ?? emptyData" :appState="appState" />
    </div>

    <!-- Logs area -->
    <div v-show="activeTab === 'logs'" class="table-area log-area">
      <LogViewer :lines="lines" :running="appState === 'loading'" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import LogViewer from '../../shared/LogViewer.vue'
import TicketTable from './TicketTable.vue'
import WorklogDashboard from './WorklogDashboard.vue'
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
const weeklyLog   = ref([])
const labels      = ref([])
const lines       = ref([])
const configHint  = ref('')
const activeTab   = ref('tickets')

const PREF_USER  = 'sprint-default-user:v1'
const PREF_LABEL = 'sprint-default-label:v1'
const TAB_KEY    = 'sprint-active-tab:v1'
const LOG_LIMIT = 500

const emptyData = { tickets: [], stats: { total_tickets: 0, total_log_seconds: 0, total_points: 0, status_counts: {}, type_counts: {} }, meta: {} }

function setTab(tab) {
  activeTab.value = tab
  window.myscriptAPI?.setPref(TAB_KEY, tab)
}

onMounted(() => {
  jiraBin.value = window.myscriptAPI?.getSetting('jira_bin') ?? ''

  // Saved defaults from last run take priority; fall back to Settings values
  user.value  = window.myscriptAPI?.getPref(PREF_USER)
             ?? window.myscriptAPI?.getSetting('jira_user')
             ?? ''
  label.value = window.myscriptAPI?.getPref(PREF_LABEL)
             ?? window.myscriptAPI?.getSetting('jira_label')
             ?? ''

  const configured = jiraBin.value && user.value && label.value
  configHint.value = configured
    ? 'Config loaded from ⚙️ Settings'
    : 'Configure Jira settings in ⚙️ Settings page'

  // Restore active tab (coerce stale values like 'dashboard' to 'tickets')
  const savedTab = window.myscriptAPI?.getPref(TAB_KEY)
  if (savedTab === 'tickets' || savedTab === 'logs') activeTab.value = savedTab
})

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

  // Persist as defaults for next session
  window.myscriptAPI?.setPref(PREF_USER, user.value)
  window.myscriptAPI?.setPref(PREF_LABEL, label.value)

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
  weeklyLog.value = []
  labels.value    = []
  appState.value  = 'loading'
  jobId.value   = crypto.randomUUID()
  activeTab.value = 'logs'   // auto-jump to logs while running

  const jiraUrl = window.myscriptAPI?.getSetting('jira_url') ?? ''
  // Split comma-separated labels into multiple --label args
  const labelList = label.value.split(',').map(l => l.trim()).filter(Boolean)
  const args = ['--jira-bin', jiraBin.value, '--user', user.value, '--json']
  for (const lbl of labelList) args.push('--label', lbl)
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
            weeklyLog.value = parsed.weekly_log ?? []
            labels.value    = parsed.meta?.labels ?? label.value.split(',').map(l => l.trim()).filter(Boolean)
            appState.value  = (parsed.stats?.total_tickets ?? 0) > 0 ? 'done' : 'no-data'
            if (appState.value === 'done') activeTab.value = 'tickets'  // auto-jump to results
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
  background: var(--bg2);
  border-bottom: 2px solid var(--border);
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
  align-items: center;
  gap: 2px;
  padding: 0 12px;
  background: var(--bg2);
  border-bottom: 2px solid var(--border);
  flex-shrink: 0;
}
.tab-btn {
  background: none;
  border: none;
  border-bottom: 2px solid transparent;
  padding: 7px 14px 9px;
  font-size: 12px;
  color: var(--text2);
  cursor: pointer;
  margin-bottom: -2px;
  transition: color 0.15s, border-color 0.15s;
}
.tab-btn:hover { color: var(--fg); }
.tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); font-weight: 600; }

/* ── Table area ───────────────────────────────────────────────────────────── */
.table-area {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-height: 0;
}

/* ── Logs tab ─────────────────────────────────────────────────────────────── */
.tab-count { opacity: 0.6; font-size: 10px; }
.tab-running { color: var(--accent); animation: blink 1s infinite; margin-left: 2px; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.2} }

.log-area {
  padding: 0;
}
.log-area :deep(.log-viewer) {
  height: 100%;
}
</style>
