<template>
  <div class="wchart">
    <div class="wc-title">📊 Weekly Worklog</div>
    <div class="wc-wrap">
      <svg :viewBox="`0 0 ${W} ${H}`" class="wc-svg">
        <!-- Horizontal grid lines -->
        <line
          v-for="g in yGrid" :key="'g'+g.h"
          :x1="ML" :y1="g.y" :x2="ML + PW" :y2="g.y"
          stroke="var(--border)" stroke-width="0.6"
        />
        <!-- Y-axis labels -->
        <text
          v-for="g in yGrid" :key="'yl'+g.h"
          :x="ML - 7" :y="g.y + 4"
          class="ax-lbl" text-anchor="end"
        >{{ g.h }}h</text>

        <!-- Grouped bars per week -->
        <template v-for="(wk, wi) in weeks" :key="wk">
          <!-- Per-label bars (side by side) -->
          <rect
            v-for="(lbl, li) in labels" :key="lbl"
            :x="barX(wi, li)"
            :y="barY(weekLabelMap[wk]?.[lbl] || 0)"
            :width="barW"
            :height="barH(weekLabelMap[wk]?.[lbl] || 0)"
            :fill="PALETTE[li % PALETTE.length]"
            fill-opacity="0.75"
            rx="2"
            class="bar"
            @mouseenter="hover = { week: wk, label: lbl, seconds: weekLabelMap[wk]?.[lbl] || 0, x: barX(wi, li) + barW / 2, y: barY(weekLabelMap[wk]?.[lbl] || 0), color: PALETTE[li % PALETTE.length] }"
            @mouseleave="hover = null"
          />
          <!-- Total line marker -->
          <line
            v-if="labels.length > 1"
            :x1="groupX(wi)" :y1="barY(weekTotal[wk] || 0)"
            :x2="groupX(wi) + groupW" :y2="barY(weekTotal[wk] || 0)"
            stroke="var(--fg)" stroke-width="2" stroke-dasharray="4,2" opacity="0.6"
          />
        </template>

        <!-- Hover tooltip -->
        <g v-if="hover">
          <rect
            :x="tipX" :y="Math.max(hover.y - 36, 2)"
            width="90" height="28" rx="4"
            fill="var(--bg3)" stroke="var(--border)" stroke-width="0.6"
          />
          <text :x="tipX + 45" :y="Math.max(hover.y - 36, 2) + 11" class="tt-date" text-anchor="middle">
            {{ fmtWeek(hover.week) }} · {{ shortLabel(hover.label) }}
          </text>
          <text :x="tipX + 45" :y="Math.max(hover.y - 36, 2) + 23" class="tt-val" text-anchor="middle">
            {{ fmtH(hover.seconds) }}
          </text>
        </g>

        <!-- X-axis labels -->
        <text
          v-for="(wk, wi) in weeks" :key="'xl'+wk"
          :x="groupX(wi) + groupW / 2" :y="H - 6"
          class="ax-lbl" text-anchor="middle"
        >{{ fmtWeek(wk) }}</text>
      </svg>
    </div>

    <!-- Legend -->
    <div class="wc-legend">
      <span v-for="(lbl, idx) in labels" :key="lbl" class="leg-item">
        <svg width="14" height="10"><rect x="0" y="1" width="14" height="8" rx="2" :fill="PALETTE[idx % PALETTE.length]" fill-opacity="0.75" /></svg>
        {{ shortLabel(lbl) }}
      </span>
      <span v-if="labels.length > 1" class="leg-item">
        <svg width="18" height="10"><line x1="0" y1="5" x2="18" y2="5" stroke="var(--fg)" stroke-width="2" stroke-dasharray="4,2" /></svg>
        Total
      </span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const PALETTE = ['#58a6ff','#f0883e','#3fb950','#d2a8ff','#f778ba','#79c0ff','#ffd33d','#ff7b72']

const props = defineProps({
  weeklyLog: { type: Array, default: () => [] },  // [{week, seconds, label}]
  labels:    { type: Array, default: () => [] },
})

const W = 340, H = 200
const ML = 28, MR = 8, MT = 10, MB = 20
const PW = W - ML - MR
const PH = H - MT - MB

