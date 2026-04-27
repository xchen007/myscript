<template>
  <div class="app-shell">
    <ToolNav :activeTool="activeTool" @select="onNavSelect" />

    <main class="app-main">
      <div v-if="!isReady" class="error-banner">
        ⚠️ Project root not found. Run <code>make install</code> inside the myscript directory.
      </div>

      <RouterView v-slot="{ Component }">
        <KeepAlive>
          <component :is="Component" />
        </KeepAlive>
      </RouterView>
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import ToolNav from './components/ToolNav.vue'

const router = useRouter()
const route  = useRoute()

const isReady = ref(window.myscriptAPI?.isReady() ?? false)

// Map route path → nav id, and vice versa
const ROUTE_TO_TOOL = {
  '/bisync':   'bisync',
  '/jira':     'jiratools',
  '/sync2pod': 'sync2pod',
  '/settings': 'settings',
}
const TOOL_TO_ROUTE = {
  bisync:    '/bisync',
  jiratools: '/jira',
  sync2pod:  '/sync2pod',
  settings:  '/settings',
}
const CODE_TO_ROUTE = {
  myscript:        '/bisync',
  bisync:          '/bisync',
  jiratools:       '/jira',
  'jira-analyzer': '/jira',
  sync2pod:        '/sync2pod',
}

const activeTool = computed(() => ROUTE_TO_TOOL[route.path] ?? 'bisync')

function onNavSelect(toolId) {
  router.push(TOOL_TO_ROUTE[toolId] ?? '/bisync')
}

function onUtoolsEnter(e) {
  const target = CODE_TO_ROUTE[e.detail?.code] ?? '/bisync'
  router.push(target)
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
