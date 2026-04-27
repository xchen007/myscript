<template>
  <div class="settings-panel">
    <h2 class="settings-title">⚙️ Settings</h2>
    <p class="settings-desc">All settings are stored in uTools database and sync across devices.</p>

    <!-- Command Paths -->
    <div class="settings-section">
      <div class="section-label">Command Paths</div>

      <div v-for="item in binaries" :key="item.key" class="setting-row">
        <label :for="item.key">{{ item.label }}</label>
        <input
          :id="item.key"
          v-model="form[item.key]"
          :placeholder="item.placeholder"
        />
        <div class="test-row">
          <span class="test-label">Test:</span>
          <input
            class="test-cmd-input"
            v-model="testCmds[item.key]"
            :placeholder="item.defaultTestCmd"
            @keyup.enter="testBin(item)"
          />
          <button
            type="button"
            class="btn btn-sm btn-ghost"
            :disabled="!form[item.key] || testingKey === item.key"
            @click="testBin(item)"
          >
            {{ testingKey === item.key ? '⏳' : '▶ Run' }}
          </button>
        </div>
        <div v-if="testResults[item.key]" class="test-output-wrap">
          <div class="test-status" :class="testResults[item.key].ok ? 'ok' : 'fail'">
            {{ testResults[item.key].error
              ? `❌ ${testResults[item.key].error}`
              : testResults[item.key].ok
                ? `✅ exit 0`
                : `❌ exit ${testResults[item.key].code}` }}
          </div>
          <pre v-if="testResults[item.key].output" class="test-output">{{ testResults[item.key].output }}</pre>
        </div>
      </div>
    </div>

    <!-- Jira Configuration -->
    <div class="settings-section">
      <div class="section-label">Jira Configuration</div>

      <div v-for="item in jiraFields" :key="item.key" class="setting-row">
        <label :for="item.key">{{ item.label }}</label>
        <input
          :id="item.key"
          v-model="form[item.key]"
          :placeholder="item.placeholder"
        />
      </div>
    </div>

    <div class="settings-footer">
      <span class="save-hint">{{ saveHint }}</span>
      <button class="btn btn-primary" @click="save" :disabled="saving">
        {{ saving ? '⏳ Saving…' : '💾 Save' }}
      </button>
    </div>
  </div>
</template>

<script setup>
import { ref, reactive, watch, onMounted } from 'vue'

const binaries = [
  { key: 'jira_bin',    label: 'Jira CLI (jira_cli)',    placeholder: '/usr/local/bin/jira_cli', defaultTestCmd: '--help' },
  { key: 'tess_bin',    label: 'Tess (kubectl wrapper)',  placeholder: '/usr/local/bin/tess',     defaultTestCmd: 'version' },
  { key: 'unison_bin',  label: 'Unison',                  placeholder: '/opt/homebrew/bin/unison', defaultTestCmd: '-version' },
  { key: 'fswatch_bin', label: 'fswatch',                 placeholder: '/opt/homebrew/bin/fswatch', defaultTestCmd: '--help' },
]

const jiraFields = [
  { key: 'jira_user',  label: 'Jira User',         placeholder: 'xchen17' },
  { key: 'jira_label', label: 'Sprint Label',       placeholder: 'SDS-CP-Sprint08-2026' },
  { key: 'jira_url',   label: 'Jira Instance URL',  placeholder: 'https://jirap.corp.ebay.com' },
]

const allKeys = [...binaries, ...jiraFields].map(i => i.key)

const form        = reactive(Object.fromEntries(allKeys.map(k => [k, ''])))
const testCmds    = reactive(Object.fromEntries(binaries.map(b => [b.key, b.defaultTestCmd])))
const testingKey  = ref(null)
const testResults = reactive({})
const saving      = ref(false)
const saveHint    = ref('')

onMounted(() => {
  const settings = window.myscriptAPI?.loadSettings() ?? {}
  for (const key of allKeys) {
    if (settings[key]) form[key] = settings[key]
  }
})

// Clear test result when binary path changes
for (const item of binaries) {
  watch(() => form[item.key], () => { delete testResults[item.key] })
}

function testBin(item) {
  const binPath = form[item.key]
  if (!binPath || !window.myscriptAPI) return
  const cmdStr = (testCmds[item.key] || '').trim()
  const testArgs = cmdStr ? cmdStr.split(/\s+/) : []
  testingKey.value = item.key
  delete testResults[item.key]
  window.myscriptAPI.testBinary(binPath, testArgs, (result) => {
    testResults[item.key] = result
    testingKey.value = null
  })
}

function save() {
  if (!window.myscriptAPI) return
  saving.value = true
  saveHint.value = ''
  const result = window.myscriptAPI.saveSettings({ ...form })
  saving.value = false
  if (result.ok) {
    saveHint.value = '✅ Settings saved to uTools database'
  } else {
    saveHint.value = `❌ Save failed: ${result.error}`
  }
  setTimeout(() => { saveHint.value = '' }, 5000)
}
</script>

<style scoped>
.settings-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  padding: 16px 20px;
  gap: 16px;
  overflow-y: auto;
}

.settings-title {
  font-size: 16px;
  font-weight: 600;
  color: var(--text);
}

.settings-desc {
  font-size: 12px;
  color: var(--text2);
  margin-top: -8px;
}

.settings-section {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.setting-row {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.test-row {
  display: flex;
  align-items: center;
  gap: 6px;
}
.test-label {
  font-size: 11px;
  color: var(--text2);
  flex-shrink: 0;
}
.test-cmd-input {
  flex: 1;
  font-family: var(--mono);
  font-size: 11px;
}
.btn-sm { padding: 4px 10px; font-size: 12px; white-space: nowrap; }

.test-output-wrap {
  display: flex;
  flex-direction: column;
  gap: 4px;
}
.test-status {
  font-size: 11px;
  font-weight: 500;
}
.test-status.ok   { color: var(--green); }
.test-status.fail { color: var(--red); }

.test-output {
  font-family: var(--mono);
  font-size: 10px;
  line-height: 1.4;
  background: var(--term-bg);
  color: var(--term-text);
  padding: 6px 8px;
  border-radius: var(--radius);
  max-height: 120px;
  overflow-y: auto;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}

.settings-footer {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-top: 8px;
}

.save-hint {
  font-size: 11px;
  color: var(--text2);
  flex: 1;
}
</style>
