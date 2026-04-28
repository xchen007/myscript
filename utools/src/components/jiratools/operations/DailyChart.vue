<template>
  <div class="dchart">
    <div class="dc-title">📈 Daily Worklog</div>
    <div class="dc-wrap">
      <svg :viewBox="`0 0 ${W} ${H}`" class="dc-svg">
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

        <!-- Target line -->
        <line
          :x1="ML" :y1="targetY" :x2="ML + PW" :y2="targetY"
          stroke="#f0883e" stroke-width="1" stroke-dasharray="4,3" opacity="0.9"
        />

        <!-- Per-label lines + area -->
        <template v-for="(s, idx) in labelSeries" :key="'ls'+s.label">
          <path v-if="s.areaD" :d="s.areaD" :fill="s.color" fill-opacity="0.08" />
          <path v-if="s.lineD" :d="s.lineD" fill="none" :stroke="s.color" stroke-width="1.5" stroke-linejoin="round" />
          <circle
            v-for="p in s.pts" :key="p.date"
            :cx="p.x" :cy="p.y" r="2.5"
            :fill="s.color" :stroke="s.color" stroke-width="1"
            class="dp"
            @mouseenter="hover = { ...p, label: s.label, color: s.color }"
            @mouseleave="hover = null"
          />
        </template>

        <!-- Total line (bold, on top) -->
        <path v-if="totalSeries.lineD" :d="totalSeries.lineD" fill="none" stroke="var(--fg)" stroke-width="2.2" stroke-linejoin="round" opacity="0.85" />
        <circle
          v-for="p in totalSeries.pts" :key="'t'+p.date"
          :cx="p.x" :cy="p.y" r="2.5"
          fill="var(--bg2)" stroke="var(--fg)" stroke-width="1.5"
          class="dp"
          @mouseenter="hover = { ...p, label: 'Total', color: 'var(--fg)' }"
          @mouseleave="hover = null"
        />

        <!-- Hover tooltip -->
        <g v-if="hover">
          <rect
            :x="tipX" :y="Math.max(hover.y - 36, 2)"
            width="90" height="28" rx="4"
            fill="var(--bg3)" stroke="var(--border)" stroke-width="0.6"
          />
          <text :x="tipX + 45" :y="Math.max(hover.y - 36, 2) + 11" class="tt-date" text-anchor="middle">
            {{ hover.date }} · {{ hover.label }}
          </text>
          <text :x="tipX + 45" :y="Math.max(hover.y - 36, 2) + 23" class="tt-val" text-anchor="middle">
            {{ fmtH(hover.seconds) }}
          </text>
        </g>

        <!-- X-axis labels (rotated) -->
        <text
          v-for="p in xLabels" :key="'xl'+p.date"
          :x="p.x" :y="H - 4"
          class="ax-lbl" text-anchor="end"
          :transform="`rotate(-45, ${p.x}, ${H - 4})`"
        >{{ p.date.slice(5) }}</text>
      </svg>
    </div>

    <!-- Legend -->
    <div class="dc-legend">
      <span v-for="s in labelSeries" :key="s.label" class="leg-item">
        <svg width="18" height="10"><line x1="0" y1="5" x2="18" y2="5" :stroke="s.color" stroke-width="2" /></svg>
        {{ shortLabel(s.label) }}
      </span>
      <span v-if="labels.length > 1" class="leg-item">
        <svg width="18" height="10"><line x1="0" y1="5" x2="18" y2="5" stroke="var(--fg)" stroke-width="2.8" /></svg>
        Total
      </span>
      <span class="leg-item">
        <svg width="18" height="10"><line x1="0" y1="5" x2="18" y2="5" stroke="#f0883e" stroke-width="1.5" stroke-dasharray="5,3" /></svg>
        {{ targetH }}h target
      </span>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const PALETTE = ['#58a6ff','#f0883e','#3fb950','#d2a8ff','#f778ba','#79c0ff','#ffd33d','#ff7b72']

const props = defineProps({
  dailyLog: { type: Array, default: () => [] },   // [{date, seconds, label}]
  labels:   { type: Array, default: () => [] },
  targetH:  { type: Number, default: 8 },
})

const W = 400, H = 200
const ML = 28, MR = 8, MT = 10, MB = 36
const PW = W - ML - MR
const PH = H - MT - MB

const hover = ref(null)

// All unique sorted dates (shared x-axis)
const dates = computed(() => {
  const s = new Set(props.dailyLog.map(e => e.date))
  return [...s].sort()
})

// Build per-label map: { label: { date: seconds } }
const labelMap = computed(() => {
  const m = {}
  for (const lbl of props.labels) m[lbl] = {}
  for (const e of props.dailyLog) {
    if (!m[e.label]) m[e.label] = {}
    m[e.label][e.date] = (m[e.label][e.date] || 0) + e.seconds
  }
  return m
})

