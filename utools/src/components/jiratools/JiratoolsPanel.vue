<template>
  <div class="panel">
    <OperationList :activeId="activeOp" @select="activeOp = $event" />

    <div class="panel-right">
      <div class="panel-header">{{ opLabel }}</div>
      <SprintReport v-if="activeOp === 'sprint-report'" />
      <!-- Future: <ModifyTicket v-if="activeOp === 'modify-ticket'" /> -->
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import OperationList from './OperationList.vue'
import SprintReport  from './operations/SprintReport.vue'

const activeOp = ref('sprint-report')

const OP_LABELS = {
  'sprint-report': '📊 Sprint Report',
}

const opLabel = computed(() => OP_LABELS[activeOp.value] ?? activeOp.value)
</script>

<style scoped>
.panel { display: flex; flex: 1; overflow: hidden; }
.panel-right { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.panel-header {
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--bg2);
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 600;
}
</style>
