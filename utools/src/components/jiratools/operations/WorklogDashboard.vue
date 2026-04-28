<template>
  <div class="wdash">
    <!-- Section header -->
    <div class="dash-header">
      <span class="dash-title">📈 ANALYTICS</span>
    </div>

    <!-- Stats bar -->
    <div v-if="hasDailyData" class="dash-stats">
      <div class="stat-group">
        <span class="stat-group-label">This week</span>
        <div class="stat-group-cards">
          <div class="stat-card">
            <span class="sv">{{ thisWeek.total ? fmtH(thisWeek.total) : '—' }}</span>
            <span class="sl">Total logged</span>
          </div>
          <div class="stat-card">
            <span class="sv">{{ thisWeek.avg ? fmtH(thisWeek.avg) : '—' }}</span>
            <span class="sl">Daily avg</span>
          </div>
        </div>
      </div>
      <div v-if="hasLastWeekData" class="stat-sep" />
      <div v-if="hasLastWeekData" class="stat-group stat-group-dim">
        <span class="stat-group-label">Last week</span>
        <div class="stat-group-cards">
          <div class="stat-card">
            <span class="sv">{{ fmtH(lastWeek.total) }}</span>
            <span class="sl">Total logged</span>
          </div>
          <div class="stat-card">
            <span class="sv">{{ fmtH(lastWeek.avg) }}</span>
            <span class="sl">Daily avg</span>
          </div>
        </div>
      </div>
    </div>

    <!-- Charts -->
    <div class="dash-charts">
      <DailyChart :dailyLog="dailyLog" :labels="labels" />
      <WeeklyChart :weeklyLog="weeklyLog" :labels="labels" />
    </div>
  </div>
</template>

<script setup>
import { computed } from 'vue'
import DailyChart from './DailyChart.vue'
import WeeklyChart from './WeeklyChart.vue'
import { fmtH } from '../../../composables/chartHelpers.js'

const props = defineProps({
  dailyLog:  { type: Array, default: () => [] },   // [{date, seconds, label}]
  weeklyLog: { type: Array, default: () => [] },   // [{week, seconds, label}]
  labels:    { type: Array, default: () => [] },
  appState:  { type: String, default: 'idle' },
})

const hasDailyData = computed(() => props.dailyLog.length > 0)

// ── Week boundary helpers ─────────────────────────────────────────────────
function getWeekBounds(offsetWeeks = 0) {
  const today = new Date()
  const dow = today.getDay() // 0=Sun, 1=Mon … 6=Sat
  const daysToMon = dow === 0 ? 6 : dow - 1
  const mon = new Date(today)
  mon.setDate(today.getDate() - daysToMon - offsetWeeks * 7)
  mon.setHours(0, 0, 0, 0)
  const fri = new Date(mon)
  fri.setDate(mon.getDate() + 4)
  fri.setHours(23, 59, 59, 999)
  return { mon, fri }
}

function parseLocalDate(str) {
  const [y, m, d] = str.split('-').map(Number)
  return new Date(y, m - 1, d)
}

function calcWeekStats(dailyLog, mon, fri) {
  const dayTotals = {}
  for (const e of dailyLog) {
    const dt = parseLocalDate(e.date)
    const dow = dt.getDay()
    if (dow < 1 || dow > 5) continue       // skip weekends
    if (dt < mon || dt > fri) continue     // skip outside window
    dayTotals[e.date] = (dayTotals[e.date] || 0) + e.seconds
  }
  const days = Object.keys(dayTotals).length
  const total = Object.values(dayTotals).reduce((s, v) => s + v, 0)
  return { total, days, avg: days ? Math.round(total / days) : 0 }
}

const thisWeek = computed(() => {
  const { mon, fri } = getWeekBounds(0)
  return calcWeekStats(props.dailyLog, mon, fri)
})

const lastWeek = computed(() => {
  const { mon, fri } = getWeekBounds(1)
  return calcWeekStats(props.dailyLog, mon, fri)
})

const hasLastWeekData = computed(() => lastWeek.value.total > 0)
</script>

<style scoped>
.wdash {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 0 0 6px;
  background: var(--bg2);
  border-bottom: 2px solid var(--border);
  flex-shrink: 0;
  max-height: min(42vh, 340px);
  overflow: hidden;
}

/* Section header */
.dash-header {
  display: flex;
  align-items: center;
  padding: 5px 12px 4px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.dash-title {
  font-size: 10px;
  font-weight: 700;
  letter-spacing: .08em;
  color: var(--text3);
}

/* Stats */
.dash-stats {
  display: flex;
  align-items: center;
  gap: 8px;
  flex-wrap: wrap;
  padding: 0 12px;
  flex-shrink: 0;
}
.stat-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.stat-group-label {
  font-size: 9px;
  font-weight: 700;
  letter-spacing: .07em;
  text-transform: uppercase;
  color: var(--accent);
}
.stat-group-dim .stat-group-label { color: var(--text3); }
.stat-group-dim .sv { color: var(--text2); }
.stat-group-cards {
  display: flex;
  gap: 6px;
}
.stat-sep {
  width: 1px;
  height: 36px;
  background: var(--border);
  flex-shrink: 0;
}
.stat-card {
  display: flex;
  flex-direction: column;
  gap: 1px;
  background: var(--bg);
  border: 1px solid var(--border);
  border-radius: 6px;
  padding: 4px 12px;
  min-width: 70px;
}
.sv { font-size: 14px; font-weight: 700; color: var(--fg); font-variant-numeric: tabular-nums; }
.sl { font-size: 9px; color: var(--text3); text-transform: uppercase; letter-spacing: .05em; }

/* Charts */
.dash-charts {
  display: flex;
  flex-direction: row;
  gap: 10px;
  flex: 0 1 min(22vh, 180px);
  min-height: 80px;
  padding: 0 12px;
  overflow: hidden;
  justify-content: flex-start;
}
.dash-charts > * { min-width: 0; }
</style>
