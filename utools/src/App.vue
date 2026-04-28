<template>
  <div class="app-shell">
    <ToolNav :activeTool="activeTool" @select="onNavSelect" @openSettings="showSettings = true" />

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

    <SettingsPanel :visible="showSettings" @close="showSettings = false" />
  </div>
</template>

<script setup>
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import ToolNav from './components/ToolNav.vue'
import SettingsPanel from './components/settings/SettingsPanel.vue'

const router = useRouter()
const route  = useRoute()

const isReady = ref(window.myscriptAPI?.isReady() ?? false)
const showSettings = ref(false)

// Map route path → nav id, and vice versa
const ROUTE_TO_TOOL = {
  '/bisync':   'bisync',
  '/jira':     'jiratools',
  '/sync2pod': 'sync2pod',
}
const TOOL_TO_ROUTE = {
  bisync:    '/bisync',
  jiratools: '/jira',
  sync2pod:  '/sync2pod',
}
const CODE_TO_ROUTE = {
  myscript:        '/bisync',
  bisync:          '/bisync',
  jiratools:       '/jira',
  'jira-analyzer': '/jira',
  sync2pod:        '/sync2pod',
}
const TOOL_IDS = new Set(['bisync', 'jiratools', 'sync2pod'])
const LAST_TOOL_KEY = 'last-active-tool:v1'

const activeTool = computed(() => ROUTE_TO_TOOL[route.path] ?? 'bisync')

function isRememberEnabled() {
  return window.myscriptAPI?.getSetting('remember_last_tool') === 'true'
}

function onNavSelect(toolId) {
  router.push(TOOL_TO_ROUTE[toolId] ?? '/bisync')
}

// Persist tool selection when navigating (only tool tabs, not settings)
watch(activeTool, (tool) => {
  if (isRememberEnabled() && TOOL_IDS.has(tool)) {
    window.myscriptAPI?.setPref(LAST_TOOL_KEY, tool)
  }
})

function onUtoolsEnter(e) {
  const code = e.detail?.code
  const explicitRoute = CODE_TO_ROUTE[code]

  if (explicitRoute) {
    router.push(explicitRoute)
  } else if (isRememberEnabled()) {
    const last = window.myscriptAPI?.getPref(LAST_TOOL_KEY)
    if (last && TOOL_TO_ROUTE[last]) {
      router.push(TOOL_TO_ROUTE[last])
    }
  }

  isReady.value = window.myscriptAPI?.isReady() ?? false
}

onMounted(() => {
  isReady.value = window.myscriptAPI?.isReady() ?? false
  window.addEventListener('utoolsEnter', onUtoolsEnter)

  // Restore last tool on initial mount
  if (isRememberEnabled()) {
    const last = window.myscriptAPI?.getPref(LAST_TOOL_KEY)
    if (last && TOOL_TO_ROUTE[last]) {
      router.replace(TOOL_TO_ROUTE[last])
    }
  }
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
