<template>
  <div class="sprint-report">
    <!-- Form (collapsible) -->
    <div class="form-section" :class="{ collapsed: formCollapsed }">
      <div class="form-header" @click="toggleForm">
        <span class="form-toggle">{{ formCollapsed ? '▶' : '▼' }}</span>
        <span class="form-title">📊 Sprint Report</span>
        <template v-if="formCollapsed && (user || label)">
          <span class="form-summary">{{ user || '—' }} · {{ label || '—' }}</span>
        </template>
      </div>
      <form v-show="!formCollapsed" class="op-form" @submit.prevent="run">
        <div v-if="!jiraBin" class="config-warn">
          ⚠️ Jira CLI path not configured. Go to <a href="#" @click.prevent="$emit('openSettings')">⚙️ Settings</a> to set it.
        </div>
        <div class="form-row">
          <div class="form-group">
            <label>Jira user</label>
            <InputWithHistory ref="userRef" v-model="user" storageKey="sprint-user" placeholder="xchen17" required />
          </div>
        </div>
        <div class="form-group">
          <label>Sprint label(s)</label>
          <LabelTransfer ref="labelTransferRef" v-model="labelArr" historyKey="sprint-label" />
        </div>
        <div class="form-footer">
          <span class="config-hint">{{ configHint }}</span>
        </div>
      </form>
      <div v-show="!formCollapsed" class="form-cta">
        <button
          type="button"
          class="btn cta-run"
          :disabled="appState === 'loading' || !jiraBin || !user || labelArr.length === 0"
          @click="run"
        >{{ appState === 'loading' ? '⏳ Running…' : '▶ Run' }}</button>
        <button
          v-if="appState === 'loading'"
          type="button"
          class="btn cta-stop"
          @click="stop"
        >■ Stop</button>
      </div>
    </div>

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
import { ref, computed, onMounted } from 'vue'
import LogViewer from '../../shared/LogViewer.vue'
import TicketTable from './TicketTable.vue'
import WorklogDashboard from './WorklogDashboard.vue'
import InputWithHistory from '../../shared/InputWithHistory.vue'
import LabelTransfer from './LabelTransfer.vue'

const jiraBin  = ref('')
const user     = ref('')
const labelArr = ref([])
const label    = computed(() => labelArr.value.join(','))
const jobId    = ref(null)

const userRef          = ref(null)
const labelTransferRef = ref(null)

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
const FORM_COLLAPSED_KEY = 'sprint-form-collapsed:v1'
const LOG_LIMIT = 500

const formCollapsed = ref(true)

const emptyData = { tickets: [], stats: { total_tickets: 0, total_log_seconds: 0, total_points: 0, status_counts: {}, type_counts: {} }, meta: {} }

function setTab(tab) {
  activeTab.value = tab
  window.myscriptAPI?.setPref(TAB_KEY, tab)
}

function toggleForm() {
  formCollapsed.value = !formCollapsed.value
  window.myscriptAPI?.setPref(FORM_COLLAPSED_KEY, formCollapsed.value)
}

onMounted(() => {
  jiraBin.value = window.myscriptAPI?.getSetting('jira_bin') ?? ''

  // Saved defaults from last run take priority; fall back to Settings values
  user.value  = window.myscriptAPI?.getPref(PREF_USER)
             ?? window.myscriptAPI?.getSetting('jira_user')
             ?? ''
  const rawLabel = window.myscriptAPI?.getPref(PREF_LABEL)
                ?? window.myscriptAPI?.getSetting('jira_label')
                ?? ''
  labelArr.value = Array.isArray(rawLabel)
    ? rawLabel
    : rawLabel ? rawLabel.split(',').map(l => l.trim()).filter(Boolean) : []

  const configured = jiraBin.value && user.value && label.value
  configHint.value = configured
    ? 'Config loaded from ⚙️ Settings'
    : 'Configure Jira settings in ⚙️ Settings page'

  // Restore active tab (coerce stale values like 'dashboard' to 'tickets')
  const savedTab = window.myscriptAPI?.getPref(TAB_KEY)
  if (savedTab === 'tickets' || savedTab === 'logs') activeTab.value = savedTab

  // Restore form collapsed state (default: collapsed)
  const savedCollapsed = window.myscriptAPI?.getPref(FORM_COLLAPSED_KEY)
  formCollapsed.value = savedCollapsed !== false
})

function pushLog(line) {
  if (lines.value.length < LOG_LIMIT) {
    lines.value.push(line)
  } else if (lines.value.length === LOG_LIMIT) {
    lines.value.push(`… (log truncated at ${LOG_LIMIT} lines)`)
  }
}

function run() {
  if (!jiraBin.value || !user.value || labelArr.value.length === 0) return

  userRef.value?.push(user.value)

  // Persist as defaults for next session and update label history
  window.myscriptAPI?.setPref(PREF_USER, user.value)
  window.myscriptAPI?.setPref(PREF_LABEL, labelArr.value)
  const LABEL_HIST_KEY = 'input-history:sprint-label'
  for (const lbl of labelArr.value) {
    const hist = (window.myscriptAPI?.getPref(LABEL_HIST_KEY) ?? []).filter(x => x !== lbl)
    hist.unshift(lbl)
    window.myscriptAPI?.setPref(LABEL_HIST_KEY, hist.slice(0, 20))
  }
  labelTransferRef.value?.refreshHistory()

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
  const labelList = labelArr.value
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
            labels.value    = parsed.meta?.labels ?? labelArr.value
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
.form-section {
  flex-shrink: 0;
  background: var(--bg2);
  border-bottom: 2px solid var(--border);
}

.form-header {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  cursor: pointer;
  user-select: none;
}
.form-header:hover { background: var(--bg3); }

.form-toggle {
  font-size: 9px;
  color: var(--text2);
  width: 12px;
  text-align: center;
}
.form-title {
  font-size: 12px;
  font-weight: 600;
  color: var(--fg);
}
.form-summary {
  font-size: 11px;
  color: var(--text2);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
  min-width: 0;
}
.form-header-actions {
  display: flex;
  gap: 4px;
  flex-shrink: 0;
  margin-left: auto;
}
.btn-sm { padding: 3px 10px; font-size: 11px; }

.op-form {
  padding: 6px 12px 10px;
  display: flex;
  flex-direction: column;
  gap: 8px;
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

.form-cta {
  display: flex;
  gap: 8px;
  padding: 0 12px 10px;
}
.cta-run {
  flex: 1;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  padding: 8px 0;
  background: var(--accent);
  color: #fff;
  border-radius: var(--radius);
}
.cta-run:hover:not(:disabled) { filter: brightness(1.12); }
.cta-run:disabled { opacity: 0.45; cursor: not-allowed; }
.cta-stop {
  padding: 8px 16px;
  background: var(--red);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  border-radius: var(--radius);
}
.cta-stop:hover { filter: brightness(0.9); }

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
  min-width: 0;
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
