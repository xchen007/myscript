<template>
  <nav class="tool-nav">
    <div class="nav-items">
      <button
        v-for="tool in tools"
        :key="tool.id"
        class="nav-btn"
        :class="{ active: activeTool === tool.id }"
        @click="$emit('select', tool.id)"
      >
        <span class="nav-icon">{{ tool.icon }}</span>
        <span class="nav-label">{{ tool.label }}</span>
      </button>
    </div>

    <button class="nav-btn theme-btn" @click="cycleTheme" :title="`Theme: ${mode}`">
      <span class="nav-icon">{{ themeIcon[mode] }}</span>
      <span class="nav-label">{{ mode }}</span>
    </button>
  </nav>
</template>

<script setup>
import { useTheme } from '../composables/useTheme.js'

defineProps({ activeTool: String })
defineEmits(['select'])

const tools = [
  { id: 'bisync',    icon: '🔄', label: 'Bisync' },
  { id: 'jiratools', icon: '📋', label: 'Jira' },
  { id: 'sync2pod',  icon: '☸️',  label: 'Sync2pod' },
]

const { mode, cycleTheme, themeIcon } = useTheme()
</script>

<style scoped>
.tool-nav {
  width: 76px;
  flex-shrink: 0;
  background: var(--bg2);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 8px 4px;
  gap: 2px;
}

.nav-items {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 7px 4px;
  border: none;
  background: transparent;
  border-radius: var(--radius);
  cursor: pointer;
  color: var(--text2);
  transition: background 0.12s, color 0.12s;
  width: 100%;
}

.nav-btn:hover { background: var(--bg3); color: var(--text); }
.nav-btn.active { background: var(--accent); color: #fff; }

.nav-icon { font-size: 16px; line-height: 1; }
.nav-label { font-size: 9px; font-weight: 500; }

.theme-btn { margin-top: auto; opacity: 0.7; }
.theme-btn:hover { opacity: 1; }
</style>
