<template>
  <div class="wchart">
    <!-- Summary stats -->
    <div class="wc-stats">
      <div class="wcs">
        <span class="wcs-v">{{ fmtH(totalSeconds) }}</span>
        <span class="wcs-l">Total logged</span>
      </div>
      <div class="wcs">
        <span class="wcs-v">{{ workDays }}</span>
        <span class="wcs-l">Work days</span>
      </div>
      <div class="wcs">
        <span class="wcs-v">{{ fmtH(avgSeconds) }}</span>
        <span class="wcs-l">Daily avg</span>
      </div>
      <div class="wcs" :class="{ above: daysAboveTarget > 0 }">
        <span class="wcs-v">{{ daysAboveTarget }} / {{ workDays }}</span>
        <span class="wcs-l">Days ≥ {{ targetH }}h</span>
      </div>
    </div>

    <!-- Chart -->
    <div class="wc-wrap">
      <svg :viewBox="`0 0 ${W} ${H}`" class="wc-svg">
        <defs>
          <linearGradient id="wcg" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stop-color="var(--accent)" stop-opacity="0.30" />
            <stop offset="100%" stop-color="var(--accent)" stop-opacity="0.02" />
          </linearGradient>
        </defs>

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
          stroke="#f0883e" stroke-width="1.4" stroke-dasharray="6,4" opacity="0.9"
        />
        <text :x="ML + PW + 4" :y="targetY + 4" class="ax-lbl target-lbl">{{ targetH }}h</text>

        <!-- Area fill (below curve) -->
        <path v-if="areaD" :d="areaD" fill="url(#wcg)" />

        <!-- Actual line (smooth bezier) -->
        <path v-if="lineD" :d="lineD" fill="none" stroke="var(--accent)" stroke-width="2.2" stroke-linejoin="round" />

        <!-- Data points -->
        <circle
          v-for="p in pts" :key="p.date"
          :cx="p.x" :cy="p.y" r="4"
          class="dp"
          :class="{ over: p.hours >= targetH }"
          @mouseenter="hover = p" @mouseleave="hover = null"
        />

        <!-- Hover tooltip -->
        <g v-if="hover">
          <rect
            :x="tipX" :y="hover.y - 40"
            width="82" height="32" rx="5"
            fill="var(--bg3)" stroke="var(--border)" stroke-width="0.8"
          />
          <text :x="tipX + 41" :y="hover.y - 26" class="tt-date" text-anchor="middle">{{ hover.date }}</text>
          <text :x="tipX + 41" :y="hover.y - 12" class="tt-val" text-anchor="middle">{{ fmtH(hover.seconds) }}</text>
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
    <div class="wc-legend">
      <span class="leg-item">
        <svg width="22" height="10"><line x1="0" y1="5" x2="22" y2="5" stroke="var(--accent)" stroke-width="2.2" /></svg>
        Logged hours
      </span>
      <span class="leg-item">
        <svg width="22" height="10"><line x1="0" y1="5" x2="22" y2="5" stroke="#f0883e" stroke-width="1.5" stroke-dasharray="5,3" /></svg>
        {{ targetH }}h target
      </span>
    </div>

    <!-- Empty state -->
    <div v-if="!sorted.length" class="wc-empty">
      No worklog data available for this sprint.
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'

const props = defineProps({
  dailyLog: { type: Array, default: () => [] },  // [{ date, seconds }]
  targetH:  { type: Number, default: 8 },
})

// ── Chart geometry constants ───────────────────────────────────────────────────
const W = 600, H = 230
const ML = 44, MR = 38, MT = 18, MB = 46
const PW = W - ML - MR  // plot width
const PH = H - MT - MB  // plot height

const hover = ref(null)

// ── Data ──────────────────────────────────────────────────────────────────────
const sorted = computed(() =>
  [...props.dailyLog].sort((a, b) => a.date.localeCompare(b.date))
)

const totalSeconds      = computed(() => sorted.value.reduce((s, d) => s + d.seconds, 0))
const workDays          = computed(() => sorted.value.length)
const avgSeconds        = computed(() => workDays.value ? Math.round(totalSeconds.value / workDays.value) : 0)
const daysAboveTarget   = computed(() => sorted.value.filter(d => d.seconds >= props.targetH * 3600).length)

