<template>
  <div class="wdash">
    <!-- Section header -->
    <div class="dash-header">
      <span class="dash-title">📈 ANALYTICS</span>
    </div>

    <!-- Stats bar -->
    <div v-if="hasDailyData" class="dash-stats">
      <div v-for="s in statCards" :key="s.label" class="stat-card" :class="{ accent: s.accent }">
        <span class="sv">{{ s.value }}</span>
        <span class="sl">{{ s.label }}</span>
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

const props = defineProps({
  dailyLog:  { type: Array, default: () => [] },   // [{date, seconds, label}]
  weeklyLog: { type: Array, default: () => [] },   // [{week, seconds, label}]
  labels:    { type: Array, default: () => [] },
  appState:  { type: String, default: 'idle' },
})

const hasDailyData = computed(() => props.dailyLog.length > 0)
const hasWeeklyData = computed(() => props.weeklyLog.length > 0)

// Aggregated stats
const totalSeconds = computed(() => props.dailyLog.reduce((s, d) => s + d.seconds, 0))
const workDays = computed(() => new Set(props.dailyLog.map(d => d.date)).size)
const avgSeconds = computed(() => workDays.value ? Math.round(totalSeconds.value / workDays.value) : 0)
const daysAboveTarget = computed(() => {
  const dayTotals = {}
  for (const e of props.dailyLog) dayTotals[e.date] = (dayTotals[e.date] || 0) + e.seconds
  return Object.values(dayTotals).filter(s => s >= 8 * 3600).length
})

const statCards = computed(() => [
  { value: fmtH(totalSeconds.value), label: 'Total logged' },
  { value: String(workDays.value), label: 'Work days' },
  { value: fmtH(avgSeconds.value), label: 'Daily avg' },
  { value: `${daysAboveTarget.value}/${workDays.value}`, label: 'Days ≥ 8h', accent: daysAboveTarget.value > 0 },
])

function fmtH(seconds) {
  const h = Math.floor(seconds / 3600)
  const m = Math.round((seconds % 3600) / 60)
  return m ? `${h}h ${m}m` : `${h}h`
}
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
  gap: 6px;
  flex-wrap: wrap;
  padding: 0 12px;
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
  min-width: 80px;
}
.stat-card.accent { border-color: var(--accent); }
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
  justify-content: center;
}
.dash-charts > * { min-width: 0; }
</style>
