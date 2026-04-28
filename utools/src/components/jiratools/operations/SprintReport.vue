<template>
  <div class="sprint-report" @click="arDdOpen = false">
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
          >
            <span class="hist-text">{{ lbl }}</span>
            <button class="hist-del" @mousedown.prevent.stop="deleteHistoryItem(lbl)" title="Delete">✕</button>
          </div>
        </div>
      </div>
      <!-- Merged Run / Refresh / Stop button -->
      <button
        class="run-btn"
        :class="{ loading: appState === 'loading', refreshing: isRefreshing }"
        :disabled="!jiraBin || !user || labelArr.length === 0"
        @click="handleRunClick"
      >
        <span class="run-icon" :class="{ spin: isRefreshing || appState === 'loading' }">
          {{ (isRefreshing || appState === 'loading') ? '↻' : '▶' }}
        </span>
        <span class="run-label">{{ isRefreshing ? 'Cancel' : 'Run' }}</span>
      </button>

      <!-- Interval dropdown (always visible) -->
      <div class="ar-group" @click.stop>
        <div class="ar-intv-wrap">
          <button
            class="ar-intv-btn"
            :disabled="!jiraBin || !user || labelArr.length === 0"
            @click.stop="arDdOpen = !arDdOpen"
          >{{ arIntervalLabel }} <span class="chev">▾</span></button>
          <div class="ar-dd-menu" v-show="arDdOpen">
            <div
              v-for="opt in AR_INTERVAL_OPTS"
              :key="opt.label"
              class="ar-dd-item"
              :class="{ sel: opt.secs === null ? !autoRefresh : (autoRefresh && refreshIntervalSecs === opt.secs) }"
              @click="setArInterval(opt.secs)"
            >
              <span class="ar-chk">{{ (opt.secs === null ? !autoRefresh : (autoRefresh && refreshIntervalSecs === opt.secs)) ? '✓' : '' }}</span>
              {{ opt.label }}
            </div>
          </div>
        </div>
      </div>
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
      <span v-if="agoText" class="tab-ago">{{ agoText }}</span>
    </div>

    <!-- Table area -->
    <div v-show="activeTab === 'tickets'" class="table-area">
      <TicketTable :data="tableData ?? emptyData" :appState="appState" :agoText="agoText" />
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
import { useJiraRun } from '../../../composables/useJiraRun.js'
import { useAutoRefresh } from '../../../composables/useAutoRefresh.js'

// ── Extra refs for SprintReport-specific data ────────────────────────────────
const dailyLog  = ref([])
const weeklyLog = ref([])
const labels    = ref([])

const {
  jiraBin, appState, tableData, lines, activeTab,
  lastUpdatedAt, agoText,
  pushLog, stampNow, setTab, restoreTab,
  run: coreRun, stop, initJiraBin, EMPTY_DATA: emptyData,
} = useJiraRun({
  tabPrefKey: 'sprint-active-tab:v1',
  onData(parsed) {
    dailyLog.value  = parsed.daily_log ?? []
    weeklyLog.value = parsed.weekly_log ?? []
    labels.value    = parsed.meta?.labels ?? labelArr.value
    if (autoRefresh.value) startRefreshTimer()
  },
})

const user     = ref('')
const labelArr = ref([])

// ── Label chip input ────────────────────────────────────────────────────────
const newLabelInput    = ref('')
const showLabelHistory = ref(false)
const labelHistory     = ref([])
const LABEL_HIST_KEY   = 'input-history:sprint-label'
const filteredHistory  = computed(() =>
  labelHistory.value.filter(l => !labelArr.value.includes(l) &&
    (!newLabelInput.value || l.toLowerCase().includes(newLabelInput.value.toLowerCase())))
)