// ── Scale ─────────────────────────────────────────────────────────────────────
const maxH = computed(() => {
  if (!sorted.value.length) return 10
  const dataMax = Math.max(...sorted.value.map(d => d.seconds / 3600), props.targetH)
  return Math.ceil(dataMax / 2) * 2
})

function yScale(h) { return MT + PH - (h / maxH.value) * PH }
function xScale(i) {
  const n = sorted.value.length
  return n <= 1 ? ML + PW / 2 : ML + (i / (n - 1)) * PW
}

const targetY = computed(() => yScale(props.targetH))

const pts = computed(() => sorted.value.map((d, i) => ({
  ...d,
  x: xScale(i),
  y: yScale(d.seconds / 3600),
  hours: d.seconds / 3600,
})))

// ── Y-axis grid ───────────────────────────────────────────────────────────────
const yGrid = computed(() => {
  const max = maxH.value
  const step = max <= 10 ? 2 : max <= 20 ? 4 : 8
  const steps = []
  for (let h = 0; h <= max; h += step) steps.push({ h, y: yScale(h) })
  return steps
})

// ── X-axis labels (skip if too crowded) ──────────────────────────────────────
const xLabels = computed(() => {
  const pv = pts.value
  if (pv.length <= 12) return pv
  const stride = Math.ceil(pv.length / 12)
  return pv.filter((_, i) => i % stride === 0 || i === pv.length - 1)
})

// ── Smooth bezier path ────────────────────────────────────────────────────────
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

const lineD = computed(() => bezierPath(pts.value))

const areaD = computed(() => {
  const pv = pts.value
  if (!pv.length) return ''
  const bottom = MT + PH
  return bezierPath(pv) + ` L ${pv[pv.length - 1].x} ${bottom} L ${pv[0].x} ${bottom} Z`
})

// ── Tooltip position (keep within chart) ─────────────────────────────────────
const tipX = computed(() => {
  if (!hover.value) return 0
  return Math.min(Math.max(hover.value.x - 41, ML), ML + PW - 82)
})

// ── Formatting ────────────────────────────────────────────────────────────────
function fmtH(seconds) {
  const h = Math.floor(seconds / 3600)
  const m = Math.round((seconds % 3600) / 60)
  return m ? `${h}h ${m}m` : `${h}h`
}
</script>

<style scoped>
.wchart {
  display: flex;
  flex-direction: column;
  gap: 14px;
  padding: 16px 16px 8px;
  overflow-y: auto;
}

/* Stats row */
.wc-stats {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
}
.wcs {
  display: flex;
  flex-direction: column;
  gap: 2px;
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 10px 18px;
  min-width: 110px;
}
.wcs.above { border-color: var(--accent); }
.wcs-v { font-size: 20px; font-weight: 700; color: var(--fg); font-variant-numeric: tabular-nums; }
.wcs-l { font-size: 11px; color: var(--text3); text-transform: uppercase; letter-spacing: .05em; }

/* Chart container */
.wc-wrap {
  width: 100%;
  background: var(--bg2);
  border: 1px solid var(--border);
  border-radius: 8px;
  padding: 8px 4px 4px;
  box-sizing: border-box;
}
.wc-svg {
  display: block;
  width: 100%;
  height: auto;
}

/* SVG text */
.ax-lbl { font-size: 10px; fill: var(--text3); font-family: var(--mono, monospace); }
.target-lbl { fill: #f0883e; font-size: 10px; font-weight: 600; font-family: var(--mono, monospace); }

/* Data points */
.dp {
  fill: var(--bg2);
  stroke: var(--accent);
  stroke-width: 2;
  cursor: pointer;
  transition: r 0.1s;
}
.dp:hover { r: 6; }
.dp.over { fill: var(--accent); }

/* Tooltip text */
.tt-date { font-size: 10px; fill: var(--text3); font-family: var(--mono, monospace); }
.tt-val  { font-size: 11px; fill: var(--fg);    font-weight: 700; font-family: var(--mono, monospace); }

/* Legend */
.wc-legend {
  display: flex;
  gap: 20px;
  font-size: 11.5px;
  color: var(--text2);
  padding-left: 4px;
}
.leg-item {
  display: flex;
  align-items: center;
  gap: 6px;
}

/* Empty state */
.wc-empty {
  text-align: center;
  color: var(--text3);
  font-size: 13px;
  padding: 40px 0;
}
</style>
