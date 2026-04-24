<template>
  <form class="bisync-form" @submit.prevent="submit">
    <div class="form-group">
      <label>Source directory</label>
      <input v-model="source" placeholder="/path/to/source" required />
    </div>

    <div class="form-group">
      <label>Target directory</label>
      <input v-model="target" placeholder="/path/to/target" required />
    </div>

    <div class="form-group">
      <label>Profile name (optional)</label>
      <input v-model="name" placeholder="my-sync" />
    </div>

    <div class="form-group">
      <label>Interval (seconds)</label>
      <input v-model.number="interval" type="number" min="1" value="5" />
    </div>

    <div class="form-group">
      <label class="checkbox-label"><input type="checkbox" v-model="reset" /> --reset (re-baseline)</label>
      <label class="checkbox-label"><input type="checkbox" v-model="dryRun" /> --dry-run</label>
      <label class="checkbox-label"><input type="checkbox" v-model="verbose" /> --verbose</label>
      <label class="checkbox-label"><input type="checkbox" v-model="nodeletion" /> --nodeletion-source</label>
    </div>

    <div class="form-actions">
      <button type="submit" class="btn btn-primary">▶ Run</button>
      <button type="button" class="btn btn-ghost" @click="$emit('cancel')">Cancel</button>
    </div>
  </form>
</template>

<script setup>
import { ref } from 'vue'

const emit = defineEmits(['submit', 'cancel'])

const source    = ref('')
const target    = ref('')
const name      = ref('')
const interval  = ref(5)
const reset     = ref(false)
const dryRun    = ref(false)
const verbose   = ref(false)
const nodeletion = ref(false)

function submit() {
  if (!source.value || !target.value) return

  const args = [source.value, target.value]
  if (name.value)     args.push('--name', name.value)
  args.push('--interval', String(interval.value))
  if (reset.value)     args.push('--reset')
  if (dryRun.value)    args.push('--dry-run')
  if (verbose.value)   args.push('--verbose')
  if (nodeletion.value) args.push('--nodeletion-source')

  const label = `${source.value.split('/').pop()} → ${target.value.split('/').pop()}`
  emit('submit', { label, args })
}
</script>

<style scoped>
.bisync-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
  overflow-y: auto;
  flex: 1;
}

.form-group {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.form-actions {
  display: flex;
  gap: 8px;
  padding-top: 4px;
}
</style>
