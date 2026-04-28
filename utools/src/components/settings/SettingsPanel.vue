<template>
  <Teleport to="body">
    <div v-if="visible" class="modal-mask" @click.self="$emit('close')">
      <div class="modal-box">
        <!-- Header -->
        <div class="modal-header">
          <span class="modal-title">⚙️ Settings</span>
          <button class="close-btn" @click="$emit('close')">✕</button>
        </div>

        <div class="modal-body">
          <!-- Left tabs -->
          <div class="tab-sidebar">
            <button
              v-for="cat in categories"
              :key="cat.id"
              class="tab-item"
              :class="{ active: activeCategory === cat.id }"
              @click="activeCategory = cat.id"
            >{{ cat.label }}</button>
          </div>

          <!-- Right content -->
          <div class="tab-content">
            <!-- General -->
            <template v-if="activeCategory === 'general'">
              <div class="setting-row-kv">
                <span class="kv-label">Remember last tool</span>
                <label class="toggle-switch">
                  <input type="checkbox" v-model="rememberLastTool" @change="autoSave" />
                  <span class="toggle-slider" />
                </label>
              </div>
              <div class="setting-row-kv col">
                <div class="kv-label">Window Height</div>
                <div class="height-ctrl">
                  <input
                    type="range"
                    min="480"
                    max="1000"
                    step="10"
                    v-model.number="windowHeight"
                    @input="applyHeight"
                    class="height-slider"
                  />
                  <input
                    type="number"
                    min="480"
                    max="1000"
                    step="10"
                    v-model.number="windowHeight"
                    @change="applyHeight"
                    class="height-num"
                  />
                </div>
              </div>
            </template>

            <!-- Bisync -->
            <template v-if="activeCategory === 'bisync'">
              <div v-for="item in bisyncBins" :key="item.key" class="setting-row-kv col">
                <div class="kv-label">{{ item.label }}</div>
                <div class="kv-input-row">
                  <input v-model="form[item.key]" :placeholder="item.placeholder" @change="autoSave" />
                  <button class="btn btn-sm btn-ghost" :disabled="!form[item.key] || testingKey === item.key" @click="testBin(item)">
                    {{ testingKey === item.key ? '⏳' : '▶' }}
                  </button>
                </div>
                <div v-if="testResults[item.key]" class="test-result" :class="testResults[item.key].ok ? 'ok' : 'fail'">
                  {{ testResults[item.key].ok ? '✅ OK' : `❌ ${testResults[item.key].error || 'exit ' + testResults[item.key].code}` }}
                </div>
              </div>
            </template>

            <!-- Jira -->
            <template v-if="activeCategory === 'jira'">
              <div v-for="item in jiraBins" :key="item.key" class="setting-row-kv col">
                <div class="kv-label">{{ item.label }}</div>
                <div class="kv-input-row">
                  <input v-model="form[item.key]" :placeholder="item.placeholder" @change="autoSave" />
                  <button v-if="item.testable" class="btn btn-sm btn-ghost" :disabled="!form[item.key] || testingKey === item.key" @click="testBin(item)">
                    {{ testingKey === item.key ? '⏳' : '▶' }}
                  </button>
                </div>
                <div v-if="testResults[item.key]" class="test-result" :class="testResults[item.key].ok ? 'ok' : 'fail'">
                  {{ testResults[item.key].ok ? '✅ OK' : `❌ ${testResults[item.key].error || 'exit ' + testResults[item.key].code}` }}
                </div>
              </div>
              <hr class="divider" />
              <div v-for="item in jiraFields" :key="item.key" class="setting-row-kv col">
                <div class="kv-label">{{ item.label }}</div>
                <input v-model="form[item.key]" :placeholder="item.placeholder" @change="autoSave" />
              </div>
            </template>

            <!-- Sync2pod -->
            <template v-if="activeCategory === 'sync2pod'">
              <div v-for="item in sync2podBins" :key="item.key" class="setting-row-kv col">
                <div class="kv-label">{{ item.label }}</div>
                <div class="kv-input-row">
                  <input v-model="form[item.key]" :placeholder="item.placeholder" @change="autoSave" />
                  <button class="btn btn-sm btn-ghost" :disabled="!form[item.key] || testingKey === item.key" @click="testBin(item)">
                    {{ testingKey === item.key ? '⏳' : '▶' }}
                  </button>
                </div>
                <div v-if="testResults[item.key]" class="test-result" :class="testResults[item.key].ok ? 'ok' : 'fail'">
                  {{ testResults[item.key].ok ? '✅ OK' : `❌ ${testResults[item.key].error || 'exit ' + testResults[item.key].code}` }}
                </div>
              </div>
            </template>
          </div>
        </div>

        <!-- Footer -->
        <div class="modal-footer">
          <span class="save-hint">{{ saveHint }}</span>
          <span class="auto-save-hint">Changes auto-saved</span>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<script setup>
