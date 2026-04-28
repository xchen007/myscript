<template>
  <div class="epic-query" @click="arDdOpen = false">
    <!-- Header: title + inputs + run -->
    <div class="epic-header">
      <span class="epic-title">🏷️ Epic Query</span>
      <input
        v-model="epicKey"
        class="epic-input epic-key-input"
        placeholder="Epic Key (e.g. SDSTOR-21000)"
        @keydown.enter="run"
      />
      <input
        v-model="labelFilter"
        class="epic-input epic-filter-input"
        placeholder="Label filter (e.g. SDS-CP-Sprint)"
      />
      <button
        class="btn epic-run-btn"
        :disabled="appState === 'loading' || !jiraBin || !epicKey.trim()"
        @click="run"
      >{{ appState === 'loading' ? '⏳' : '▶ Run' }}</button>
      <button v-if="appState === 'loading'" class="btn epic-stop-btn" @click="stop">■</button>
      <span class="header-spacer" />
      <span v-if="lastUpdatedAt" class="ago-hint">{{ agoText }}</span>

      <!-- Auto-refresh dropdown (Grafana style) -->
      <div class="ar-dd-wrap" @click.stop>
        <button
          class="btn ar-dd-btn"
          :class="{ active: autoRefresh }"
          :disabled="!jiraBin || !epicKey.trim()"
          @click.stop="arDdOpen = !arDdOpen"
        >
          🔄 Refresh
          <span class="ar-interval-badge">{{ autoRefresh ? `${refreshIntervalMin}m` : 'Off' }}</span>
          <span v-if="autoRefresh" class="ar-countdown-badge">{{ isRefreshing ? '…' : `${nextRefreshIn}s` }}</span>
          <span class="chev">▾</span>
        </button>
        <div class="ar-dd-menu" v-show="arDdOpen">
          <div
            class="ar-dd-item"
            :class="{ sel: !autoRefresh }"
            @click="setArInterval(null)"
          >
            <span class="ar-chk">{{ !autoRefresh ? '✓' : '' }}</span> Off
          </div>
          <div
            v-for="m in [1, 2, 5, 10, 15, 30]"
            :key="m"
            class="ar-dd-item"
            :class="{ sel: autoRefresh && refreshIntervalMin === m }"
            @click="setArInterval(m)"
          >
            <span class="ar-chk">{{ autoRefresh && refreshIntervalMin === m ? '✓' : '' }}</span> {{ m }}m
          </div>
        </div>
      </div>
    </div>

    <div v-if="!jiraBin" class="config-warn-bar">
      ⚠️ Jira CLI not configured — go to ⚙️ Settings
    </div>

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
      <TicketTable
        :data="tableData ?? emptyData"
        :appState="appState"
        :labelFilter="labelFilter"
        prefKey="epic-table-prefs:v1"
      />
    </div>

    <!-- Logs area -->
    <div v-show="activeTab === 'logs'" class="table-area log-area">
      <LogViewer :lines="lines" :running="appState === 'loading'" />
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, onUnmounted } from 'vue'
import LogViewer from '../../shared/LogViewer.vue'
import TicketTable from './TicketTable.vue'

const jiraBin     = ref('')
const epicKey     = ref('')
const labelFilter = ref('')
const jobId       = ref(null)

const appState    = ref('idle')
const tableData   = ref(null)
const lines       = ref([])
const activeTab   = ref('tickets')
const lastUpdatedAt = ref(0)
const agoTick     = ref(0)
let agoTimer = null

// Auto-refresh state
const autoRefresh        = ref(false)
const refreshIntervalMin = ref(5)
const isRefreshing       = ref(false)
const nextRefreshIn      = ref(0)
const arDdOpen           = ref(false)
let refreshTimer   = null
let countdownTimer = null

const PREF_EPIC   = 'epic-default-key:v1'
const PREF_FILTER = 'epic-default-filter:v1'
const TAB_KEY     = 'epic-active-tab:v1'
const PREF_AR     = 'epic-auto-refresh:v1'
const PREF_AR_MIN = 'epic-auto-refresh-min:v1'
const LOG_LIMIT   = 500

const emptyData = {
  tickets: [], stats: { total_tickets: 0, total_log_seconds: 0, total_points: 0, status_counts: {}, type_counts: {} }, meta: {}
}

function stampNow() {
  lastUpdatedAt.value = Date.now()
  if (!agoTimer) {
    agoTimer = setInterval(() => { agoTick.value++ }, 10_000)
  }
}
const agoText = computed(() => {
  void agoTick.value
  if (!lastUpdatedAt.value) return ''
  const secs = Math.floor((Date.now() - lastUpdatedAt.value) / 1000)
  if (secs < 10) return 'just now'
  if (secs < 60) return `${secs}s ago`
  const mins = Math.floor(secs / 60)
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  return `${hrs}h${mins % 60}m ago`
})

