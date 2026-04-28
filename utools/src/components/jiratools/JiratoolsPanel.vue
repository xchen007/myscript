<template>
  <div class="panel">
    <OperationList :activeId="activeOp" @select="activeOp = $event" />

    <div class="panel-right">
      <SprintReport v-if="activeOp === 'sprint-report'" />
      <EpicQuery    v-if="activeOp === 'epic-query'" />
    </div>
  </div>
</template>

<script setup>
import { ref } from 'vue'
import OperationList from './OperationList.vue'
import SprintReport  from './operations/SprintReport.vue'
import EpicQuery     from './operations/EpicQuery.vue'

const activeOp = ref('sprint-report')
</script>

<style scoped>
.panel { display: flex; flex: 1; overflow: hidden; }
.panel-right { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
</style>