// Total per date (deduped across labels — since backend already deduped, just sum)
const totalMap = computed(() => {
  const m = {}
  for (const d of dates.value) {
    let sum = 0
    for (const lbl of props.labels) sum += (labelMap.value[lbl]?.[d] || 0)
    m[d] = sum
  }
  return m
})

// Y-axis max
const maxH = computed(() => {
  if (!dates.value.length) return 10
  const allVals = dates.value.map(d => (totalMap.value[d] || 0) / 3600)
  const dataMax = Math.max(...allVals, props.targetH)
  return Math.ceil(dataMax / 2) * 2
})

function yScale(h) { return MT + PH - (h / maxH.value) * PH }
function xScale(i) {
  const n = dates.value.length
  return n <= 1 ? ML + PW / 2 : ML + (i / (n - 1)) * PW
}

const targetY = computed(() => yScale(props.targetH))

function buildPoints(valMap) {
  return dates.value.map((d, i) => ({
    date: d,
    seconds: valMap[d] || 0,
    x: xScale(i),
    y: yScale((valMap[d] || 0) / 3600),
    hours: (valMap[d] || 0) / 3600,
  }))
}

function bezierPath(points) {
  if (!points.length) return ''
  if (points.length === 1) return `M ${points[0].x} ${points[0].y}`
  let d = `M ${points[0].x} ${points[0].y}`
  for (let i = 1; i < points.length; i++) {
    const p0 = points[i - 1], p1 = points[i]
    const cpx = (p0.x + p1.x) / 2
    d += ` C ${cpx} ${p0.y} ${cpx} ${p1.y} ${p1.x} ${p1.y}`
  }
  return d
}

function buildSeries(pts) {
  const lineD = bezierPath(pts)
  const bottom = MT + PH
  const areaD = pts.length
    ? lineD + ` L ${pts[pts.length - 1].x} ${bottom} L ${pts[0].x} ${bottom} Z`
    : ''
  return { pts, lineD, areaD }
}

// Per-label series
const labelSeries = computed(() =>
  props.labels.map((lbl, idx) => {
    const pts = buildPoints(labelMap.value[lbl] || {})
    const { lineD, areaD } = buildSeries(pts)
    return { label: lbl, color: PALETTE[idx % PALETTE.length], pts, lineD, areaD }
  })
)

// Total series (only meaningful when multi-label, but always computed)
const totalSeries = computed(() => {
  const pts = buildPoints(totalMap.value)
  const { lineD } = buildSeries(pts)
  return { pts, lineD }
})

// Y-axis grid
const yGrid = computed(() => {
  const max = maxH.value
  const step = max <= 10 ? 2 : max <= 20 ? 4 : 8
  const steps = []
  for (let h = 0; h <= max; h += step) steps.push({ h, y: yScale(h) })
  return steps
})

// X-axis labels (skip if too crowded)
const xLabels = computed(() => {
  const allPts = dates.value.map((d, i) => ({ date: d, x: xScale(i) }))
  if (allPts.length <= 14) return allPts
  const stride = Math.ceil(allPts.length / 14)
  return allPts.filter((_, i) => i % stride === 0 || i === allPts.length - 1)
})

// Tooltip position (keep within chart)
const tipX = computed(() => {
  if (!hover.value) return 0
  return Math.min(Math.max(hover.value.x - 45, ML), ML + PW - 90)
})

function fmtH(seconds) {
  const h = Math.floor(seconds / 3600)
  const m = Math.round((seconds % 3600) / 60)
  return m ? `${h}h ${m}m` : `${h}h`
}

function shortLabel(label) {
  return label.length > 20 ? label.slice(0, 18) + '…' : label
}
</script>

<style scoped>
.dchart { display: flex; flex-direction: column; gap: 4px; }
.dc-title { font-size: 11px; font-weight: 600; color: var(--text2); text-transform: uppercase; letter-spacing: .04em; }

.dc-wrap {
  flex: 1;
  width: 100%;
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 2px 2px 0;
  box-sizing: border-box;
}
.dc-svg { display: block; width: 100%; height: 100%; }

.ax-lbl { font-size: 8px; fill: var(--text3); font-family: var(--mono, monospace); }
.target-lbl { fill: #f0883e; font-size: 8px; font-weight: 600; font-family: var(--mono, monospace); }

.dp { cursor: pointer; transition: r 0.1s; }
.dp:hover { r: 4; }

.tt-date { font-size: 7px; fill: var(--text3); font-family: var(--mono, monospace); }
.tt-val  { font-size: 9px; fill: var(--fg); font-weight: 700; font-family: var(--mono, monospace); }

.dc-legend { display: flex; gap: 10px; flex-wrap: wrap; font-size: 10px; color: var(--text2); padding-left: 2px; }
.leg-item { display: flex; align-items: center; gap: 4px; }
</style>
