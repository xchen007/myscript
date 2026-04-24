<template>
  <div class="op-list">
    <div
      v-for="op in operations"
      :key="op.id"
      class="op-item"
      :class="{ active: op.id === activeId }"
      @click="$emit('select', op.id)"
    >
      <span class="op-icon">{{ op.icon }}</span>
      <span class="op-name">{{ op.name }}</span>
    </div>
  </div>
</template>

<script setup>
defineProps({ activeId: { type: String, default: null } })
defineEmits(['select'])

const operations = [
  { id: 'sprint-report', icon: '📊', name: 'Sprint Report' },
  // Future operations added here
]
</script>

<style scoped>
.op-list {
  width: 140px;
  flex-shrink: 0;
  background: var(--bg2);
  border-right: 1px solid var(--border);
  padding: 8px 4px;
  display: flex;
  flex-direction: column;
  gap: 2px;
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
  transition: background 0.12s;
}
.op-item:hover { background: var(--bg3); color: var(--text); }
.op-item.active { background: var(--accent); color: #fff; }
.op-icon { font-size: 14px; }
</style>