function setTab(tab) {
  activeTab.value = tab
  window.myscriptAPI?.setPref(TAB_KEY, tab)
}

function buildArgs() {
  const key = epicKey.value.trim()
  const jiraUrl = window.myscriptAPI?.getSetting('jira_url') ?? ''
  const args = ['--jira-bin', jiraBin.value, '--epic', key, '--json']
  if (jiraUrl) args.push('--jira-url', jiraUrl)
  return args
}

/* ── Auto-refresh helpers ────────────────────────────────────────────────── */
function applyRefreshData(parsed) {
  tableData.value = parsed
  stampNow()
  if ((parsed.stats?.total_tickets ?? 0) > 0 && appState.value !== 'loading') {
    appState.value = 'done'
  }
}

function runBackground() {
  if (!jiraBin.value || !epicKey.value.trim()) return
  if (isRefreshing.value) return
  isRefreshing.value = true
  const bgJobId = `bg-${crypto.randomUUID()}`
  const bgLines = []

  try {
    window.myscriptAPI.runTool(
      bgJobId, 'jira-analyzer', buildArgs(),
      () => {},
      (code) => {
        isRefreshing.value = false
        if (code !== 0) return  // discard failed refresh
      },
      (line) => {
        if (line.startsWith('__SPRINT_TABLE_JSON__:')) {
          try {
            const parsed = JSON.parse(line.slice('__SPRINT_TABLE_JSON__:'.length))
            applyRefreshData(parsed)
          } catch (_) { /* ignore parse error in bg */ }
        }
      },
    )
  } catch (_) {
    isRefreshing.value = false
  }
}

function startRefreshTimer() {
  stopRefreshTimer()
  const secs = refreshIntervalMin.value * 60
  nextRefreshIn.value = secs
  countdownTimer = setInterval(() => {
    nextRefreshIn.value = Math.max(0, nextRefreshIn.value - 1)
  }, 1000)
  refreshTimer = setInterval(() => {
    nextRefreshIn.value = secs
    runBackground()
  }, secs * 1000)
}

function stopRefreshTimer() {
  if (refreshTimer)  { clearInterval(refreshTimer);  refreshTimer = null }
  if (countdownTimer) { clearInterval(countdownTimer); countdownTimer = null }
  nextRefreshIn.value = 0
}

// Unified setter: null = Off, number = interval in minutes
function setArInterval(intervalMin) {
  arDdOpen.value = false
  if (intervalMin === null) {
    autoRefresh.value = false
    window.myscriptAPI?.setPref(PREF_AR, false)
    stopRefreshTimer()
  } else {
    const v = Math.max(1, Math.min(60, Number(intervalMin) || 5))
    refreshIntervalMin.value = v
    window.myscriptAPI?.setPref(PREF_AR_MIN, v)
    autoRefresh.value = true
    window.myscriptAPI?.setPref(PREF_AR, true)
    startRefreshTimer()
  }
}

onUnmounted(() => {
  stopRefreshTimer()
  if (agoTimer) clearInterval(agoTimer)
})

onMounted(() => {
  jiraBin.value = window.myscriptAPI?.getSetting('jira_bin') ?? ''
  epicKey.value = window.myscriptAPI?.getPref(PREF_EPIC) ?? ''
  labelFilter.value = window.myscriptAPI?.getPref(PREF_FILTER) ?? ''
  const savedTab = window.myscriptAPI?.getPref(TAB_KEY)
  if (savedTab === 'tickets' || savedTab === 'logs') activeTab.value = savedTab

  // Restore auto-refresh prefs
  const savedAR = window.myscriptAPI?.getPref(PREF_AR)
  if (savedAR === true) autoRefresh.value = true
  const savedARMin = window.myscriptAPI?.getPref(PREF_AR_MIN)
  if (savedARMin) refreshIntervalMin.value = Number(savedARMin) || 5
})

function pushLog(line) {
  if (lines.value.length < LOG_LIMIT) {
    lines.value.push(line)
  } else if (lines.value.length === LOG_LIMIT) {
    lines.value.push(`… (log truncated at ${LOG_LIMIT} lines)`)
  }
}

