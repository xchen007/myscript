<template>
  <div class="sprint-report">
    <!-- Always-visible header: title + inline inputs + run -->
    <div class="sprint-header">
      <span class="sprint-title">📊 Sprint Report</span>
      <input
        v-model="user"
        class="sprint-input sprint-user"
        placeholder="User"
      />
      <div class="sprint-labels-wrap">
        <div class="sprint-labels">
          <span v-for="lbl in labelArr" :key="lbl" class="label-chip">
            <span class="chip-text">{{ lbl }}</span>
            <button class="chip-rm" @click="removeLabel(lbl)" tabindex="-1">✕</button>
          </span>
          <input
            v-model="newLabelInput"
            class="label-add-input"
            :placeholder="labelArr.length ? '+ label' : 'Sprint label, Enter to add'"
            @keydown.enter.prevent="addLabelInput"
            @focus="showLabelHistory = true"
            @blur="hideLabelHistory"
          />
        </div>
        <div v-if="showLabelHistory && filteredHistory.length" class="label-hist-drop">
          <div
            v-for="lbl in filteredHistory"
            :key="lbl"
            class="hist-item"
            @mousedown.prevent="pickHistoryLabel(lbl)"
          >{{ lbl }}</div>
        </div>
      </div>
      <button
        class="btn sprint-run-btn"
        :disabled="appState === 'loading' || !jiraBin || !user || labelArr.length === 0"
        @click="run"
      >{{ appState === 'loading' ? '⏳' : '▶ Run' }}</button>
      <button v-if="appState === 'loading'" class="btn sprint-stop-btn" @click="stop">■</button>
    </div>

    <div v-if="!jiraBin" class="config-warn-bar">
      ⚠️ Jira CLI not configured — go to ⚙️ Settings
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

const jiraBin  = ref('')
const user     = ref('')
const labelArr = ref([])
const label    = computed(() => labelArr.value.join(','))
const jobId    = ref(null)

// Label chip input state
const newLabelInput   = ref('')
const showLabelHistory = ref(false)
const labelHistory    = ref([])
const filteredHistory = computed(() =>
  labelHistory.value.filter(l => !labelArr.value.includes(l) &&
    (!newLabelInput.value || l.toLowerCase().includes(newLabelInput.value.toLowerCase())))
)

function addLabel(lbl) {
  if (lbl && !labelArr.value.includes(lbl)) labelArr.value = [...labelArr.value, lbl]
}
function removeLabel(lbl) {
  labelArr.value = labelArr.value.filter(l => l !== lbl)
}
function addLabelInput() {
  const lbl = newLabelInput.value.trim()
  if (!lbl) return
  addLabel(lbl)
  // Persist to history
  const LABEL_HIST_KEY = 'input-history:sprint-label'
  const hist = (window.myscriptAPI?.getPref(LABEL_HIST_KEY) ?? []).filter(x => x !== lbl)
  hist.unshift(lbl)
  const saved = hist.slice(0, 20)
  window.myscriptAPI?.setPref(LABEL_HIST_KEY, saved)
  labelHistory.value = saved
  newLabelInput.value = ''
}
function pickHistoryLabel(lbl) {
  addLabel(lbl)
  showLabelHistory.value = false
  newLabelInput.value = ''
}
function hideLabelHistory() {
  setTimeout(() => { showLabelHistory.value = false }, 150)
}