import { ref, reactive, watch, onMounted } from 'vue'

defineProps({ visible: Boolean })
defineEmits(['close'])

const WINDOW_HEIGHT_KEY = 'window_height'
const windowHeight = ref(700)

const categories = [
  { id: 'general',  label: 'General' },
  { id: 'bisync',   label: 'Bisync' },
  { id: 'jira',     label: 'Jira' },
  { id: 'sync2pod', label: 'Sync2pod' },
]

const activeCategory = ref('general')

const bisyncBins = [
  { key: 'unison_bin',  label: 'Unison',  placeholder: '/opt/homebrew/bin/unison', defaultTestCmd: '-version', testable: true },
  { key: 'fswatch_bin', label: 'fswatch', placeholder: '/opt/homebrew/bin/fswatch', defaultTestCmd: '--help', testable: true },
]

const jiraBins = [
  { key: 'jira_bin', label: 'Jira CLI (jira_cli)', placeholder: '/usr/local/bin/jira_cli', defaultTestCmd: '--help', testable: true },
]

const jiraFields = [
  { key: 'jira_user',  label: 'Jira User',        placeholder: 'xchen17' },
  { key: 'jira_label', label: 'Sprint Label',      placeholder: 'SDS-CP-Sprint08-2026' },
  { key: 'jira_url',   label: 'Jira Instance URL', placeholder: 'https://jirap.corp.ebay.com' },
]

const sync2podBins = [
  { key: 'tess_bin', label: 'Tess (kubectl wrapper)', placeholder: '/usr/local/bin/tess', defaultTestCmd: 'version', testable: true },
]

const allBins = [...bisyncBins, ...jiraBins, ...sync2podBins]
const allInputKeys = [...allBins, ...jiraFields].map(i => i.key)

const form        = reactive(Object.fromEntries(allInputKeys.map(k => [k, ''])))
const testingKey  = ref(null)
const testResults = reactive({})
const saveHint    = ref('')
const rememberLastTool = ref(false)

onMounted(() => {
  const settings = window.myscriptAPI?.loadSettings() ?? {}
  for (const key of allInputKeys) {
    if (settings[key]) form[key] = settings[key]
  }
  rememberLastTool.value = settings.remember_last_tool === 'true'

  const savedH = window.myscriptAPI?.getPref(WINDOW_HEIGHT_KEY)
  if (savedH) {
    windowHeight.value = savedH
    window.myscriptAPI?.setExpendHeight(savedH)
  }
})

for (const item of allBins) {
  watch(() => form[item.key], () => { delete testResults[item.key] })
}

function testBin(item) {
  const binPath = form[item.key]
  if (!binPath || !window.myscriptAPI) return
  const testArgs = (item.defaultTestCmd || '').trim().split(/\s+/)
  testingKey.value = item.key
  delete testResults[item.key]
  window.myscriptAPI.testBinary(binPath, testArgs, (result) => {
    testResults[item.key] = result
    testingKey.value = null
  })
}

function autoSave() {
  if (!window.myscriptAPI) return
  const payload = { ...form, remember_last_tool: rememberLastTool.value ? 'true' : '' }
  const result = window.myscriptAPI.saveSettings(payload)
  saveHint.value = result.ok ? '✅ Saved' : `❌ ${result.error}`
  setTimeout(() => { saveHint.value = '' }, 2000)
}

