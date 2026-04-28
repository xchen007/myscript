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
      <!-- Merged Run / Refresh / Stop button -->
      <button
        class="btn run-btn"
        :class="{ loading: appState === 'loading', refreshing: isRefreshing }"
        :disabled="!jiraBin || !epicKey.trim()"
        @click="handleRunClick"
      >
        <span class="run-icon" :class="{ spin: isRefreshing || appState === 'loading' }">
          {{ (isRefreshing || appState === 'loading') ? '↻' : '▶' }}
        </span>
        <span class="run-label">Run</span>
      </button>
      <span class="header-spacer" />
      <span v-if="lastUpdatedAt" class="ago-hint">{{ agoText }}</span>

      <!-- Interval dropdown (always visible) -->
      <div class="ar-group" @click.stop>
        <div class="ar-intv-wrap">
          <button
            class="ar-intv-btn"
            :disabled="!jiraBin || !epicKey.trim()"
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
import { ref, computed, onMounted } from 'vue'
import LogViewer from '../../shared/LogViewer.vue'
import TicketTable from './TicketTable.vue'
import { useJiraRun } from '../../../composables/useJiraRun.js'
import { useAutoRefresh } from '../../../composables/useAutoRefresh.js'

const {
  jiraBin, appState, tableData, lines, activeTab,
  lastUpdatedAt, agoText,
  pushLog, stampNow, setTab, restoreTab,
  run: coreRun, stop, initJiraBin, EMPTY_DATA: emptyData,
} = useJiraRun({
  tabPrefKey: 'epic-active-tab:v1',
  onData(parsed) {
    if (autoRefresh.value) startRefreshTimer()
  },
})

const epicKey     = ref('')
const labelFilter = ref('')

const PREF_EPIC   = 'epic-default-key:v1'
const PREF_FILTER = 'epic-default-filter:v1'

function buildArgs() {
  const key = epicKey.value.trim()
  const jiraUrl = window.myscriptAPI?.getSetting('jira_url') ?? ''
  const args = ['--jira-bin', jiraBin.value, '--epic', key, '--json']
  if (jiraUrl) args.push('--jira-url', jiraUrl)
  return args
}

// ── Auto-refresh ────────────────────────────────────────────────────────────
const arDdOpen = ref(false)

const {
  autoRefresh, refreshIntervalSecs, isRefreshing, nextRefreshIn,
  startRefreshTimer, setAutoRefresh, restoreAutoRefresh,
} = useAutoRefresh({
  appState,
  buildArgs,
  applyData(parsed) {
    tableData.value = parsed
    stampNow()
    if ((parsed.stats?.total_tickets ?? 0) > 0 && appState.value !== 'loading') {
      appState.value = 'done'
    }
  },
  canRun: () => !!jiraBin.value && !!epicKey.value.trim(),
  pushLog,
  prefKeyAR: 'epic-auto-refresh:v1',
  prefKeyInterval: 'epic-auto-refresh-secs:v1',
  defaultIntervalSecs: 300,
})

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

function handleRunClick() {
  if (isRefreshing.value) {
    isRefreshing.value = false
  } else if (appState.value === 'loading') {
    stop()
  } else {
    run()
  }
}

// ── Lifecycle ─────────────────────────────────────────────────────────────────
onMounted(() => {
  initJiraBin()
  epicKey.value = window.myscriptAPI?.getPref(PREF_EPIC) ?? ''
  labelFilter.value = window.myscriptAPI?.getPref(PREF_FILTER) ?? ''
  restoreTab()
  restoreAutoRefresh()
})

function run() {
  const key = epicKey.value.trim()
  if (!jiraBin.value || !key) return
  window.myscriptAPI?.setPref(PREF_EPIC, key)
  window.myscriptAPI?.setPref(PREF_FILTER, labelFilter.value)
  coreRun(buildArgs())
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

/* ── Merged Run / Refresh button ─────────────────────────────────────────── */
.run-btn {
  display: flex;
  align-items: center;
  gap: 5px;
  background: var(--accent);
  color: #fff;
  border: none;
  padding: 4px 12px;
  border-radius: var(--radius) 0 0 var(--radius);
  font-size: 12px;
  font-weight: 600;
  cursor: pointer;
  white-space: nowrap;
  transition: opacity .12s;
}
.run-btn:disabled { opacity: .5; cursor: not-allowed; }
.run-btn.loading, .run-btn.refreshing { opacity: 0.85; }

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
.run-cd {
  font-size: 10px;
  opacity: 0.7;
  min-width: 22px;
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

/* ── ago hint ────────────────────────────────────────────────────────────── */
.ago-hint {
  font-size: 11px;
  color: var(--fg-dim, var(--fg));
  opacity: 0.55;
  white-space: nowrap;
  flex-shrink: 0;
}
.header-spacer { flex: 1; }

/* ── Interval dropdown (right half of button group) ─────────────────────── */
.ar-group {
  display: flex;
  align-items: center;
  flex-shrink: 0;
}
.ar-intv-wrap {
  position: relative;
}
.ar-intv-btn {
  display: flex;
  align-items: center;
  gap: 3px;
  font-size: 12px;
  padding: 3px 8px;
  border: 1px solid var(--border);
  border-radius: 0 var(--radius) var(--radius) 0;
  background: var(--bg);
  color: var(--fg);
  cursor: pointer;
  white-space: nowrap;
  transition: background .12s;
  height: 26px;
}
.ar-intv-btn:hover:not(:disabled) { background: var(--bg2); }
.ar-intv-btn:disabled { opacity: .45; cursor: not-allowed; }
.ar-intv-btn .chev { font-size: 10px; opacity: 0.6; }

/* Shared dropdown menu */
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