function run() {
  const key = epicKey.value.trim()
  if (!jiraBin.value || !key) return

  window.myscriptAPI?.setPref(PREF_EPIC, key)
  window.myscriptAPI?.setPref(PREF_FILTER, labelFilter.value)

  if (!window.myscriptAPI?.isReady()) {
    lines.value = ['[error] Project root not found. Run: make install inside the myscript directory.']
    appState.value = 'error'
    return
  }

  if (jobId.value && appState.value === 'loading') {
    window.myscriptAPI.stopTool(jobId.value)
  }

  lines.value     = []
  appState.value  = 'loading'
  jobId.value     = crypto.randomUUID()
  activeTab.value = 'logs'

  const args = buildArgs()

  try {
    window.myscriptAPI.runTool(
      jobId.value,
      'jira-analyzer',
      args,
      (line) => pushLog(line),
      (code) => {
        if (appState.value === 'loading') {
          appState.value = code === 0 ? 'no-data' : 'error'
        }
      },
      (line) => {
        if (line.startsWith('__SPRINT_TABLE_JSON__:')) {
          try {
            const parsed = JSON.parse(line.slice('__SPRINT_TABLE_JSON__:'.length))
            tableData.value = parsed
            appState.value  = (parsed.stats?.total_tickets ?? 0) > 0 ? 'done' : 'no-data'
            stampNow()
            if (appState.value === 'done') {
              activeTab.value = 'tickets'
              if (autoRefresh.value) startRefreshTimer()
            }
          } catch (e) {
            pushLog(`[error] Failed to parse data: ${e.message}`)
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
.epic-query {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.epic-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
  background: var(--bg2);
}
.epic-title {
  font-size: 13px;
  font-weight: 700;
  color: var(--fg);
  white-space: nowrap;
}
.epic-input {
  font-size: 12px;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg);
  color: var(--fg);
}
.epic-key-input { width: 180px; }
.epic-filter-input { width: 160px; }
.epic-run-btn {
  background: var(--accent); color: #fff; border: none;
  padding: 4px 14px; border-radius: var(--radius);
  font-size: 12px; font-weight: 600; cursor: pointer;
  white-space: nowrap;
}
.epic-run-btn:disabled { opacity: .5; cursor: not-allowed; }
.epic-stop-btn {
  background: var(--red); color: #fff; border: none;
  padding: 4px 10px; border-radius: var(--radius);
  font-size: 12px; cursor: pointer;
}

.config-warn-bar {
  background: #fef2f2; color: #b91c1c;
  padding: 5px 12px; font-size: 11px;
  border-bottom: 1px solid #fecaca; flex-shrink: 0;
}

.tab-bar {
  display: flex; gap: 0; border-bottom: 2px solid var(--border);
  padding: 0 12px; background: var(--bg2); flex-shrink: 0;
}
.tab-btn {
  padding: 6px 14px; font-size: 12px; font-weight: 600;
  background: none; border: none; border-bottom: 2px solid transparent;
  margin-bottom: -2px; cursor: pointer; color: var(--text2);
  display: flex; align-items: center; gap: 4px;
  transition: color .12s, border-color .12s;
}
.tab-btn:hover { color: var(--fg); }
.tab-btn.active { color: var(--accent); border-bottom-color: var(--accent); }
.tab-count { font-weight: 400; color: var(--text3); font-size: 11px; }
.tab-running { color: var(--accent); font-size: 8px; animation: pulse 1s infinite; }
@keyframes pulse { 0%,100%{opacity:.3} 50%{opacity:1} }

.table-area { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.log-area { overflow-y: auto; }

/* ── ago hint + auto-refresh ────────────────────────────────────────────── */
.ago-hint {
  font-size: 11px;
  color: var(--fg-dim, var(--fg));
  opacity: 0.55;
  white-space: nowrap;
  flex-shrink: 0;
}
.header-spacer { flex: 1; }

/* Grafana-style refresh dropdown */
.ar-dd-wrap {
  position: relative;
  flex-shrink: 0;
}
.ar-dd-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  font-size: 12px;
  padding: 3px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg);
  color: var(--fg);
  cursor: pointer;
  white-space: nowrap;
}
.ar-dd-btn:disabled { opacity: .45; cursor: not-allowed; }
.ar-dd-btn.active {
  border-color: var(--accent);
  color: var(--accent);
}
.ar-interval-badge {
  font-size: 11px;
  font-weight: 600;
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: 3px;
  padding: 0 5px;
  line-height: 18px;
}
.ar-dd-btn.active .ar-interval-badge {
  background: var(--accent);
  border-color: var(--accent);
  color: #fff;
}
.ar-countdown-badge {
  font-size: 10px;
  opacity: 0.6;
  min-width: 24px;
  text-align: right;
}
.ar-dd-btn .chev { font-size: 10px; opacity: 0.7; }

.ar-dd-menu {
  position: absolute;
  top: calc(100% + 4px);
  right: 0;
  min-width: 90px;
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
