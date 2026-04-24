<template>
  <div class="app-shell">
    <ToolNav :activeTool="activeTool" @select="activeTool = $event" />

    <main class="app-main">
      <div v-if="!isReady" class="error-banner">
        ⚠️ Project root not found. Run <code>make install</code> inside the myscript directory.
      </div>

      <BisyncPanel    v-show="activeTool === 'bisync'" />
      <JiratoolsPanel v-show="activeTool === 'jiratools'" />
      <Sync2podPanel  v-show="activeTool === 'sync2pod'" />
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import ToolNav        from './components/ToolNav.vue'
import BisyncPanel    from './components/bisync/BisyncPanel.vue'
import JiratoolsPanel from './components/jiratools/JiratoolsPanel.vue'
import Sync2podPanel  from './components/sync2pod/Sync2podPanel.vue'

const activeTool = ref('bisync')
const isReady = ref(window.myscriptAPI?.isReady() ?? false)

const CODE_TO_TOOL = {
  myscript:        'bisync',
  bisync:          'bisync',
  jiratools:       'jiratools',
  'jira-analyzer': 'jiratools',
  sync2pod:        'sync2pod',
}

// preload.js already calls utools.onPluginEnter and dispatches the
// 'utoolsEnter' custom event — listen here instead of re-registering.
function onUtoolsEnter(e) {
  activeTool.value = CODE_TO_TOOL[e.detail?.code] ?? 'bisync'
  isReady.value = window.myscriptAPI?.isReady() ?? false
}

onMounted(() => {
  isReady.value = window.myscriptAPI?.isReady() ?? false
  window.addEventListener('utoolsEnter', onUtoolsEnter)
})

onUnmounted(() => {
  window.removeEventListener('utoolsEnter', onUtoolsEnter)
})
</script>

<style scoped>
.app-shell {
  width: 100vw;
  height: 100vh;
  display: flex;
  overflow: hidden;
}

.app-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--bg);
}

.error-banner {
  background: #fef2f2;
  color: #b91c1c;
  padding: 6px 12px;
  font-size: 12px;
  border-bottom: 1px solid #fecaca;
  flex-shrink: 0;
}

.error-banner code {
  font-family: var(--mono);
  background: #fee2e2;
  padding: 1px 4px;
  border-radius: 3px;
}
</style>
