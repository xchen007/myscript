<template>
  <div
    class="op-list"
    :style="{ width: collapsed ? '40px' : width + 'px' }"
  >
    <div
      v-for="op in operations"
      :key="op.id"
      class="op-item"
      :class="{ active: op.id === activeId, collapsed }"
      :title="collapsed ? op.name : undefined"
      @click="$emit('select', op.id)"
    >
      <span class="op-icon">{{ op.icon }}</span>
      <span v-if="!collapsed" class="op-name">{{ op.name }}</span>
    </div>

    <div class="spacer" />

    <button
      class="collapse-btn"
      :title="collapsed ? 'Expand sidebar' : 'Collapse sidebar'"
      @click="$emit('toggle-collapse')"
    >{{ collapsed ? '›' : '‹' }}</button>
  </div>
</template>

<script setup>
defineProps({
  activeId:  { type: String,  default: null },
  width:     { type: Number,  default: 140 },
  collapsed: { type: Boolean, default: false },
})
defineEmits(['select', 'toggle-collapse'])

const operations = [
  { id: 'sprint-report', icon: '📊', name: 'Sprint Report' },
  { id: 'epic-query',    icon: '🏷️', name: 'Epic Query' },
]
</script>

<style scoped>
.op-list {
  flex-shrink: 0;
  background: var(--bg2);
  border-right: 1px solid var(--border);
  padding: 8px 4px 6px;
  display: flex;
  flex-direction: column;
  gap: 2px;
  overflow: hidden;
  transition: width 0.18s ease;
  min-width: 0;
}

.op-item {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 7px 8px;
  border-radius: var(--radius);
  cursor: pointer;
  color: var(--text2);
  font-size: 12px;
  font-weight: 500;
  white-space: nowrap;
  transition: background 0.12s;
}
.op-item.collapsed {
  justify-content: center;
  padding: 7px 4px;
}
.op-item:hover { background: var(--bg3); color: var(--text); }
.op-item.active { background: var(--accent); color: #fff; }
.op-icon { font-size: 14px; flex-shrink: 0; }
.op-name { overflow: hidden; text-overflow: ellipsis; }

.spacer { flex: 1; }

.collapse-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 100%;
  height: 24px;
  background: none;
  border: none;
  color: var(--text3);
  font-size: 14px;
  cursor: pointer;
  border-radius: var(--radius);
  transition: background 0.12s, color 0.12s;
  flex-shrink: 0;
}
.collapse-btn:hover { background: var(--bg3); color: var(--text); }
</style>
