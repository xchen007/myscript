<template>
  <div class="panel">
    <OperationList
      :activeId="activeOp"
      :width="sidebarWidth"
      :collapsed="sidebarCollapsed"
      @select="activeOp = $event"
      @toggle-collapse="toggleCollapse"
    />

    <div
      v-show="!sidebarCollapsed"
      class="resize-handle"
      @mousedown.prevent="startResize"
    />

    <div class="panel-right">
      <SprintReport v-if="activeOp === 'sprint-report'" />
      <EpicQuery    v-if="activeOp === 'epic-query'" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import OperationList from './OperationList.vue'
import SprintReport  from './operations/SprintReport.vue'
import EpicQuery     from './operations/EpicQuery.vue'

const activeOp = ref('sprint-report')

const PREF_WIDTH     = 'jira-sidebar-width:v1'
const PREF_COLLAPSED = 'jira-sidebar-collapsed:v1'
const sidebarWidth     = ref(140)
const sidebarCollapsed = ref(false)

function loadPrefs() {
  const w = window.myscriptAPI?.getPref(PREF_WIDTH)
  if (typeof w === 'number' && w > 0) sidebarWidth.value = w
  const c = window.myscriptAPI?.getPref(PREF_COLLAPSED)
  if (c === true || c === false) sidebarCollapsed.value = c
}

function toggleCollapse() {
  sidebarCollapsed.value = !sidebarCollapsed.value
  window.myscriptAPI?.setPref(PREF_COLLAPSED, sidebarCollapsed.value)
}

// ── Drag resize ───────────────────────────────────────────────────────────
let resizing = false
let startX   = 0
let startW   = 0

function startResize(e) {
  resizing = true
  startX   = e.clientX
  startW   = sidebarWidth.value
  document.addEventListener('mousemove', onMouseMove)
  document.addEventListener('mouseup',   onMouseUp)
}

function onMouseMove(e) {
  if (!resizing) return
  sidebarWidth.value = Math.max(80, Math.min(280, startW + e.clientX - startX))
}

function onMouseUp() {
  resizing = false
  document.removeEventListener('mousemove', onMouseMove)
  document.removeEventListener('mouseup',   onMouseUp)
  window.myscriptAPI?.setPref(PREF_WIDTH, sidebarWidth.value)
}

onMounted(loadPrefs)
onUnmounted(() => {
  document.removeEventListener('mousemove', onMouseMove)
  document.removeEventListener('mouseup',   onMouseUp)
})
</script>

<style scoped>
.panel { display: flex; flex: 1; overflow: hidden; }
.panel-right { flex: 1; display: flex; flex-direction: column; overflow: hidden; }

.resize-handle {
  width: 4px;
  flex-shrink: 0;
  cursor: col-resize;
  background: transparent;
  position: relative;
  z-index: 2;
  transition: background 0.15s;
}
.resize-handle:hover,
.resize-handle:active { background: var(--accent); opacity: 0.5; }
</style>