function addLabel(lbl) {
  if (lbl && !labelArr.value.includes(lbl)) labelArr.value = [...labelArr.value, lbl]
}
function removeLabel(lbl) { labelArr.value = labelArr.value.filter(l => l !== lbl) }
function addLabelInput() {
  const lbl = newLabelInput.value.trim()
  if (!lbl) return
  addLabel(lbl)
  const hist = (window.myscriptAPI?.getPref(LABEL_HIST_KEY) ?? []).filter(x => x !== lbl)
  hist.unshift(lbl)
  const saved = hist.slice(0, 20)
  window.myscriptAPI?.setPref(LABEL_HIST_KEY, saved)
  labelHistory.value = saved
  newLabelInput.value = ''
}
function pickHistoryLabel(lbl) { addLabel(lbl); showLabelHistory.value = false; newLabelInput.value = '' }
function hideLabelHistory() { setTimeout(() => { showLabelHistory.value = false }, 150) }
function deleteHistoryItem(lbl) {
  const updated = labelHistory.value.filter(x => x !== lbl)
  window.myscriptAPI?.setPref(LABEL_HIST_KEY, updated)
  labelHistory.value = updated
}

const PREF_USER  = 'sprint-default-user:v1'
const PREF_LABEL = 'sprint-default-label:v1'

function buildArgs() {
  const jiraUrl = window.myscriptAPI?.getSetting('jira_url') ?? ''
  const args = ['--jira-bin', jiraBin.value, '--user', user.value, '--json']
  for (const lbl of labelArr.value) args.push('--label', lbl)
  if (jiraUrl) args.push('--jira-url', jiraUrl)
  return args
}

// ── Auto-refresh ────────────────────────────────────────────────────────────
const {
  autoRefresh, refreshIntervalSecs, isRefreshing, nextRefreshIn,
  startRefreshTimer, setAutoRefresh, restoreAutoRefresh,
} = useAutoRefresh({
  appState,
  buildArgs,
  applyData(parsed) {
    tableData.value  = parsed
    dailyLog.value   = parsed.daily_log ?? []
    weeklyLog.value  = parsed.weekly_log ?? []
    labels.value     = parsed.meta?.labels ?? labelArr.value
    stampNow()
    if ((parsed.stats?.total_tickets ?? 0) > 0 && appState.value !== 'loading') {
      appState.value = 'done'
    }
  },
  canRun: () => !!jiraBin.value && !!user.value && labelArr.value.length > 0,
  pushLog,
  prefKeyAR: 'sprint-auto-refresh:v1',
  prefKeyInterval: 'sprint-auto-refresh-secs:v1',
  defaultIntervalSecs: 300,
})

const arDdOpen = ref(false)

const AR_INTERVAL_OPTS = [
  { label: 'Off',  secs: null },
  { label: '30s',  secs: 30 },
  { label: '1m',   secs: 60 },
  { label: '2m',   secs: 120 },
  { label: '5m',   secs: 300 },
  { label: '10m',  secs: 600 },
  { label: '15m',  secs: 900 },
  { label: '30m',  secs: 1800 },
]

function formatInterval(secs) {
  if (!secs) return 'Off'
  return secs < 60 ? `${secs}s` : `${secs / 60}m`
}

const arIntervalLabel = computed(() =>
  autoRefresh.value ? formatInterval(refreshIntervalSecs.value) : 'Off'
)

