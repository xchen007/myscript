<template>
  <form class="sync2pod-form" @submit.prevent="submit">

    <div class="form-group">
      <label>Operation</label>
      <select v-model="operation">
        <option value="sync">Sync project</option>
        <option value="list">List projects</option>
        <option value="init">Init new project config</option>
      </select>
    </div>

    <!-- Sync project -->
    <template v-if="operation === 'sync'">
      <div class="form-group">
        <label>Project</label>
        <div style="display:flex;gap:6px">
          <select v-model="project" style="flex:1">
            <option v-for="p in projects" :key="p" :value="p">{{ p }}</option>
          </select>
          <button type="button" class="btn btn-ghost btn-sm" @click="refreshProjects">↻</button>
        </div>
        <div v-if="configHint" class="hint">{{ configHint }}</div>
      </div>
      <div class="form-group">
        <label class="checkbox-label"><input type="checkbox" v-model="force" /> --force</label>
        <label class="checkbox-label"><input type="checkbox" v-model="skipVerify" /> --skip-verify</label>
        <label class="checkbox-label"><input type="checkbox" v-model="dryRun" /> --dry-run</label>
      </div>
    </template>

    <!-- Init new project -->
    <template v-if="operation === 'init'">
      <div class="form-group">
        <label>Project name</label>
        <input v-model="newProject" placeholder="my-project" required />
      </div>
      <div class="form-group">
        <label>Local path</label>
        <input v-model="newLocalPath" placeholder="/path/to/local/dir" required />
      </div>
    </template>

    <div class="form-actions">
      <button type="submit" class="btn btn-primary">▶ Run</button>
      <button type="button" class="btn btn-ghost" @click="$emit('cancel')">Cancel</button>
    </div>
  </form>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

const emit = defineEmits(['submit', 'cancel'])

const operation   = ref('sync')
const project     = ref('')
const projects    = ref([])
const force       = ref(false)
const skipVerify  = ref(true)
const dryRun      = ref(false)
const newProject  = ref('')
const newLocalPath = ref('')

const configHint = computed(() => {
  if (!project.value) return ''
  const home = window.myscriptAPI?.getHomeDir() ?? '~'
  return `${home}/.sync2pod/${project.value}/sync_config.json`
})

function refreshProjects() {
  projects.value = window.myscriptAPI?.listSync2podProjects() ?? []
  if (!project.value && projects.value.length) project.value = projects.value[0]
}

onMounted(refreshProjects)

function submit() {
  let args, label

  if (operation.value === 'list') {
    args = ['--list-projects']
    label = 'list-projects'
  } else if (operation.value === 'init') {
    if (!newProject.value || !newLocalPath.value) return
    args = ['--init-config', '--project', newProject.value, '--local-path', newLocalPath.value]
    label = `init: ${newProject.value}`
  } else {
    if (!project.value) return
    args = ['--project', project.value]
    if (force.value)      args.push('--force')
    if (skipVerify.value) args.push('--skip-verify')
    if (dryRun.value)     args.push('--dry-run')
    label = `sync: ${project.value}`
  }

  emit('submit', { label, args })
}
</script>

<style scoped>
.sync2pod-form {
  display: flex;
  flex-direction: column;
  gap: 12px;
  padding: 12px;
  overflow-y: auto;
  flex: 1;
}

.form-group { display: flex; flex-direction: column; gap: 4px; }

.hint { font-size: 10px; color: var(--text2); font-family: var(--mono); }

.form-actions { display: flex; gap: 8px; padding-top: 4px; }

.btn-sm { padding: 3px 8px; font-size: 11px; }
</style>