function applyHeight() {
  const h = Math.max(480, Math.min(1000, windowHeight.value))
  windowHeight.value = h
  window.myscriptAPI?.setExpendHeight(h)
  window.myscriptAPI?.setPref(WINDOW_HEIGHT_KEY, h)
}
</script>

<style scoped>
.modal-mask {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.35);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-box {
  width: min(580px, 90vw);
  max-height: 80vh;
  background: var(--bg);
  border-radius: 12px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.2);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.modal-header {
  display: flex;
  align-items: center;
  padding: 14px 18px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.modal-title {
  font-size: 15px;
  font-weight: 700;
  color: var(--fg);
  flex: 1;
}
.close-btn {
  background: none;
  border: none;
  font-size: 16px;
  color: var(--text2);
  cursor: pointer;
  padding: 2px 6px;
  border-radius: 4px;
}
.close-btn:hover { background: var(--bg3); color: var(--fg); }

.modal-body {
  display: flex;
  flex: 1;
  min-height: 0;
  overflow: hidden;
}

/* Left tabs */
.tab-sidebar {
  width: 120px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: 2px;
  padding: 12px 8px;
  border-right: 1px solid var(--border);
  background: var(--bg2);
}
.tab-item {
  text-align: left;
  padding: 8px 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg);
  color: var(--text2);
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.1s, color 0.1s;
}
.tab-item:hover { background: var(--bg3); color: var(--fg); }
.tab-item.active {
  background: var(--accent);
  color: #fff;
  border-color: var(--accent);
}

/* Right content */
.tab-content {
  flex: 1;
  padding: 14px 18px;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 10px;
}

.setting-row-kv {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 8px 14px;
  background: var(--bg2);
  border-radius: var(--radius);
  gap: 12px;
}
.setting-row-kv.col {
  flex-direction: column;
  align-items: stretch;
  gap: 6px;
}
.kv-label {
  font-size: 12px;
  color: var(--text2);
  font-weight: 500;
  flex-shrink: 0;
}
.kv-input-row {
  display: flex;
  gap: 6px;
  align-items: center;
}
.kv-input-row input { flex: 1; }

.test-result {
  font-size: 10px;
  font-weight: 500;
}
.test-result.ok   { color: var(--green); }
.test-result.fail { color: var(--red); }

.btn-sm { padding: 4px 8px; font-size: 11px; white-space: nowrap; }

/* Toggle switch */
.toggle-switch {
  position: relative;
  display: inline-block;
  width: 36px;
  height: 20px;
  margin: 0;
  flex-shrink: 0;
}
.toggle-switch input { opacity: 0; width: 0; height: 0; }
.toggle-slider {
  position: absolute;
  inset: 0;
  background: var(--border);
  border-radius: 10px;
  cursor: pointer;
  transition: background 0.2s;
}
.toggle-slider::before {
  content: '';
  position: absolute;
  width: 16px;
  height: 16px;
  left: 2px;
  top: 2px;
  background: #fff;
  border-radius: 50%;
  transition: transform 0.2s;
}
.toggle-switch input:checked + .toggle-slider { background: var(--accent); }
.toggle-switch input:checked + .toggle-slider::before { transform: translateX(16px); }

.divider {
  border: none;
  border-top: 1px solid var(--border);
  margin: 4px 0;
}

.modal-footer {
  display: flex;
  align-items: center;
  padding: 8px 18px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
  gap: 8px;
}
.save-hint {
  font-size: 11px;
  color: var(--green);
}
.auto-save-hint {
  font-size: 10px;
  color: var(--text2);
  font-style: italic;
  margin-left: auto;
}

.height-ctrl {
  display: flex;
  align-items: center;
  gap: 10px;
}
.height-slider {
  flex: 1;
  border: none;
  padding: 0;
  accent-color: var(--accent);
  cursor: pointer;
}
.height-num {
  width: 60px;
  flex-shrink: 0;
  text-align: right;
}
</style>