// 'idle' | 'loading' | 'done' | 'no-data' | 'error'
const appState    = ref('idle')
const tableData   = ref(null)
const dailyLog    = ref([])
const weeklyLog   = ref([])
const labels      = ref([])
const lines       = ref([])
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

  user.value = window.myscriptAPI?.getPref(PREF_USER)
             ?? window.myscriptAPI?.getSetting('jira_user')
             ?? ''
  const rawLabel = window.myscriptAPI?.getPref(PREF_LABEL)
                ?? window.myscriptAPI?.getSetting('jira_label')
                ?? ''
  labelArr.value = Array.isArray(rawLabel)
    ? rawLabel
    : rawLabel ? rawLabel.split(',').map(l => l.trim()).filter(Boolean) : []

  labelHistory.value = window.myscriptAPI?.getPref('input-history:sprint-label') ?? []

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
  if (!jiraBin.value || !user.value || labelArr.value.length === 0) return

  // Persist defaults and label history
  window.myscriptAPI?.setPref(PREF_USER, user.value)
  window.myscriptAPI?.setPref(PREF_LABEL, labelArr.value)
  const LABEL_HIST_KEY = 'input-history:sprint-label'
  for (const lbl of labelArr.value) {
    const hist = (window.myscriptAPI?.getPref(LABEL_HIST_KEY) ?? []).filter(x => x !== lbl)
    hist.unshift(lbl)
    window.myscriptAPI?.setPref(LABEL_HIST_KEY, hist.slice(0, 20))
  }
  labelHistory.value = window.myscriptAPI?.getPref(LABEL_HIST_KEY) ?? []

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

/* ── Inline header bar ───────────────────────────────────────────────────── */
.sprint-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 12px;
  background: var(--bg2);
  border-bottom: 2px solid var(--border);
  flex-shrink: 0;
  flex-wrap: nowrap;
  min-width: 0;
}

.sprint-title {
  font-size: 12px;
  font-weight: 700;
  color: var(--fg);
  white-space: nowrap;
  flex-shrink: 0;
}

.sprint-input {
  height: 28px;
  font-size: 12px;
  padding: 0 8px;
}
.sprint-user {
  width: 110px;
  flex-shrink: 0;
}

/* Label chips + type-to-add ─────────────────────────────────────────────── */
.sprint-labels-wrap {
  flex: 1;
  min-width: 0;
  position: relative;
}
.sprint-labels {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
  min-height: 28px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg);
  padding: 3px 6px;
  cursor: text;
}
.label-chip {
  display: inline-flex;
  align-items: center;
  gap: 3px;
  background: color-mix(in srgb, var(--accent) 15%, transparent);
  color: var(--accent);
  border-radius: 10px;
  padding: 1px 6px 1px 8px;
  font-size: 11px;
  white-space: nowrap;
}
.chip-text { max-width: 160px; overflow: hidden; text-overflow: ellipsis; }
.chip-rm {
  background: none;
  border: none;
  color: inherit;
  opacity: 0.6;
  cursor: pointer;
  font-size: 10px;
  padding: 0;
  line-height: 1;
  flex-shrink: 0;
}
.chip-rm:hover { opacity: 1; }
.label-add-input {
  border: none;
  outline: none;
  background: transparent;
  font-size: 11px;
  padding: 0 2px;
  min-width: 80px;
  flex: 1;
  color: var(--fg);
}
.label-hist-drop {
  position: absolute;
  top: calc(100% + 2px);
  left: 0;
  right: 0;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 4px 12px rgba(0,0,0,.15);
  z-index: 100;
  max-height: 160px;
  overflow-y: auto;
}
.hist-item {
  padding: 5px 10px;
  font-size: 11.5px;
  cursor: pointer;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.hist-item:hover { background: color-mix(in srgb, var(--accent) 10%, transparent); color: var(--accent); }

/* Run / Stop ────────────────────────────────────────────────────────────── */
.sprint-run-btn {
  flex-shrink: 0;
  padding: 5px 16px;
  font-size: 12px;
  font-weight: 600;
  background: var(--accent);
  color: #fff;
  border-radius: var(--radius);
  white-space: nowrap;
}
.sprint-run-btn:hover:not(:disabled) { filter: brightness(1.1); }
.sprint-run-btn:disabled { opacity: 0.45; cursor: not-allowed; }
.sprint-stop-btn {
  flex-shrink: 0;
  padding: 5px 12px;
  font-size: 12px;
  font-weight: 600;
  background: var(--red);
  color: #fff;
  border-radius: var(--radius);
}
.sprint-stop-btn:hover { filter: brightness(0.9); }

.config-warn-bar {
  flex-shrink: 0;
  font-size: 11px;
  color: var(--yellow);
  padding: 4px 12px;
  background: color-mix(in srgb, var(--yellow) 10%, transparent);
}

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

.log-area { padding: 0; }
.log-area :deep(.log-viewer) { height: 100%; }
</style>
