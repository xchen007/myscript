import { ref, computed, onUnmounted } from 'vue'

const LOG_LIMIT = 500
const SENTINEL = '__SPRINT_TABLE_JSON__:'
const EMPTY_DATA = {
  tickets: [],
  stats: { total_tickets: 0, total_log_seconds: 0, total_points: 0, status_counts: {}, type_counts: {} },
  meta: {},
}

/**
 * Shared composable for Jira tool operations (run/stop/log/ago).
 *
 * @param {Object} opts
 * @param {string} opts.tabPrefKey  - pref key for persisting active tab
 * @param {Function} opts.onData    - optional extra handler called with parsed JSON on success
 */
export function useJiraRun({ tabPrefKey, onData } = {}) {
  const jiraBin       = ref('')
  const jobId         = ref(null)
  const appState      = ref('idle')   // 'idle' | 'loading' | 'done' | 'no-data' | 'error'
  const tableData     = ref(null)
  const lines         = ref([])
  const activeTab     = ref('tickets')
  const lastUpdatedAt = ref(0)
  const agoTick       = ref(0)
  let agoTimer = null

  // ── Relative time display ──────────────────────────────────────────────────
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

  // ── Log management ────────────────────────────────────────────────────────
  function pushLog(line) {
    if (lines.value.length < LOG_LIMIT) {
      lines.value.push(line)
    } else if (lines.value.length === LOG_LIMIT) {
      lines.value.push(`… (log truncated at ${LOG_LIMIT} lines)`)
    }
  }

  // ── Tab persistence ─────────────────────────────────────────────────────────
  function setTab(tab) {
    activeTab.value = tab
    if (tabPrefKey) window.myscriptAPI?.setPref(tabPrefKey, tab)
  }

  function restoreTab() {
    if (!tabPrefKey) return
    const saved = window.myscriptAPI?.getPref(tabPrefKey)
    if (saved === 'tickets' || saved === 'logs') activeTab.value = saved
  }

  // ── Core run / stop ───────────────────────────────────────────────────────
  /**
   * Run jira-analyzer with the given args. Parses sentinel JSON on stdout.
   * @param {string[]} args - CLI arguments
   * @param {Function} [beforeRun] - called before launch (for saving prefs etc.)
   */
  function run(args, beforeRun) {
    if (!window.myscriptAPI?.isReady()) {
      lines.value = ['[error] Project root not found. Run: make install inside the myscript directory.']
      appState.value = 'error'
      return
    }

    if (jobId.value && appState.value === 'loading') {
      window.myscriptAPI.stopTool(jobId.value)
    }

    beforeRun?.()

    lines.value    = []
    appState.value = 'loading'
    jobId.value    = crypto.randomUUID()

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
          if (line.startsWith(SENTINEL)) {
            try {
              const parsed = JSON.parse(line.slice(SENTINEL.length))
              tableData.value = parsed
              appState.value = (parsed.stats?.total_tickets ?? 0) > 0 ? 'done' : 'no-data'
              stampNow()
              onData?.(parsed)
              if (appState.value === 'done') activeTab.value = 'tickets'
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

  // ── Init & cleanup ──────────────────────────────────────────────────────────
  function initJiraBin() {
    jiraBin.value = window.myscriptAPI?.getSetting('jira_bin') ?? ''
  }

  function cleanupAgo() {
    if (agoTimer) { clearInterval(agoTimer); agoTimer = null }
  }

  onUnmounted(cleanupAgo)

  return {
    jiraBin, jobId, appState, tableData, lines, activeTab,
    lastUpdatedAt, agoText,
    pushLog, stampNow, setTab, restoreTab,
    run, stop, initJiraBin, cleanupAgo,
    EMPTY_DATA,
  }
}