const hover = ref(null)

// Unique sorted weeks
const weeks = computed(() => {
  const s = new Set(props.weeklyLog.map(e => e.week))
  return [...s].sort()
})

// {week: {label: seconds}}
const weekLabelMap = computed(() => {
  const m = {}
  for (const e of props.weeklyLog) {
    if (!m[e.week]) m[e.week] = {}
    m[e.week][e.label] = (m[e.week][e.label] || 0) + e.seconds
  }
  return m
})

// Total per week
const weekTotal = computed(() => {
  const m = {}
  for (const wk of weeks.value) {
    let sum = 0
    for (const lbl of props.labels) sum += (weekLabelMap.value[wk]?.[lbl] || 0)
    m[wk] = sum
  }
  return m
})

// Y-axis max
const maxH = computed(() => {
  if (!weeks.value.length) return 40
  const vals = weeks.value.map(wk => (weekTotal.value[wk] || 0) / 3600)
  return Math.ceil(Math.max(...vals, 8) / 4) * 4
})

function yScale(h) { return MT + PH - (h / maxH.value) * PH }
function barY(seconds) { return yScale(seconds / 3600) }
function barH(seconds) { return MT + PH - barY(seconds) }

// Bar layout: group width and individual bar width
const nLabels = computed(() => Math.max(props.labels.length, 1))
const groupW = computed(() => {
  const n = weeks.value.length
  if (!n) return PW
  return Math.min(PW / n * 0.7, 80)
})
const groupGap = computed(() => {
  const n = weeks.value.length
  if (n <= 1) return 0
  return (PW - groupW.value * n) / (n - 1)
})
const barW = computed(() => Math.max(groupW.value / nLabels.value - 2, 4))

function groupX(wi) {
  const n = weeks.value.length
  if (n <= 1) return ML + (PW - groupW.value) / 2
  return ML + wi * (groupW.value + groupGap.value)
}
function barX(wi, li) {
  const gx = groupX(wi)
  const offset = (groupW.value - barW.value * nLabels.value) / 2
  return gx + offset + li * barW.value
}

// Y-axis grid
const yGrid = computed(() => {
  const max = maxH.value
  const step = max <= 20 ? 4 : max <= 40 ? 8 : 16
  const steps = []
  for (let h = 0; h <= max; h += step) steps.push({ h, y: yScale(h) })
  return steps
})

// Tooltip position
const tipX = computed(() => {
  if (!hover.value) return 0
  return Math.min(Math.max(hover.value.x - 45, ML), ML + PW - 90)
})

function fmtH(seconds) {
  const h = Math.floor(seconds / 3600)
  const m = Math.round((seconds % 3600) / 60)
  return m ? `${h}h ${m}m` : `${h}h`
}

function fmtWeek(weekStart) {
  const d = new Date(weekStart + 'T00:00:00')
  const mon = d.toLocaleDateString('en', { month: 'short', day: 'numeric' })
  return mon
}

function shortLabel(label) {
  return label.length > 16 ? label.slice(0, 14) + '…' : label
}
</script>

<style scoped>
.wchart { display: flex; flex-direction: column; gap: 4px; min-height: 0; overflow: hidden; }
.wc-title { font-size: 11px; font-weight: 600; color: var(--text2); text-transform: uppercase; letter-spacing: .04em; flex-shrink: 0; }

.wc-wrap {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 2px 2px 0;
  box-sizing: border-box;
  aspect-ratio: 340 / 200;
}
.wc-svg { display: block; width: 100%; height: 100%; }

.ax-lbl { font-size: 8px; fill: var(--text3); font-family: var(--mono, monospace); }

.bar { cursor: pointer; transition: fill-opacity 0.15s; }
.bar:hover { fill-opacity: 1; }

.tt-date { font-size: 7px; fill: var(--text3); font-family: var(--mono, monospace); }
.tt-val  { font-size: 9px; fill: var(--fg); font-weight: 700; font-family: var(--mono, monospace); }

.wc-legend { display: flex; gap: 10px; flex-wrap: wrap; font-size: 10px; color: var(--text2); padding-left: 2px; flex-shrink: 0; }
.leg-item { display: flex; align-items: center; gap: 4px; }
</style>