function setArInterval(secs) {
  arDdOpen.value = false
  setAutoRefresh(secs !== null, secs)
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────
onMounted(() => {
  initJiraBin()
  user.value = window.myscriptAPI?.getPref(PREF_USER)
             ?? window.myscriptAPI?.getSetting('jira_user') ?? ''
  const rawLabel = window.myscriptAPI?.getPref(PREF_LABEL)
                ?? window.myscriptAPI?.getSetting('jira_label') ?? ''
  labelArr.value = Array.isArray(rawLabel)
    ? rawLabel
    : rawLabel ? rawLabel.split(',').map(l => l.trim()).filter(Boolean) : []
  labelHistory.value = window.myscriptAPI?.getPref(LABEL_HIST_KEY) ?? []
  restoreTab()
  restoreAutoRefresh()
})

function handleRunClick() {
  if (isRefreshing.value) {
    isRefreshing.value = false
  } else if (appState.value === 'loading') {
    stop()
  } else {
    run()
  }
}

function run() {
  if (!jiraBin.value || !user.value || labelArr.value.length === 0) return
  window.myscriptAPI?.setPref(PREF_USER, user.value)
  window.myscriptAPI?.setPref(PREF_LABEL, labelArr.value)
  for (const lbl of labelArr.value) {
    const hist = (window.myscriptAPI?.getPref(LABEL_HIST_KEY) ?? []).filter(x => x !== lbl)
    hist.unshift(lbl)
    window.myscriptAPI?.setPref(LABEL_HIST_KEY, hist.slice(0, 20))
  }
  labelHistory.value = window.myscriptAPI?.getPref(LABEL_HIST_KEY) ?? []
  coreRun(buildArgs())
}
</script>

<style scoped>
.sprint-report {
  display: flex;
  flex-direction: column;
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
  min-width: 120px;
  position: relative;
  overflow: hidden;
}
.sprint-labels {
  display: flex;
  flex-wrap: nowrap;
  align-items: center;
  gap: 4px;
  min-height: 28px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg);
  padding: 3px 6px;
  cursor: text;
  overflow-x: auto;
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
  min-width: 280px;
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
  display: flex;
  align-items: center;
  gap: 4px;
}
.hist-text {
  flex: 1;
  white-space: nowrap;
}
.hist-del {
  flex-shrink: 0;
  background: none;
  border: none;
  color: var(--text3, #999);
  font-size: 10px;
  cursor: pointer;
  padding: 2px 4px;
  border-radius: 3px;
  opacity: 0;
  transition: opacity .12s, color .12s;
}
.hist-item:hover .hist-del { opacity: 1; }
.hist-del:hover { color: var(--red, #e53e3e); background: rgba(229,62,62,.1); }
.hist-item:hover { background: color-mix(in srgb, var(--accent) 10%, transparent); color: var(--accent); }

/* Run / Stop → merged Run button ────────────────────────────────────────── */
.run-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  flex-shrink: 0;
  padding: 4px 12px;
  font-size: 12px;
  font-weight: 600;
  background: var(--accent);
  color: #fff;
  border: none;
  border-radius: var(--radius) 0 0 var(--radius);
  cursor: pointer;
  white-space: nowrap;
  transition: opacity .12s;
}
.run-btn:hover:not(:disabled) { filter: brightness(1.1); }
.run-btn:disabled { opacity: 0.45; cursor: not-allowed; }

.run-icon {
  font-size: 13px;
  display: inline-block;
  line-height: 1;
}
.run-icon.spin { animation: ar-spin 0.8s linear infinite; }
@keyframes ar-spin {
  from { transform: rotate(0deg); }
  to   { transform: rotate(360deg); }
}
.run-label { font-size: 12px; font-weight: 600; }
.run-cd { font-size: 10px; opacity: 0.7; min-width: 22px; }

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
.tab-ago { margin-left: auto; font-size: 10.5px; color: var(--text3); white-space: nowrap; }

/* ── Table area ───────────────────────────────────────────────────────────── */
.table-area {
  display: flex;
  flex-direction: column;
}

/* ── Logs tab ─────────────────────────────────────────────────────────────── */
.tab-count { opacity: 0.6; font-size: 10px; }
.tab-running { color: var(--accent); animation: blink 1s infinite; margin-left: 2px; }
@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0.2} }

.log-area { padding: 0; }
.log-area :deep(.log-viewer) { height: 100%; }

/* ── Auto-refresh controls ──────────────────────────────────────────────── */
.ar-group {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}
.ar-intv-wrap { position: relative; }
.ar-intv-btn {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 0 var(--radius) var(--radius) 0;
  background: var(--bg);
  color: var(--fg);
  cursor: pointer;
  white-space: nowrap;
  height: 26px;
  transition: background .12s;
}
.ar-intv-btn:hover:not(:disabled) { background: var(--bg2); }
.ar-intv-btn:disabled { opacity: .45; cursor: not-allowed; }
.ar-intv-btn .chev { font-size: 10px; opacity: 0.6; }
.ar-dd-menu {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  min-width: 80px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: var(--radius);
  box-shadow: 0 4px 12px rgba(0,0,0,.15);
  z-index: 200;
  overflow: hidden;
}
.ar-dd-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 12px;
  font-size: 12px;
  cursor: pointer;
  color: var(--fg);
  white-space: nowrap;
}
.ar-dd-item:hover { background: var(--bg2); }
.ar-dd-item.sel { color: var(--accent); font-weight: 600; }
.ar-chk { width: 12px; font-size: 11px; }
</style>
