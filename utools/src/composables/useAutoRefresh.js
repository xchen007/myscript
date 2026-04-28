import { ref, onUnmounted } from 'vue'

const SENTINEL = '__SPRINT_TABLE_JSON__:'

/**
 * Shared composable for auto-refresh functionality.
 *
 * @param {Object} opts
 * @param {import('vue').Ref} opts.appState     - reactive appState from useJiraRun
 * @param {Function} opts.buildArgs             - returns args array for jira-analyzer
 * @param {Function} opts.applyData             - called with parsed JSON on success
 * @param {Function} opts.canRun                - returns boolean: inputs valid?
 * @param {Function} [opts.pushLog]             - optional log function
 * @param {string}   opts.prefKeyAR             - pref key for auto-refresh on/off
 * @param {string}   opts.prefKeyInterval       - pref key for interval value
 * @param {number}   [opts.defaultIntervalSecs] - default interval in seconds (300 = 5m)
 */
export function useAutoRefresh({
  appState, buildArgs, applyData, canRun,
  pushLog, prefKeyAR, prefKeyInterval,
  defaultIntervalSecs = 300,
}) {
  const autoRefresh         = ref(false)
  const refreshIntervalSecs = ref(defaultIntervalSecs)
  const isRefreshing        = ref(false)
  const nextRefreshIn       = ref(0)
  let refreshTimer   = null
  let countdownTimer = null

  function runBackground() {
    if (!canRun()) return
    if (isRefreshing.value || appState.value === 'loading') return
    isRefreshing.value = true
    const bgJobId = `bg-${crypto.randomUUID()}`

    try {
      window.myscriptAPI.runTool(
        bgJobId, 'jira-analyzer', buildArgs(),
        (line) => pushLog?.(`[auto] ${line}`),
        (code) => {
          if (code !== 0) isRefreshing.value = false
        },
        (line) => {
          if (line.startsWith(SENTINEL)) {
            try {
              applyData(JSON.parse(line.slice(SENTINEL.length)))
            } catch (e) {
              pushLog?.(`[auto error] ${e.message}`)
            }
            isRefreshing.value = false
          } else {
            pushLog?.(`[auto] ${line}`)
          }
        },
      )
    } catch (err) {
      pushLog?.(`[auto error] ${err.message}`)
      isRefreshing.value = false
    }
  }

  function startRefreshTimer() {
    stopRefreshTimer()
    if (!autoRefresh.value) return
    const secs = refreshIntervalSecs.value
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
    if (refreshTimer)   { clearInterval(refreshTimer);   refreshTimer = null }
    if (countdownTimer) { clearInterval(countdownTimer);  countdownTimer = null }
    nextRefreshIn.value = 0
  }

  function setAutoRefresh(enabled, intervalSecs) {
    if (!enabled) {
      autoRefresh.value = false
      window.myscriptAPI?.setPref(prefKeyAR, false)
      stopRefreshTimer()
    } else {
      if (intervalSecs != null) refreshIntervalSecs.value = intervalSecs
      window.myscriptAPI?.setPref(prefKeyInterval, refreshIntervalSecs.value)
      autoRefresh.value = true
      window.myscriptAPI?.setPref(prefKeyAR, true)
      startRefreshTimer()
    }
  }

  function restoreAutoRefresh() {
    const savedAR = window.myscriptAPI?.getPref(prefKeyAR)
    if (savedAR === true) autoRefresh.value = true
    const savedSecs = window.myscriptAPI?.getPref(prefKeyInterval)
    if (savedSecs) refreshIntervalSecs.value = Number(savedSecs) || defaultIntervalSecs
  }

  onUnmounted(stopRefreshTimer)

  return {
    autoRefresh, refreshIntervalSecs, isRefreshing, nextRefreshIn,
    startRefreshTimer, stopRefreshTimer, setAutoRefresh,
    restoreAutoRefresh, runBackground,
  }
}
