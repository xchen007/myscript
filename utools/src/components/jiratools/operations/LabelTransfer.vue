<template>
  <div class="lt">
    <!-- Left: available -->
    <div class="lt-panel">
      <div class="lt-head">
        <span class="lt-title">Available</span>
        <span class="lt-count">{{ available.length }}</span>
      </div>
      <div class="lt-list">
        <div
          v-for="lbl in available"
          :key="lbl"
          class="lt-item"
          @click="addLabel(lbl)"
        >{{ lbl }}</div>
        <div v-if="!available.length" class="lt-empty">No history yet — type below</div>
      </div>
      <div class="lt-add">
        <input
          v-model="newLabel"
          placeholder="Type label, Enter to add"
          class="lt-input"
          @keydown.enter.prevent="addCustom"
        />
      </div>
    </div>

    <!-- Right: selected -->
    <div class="lt-panel lt-selected">
      <div class="lt-head">
        <span class="lt-title">Selected</span>
        <span class="lt-count">{{ selected.length }}</span>
        <button v-if="selected.length" class="lt-clear" @click="clearAll" title="Clear all">✕</button>
      </div>
      <div class="lt-list">
        <div
          v-for="lbl in selected"
          :key="lbl"
          class="lt-item lt-item-sel"
          @click="removeLabel(lbl)"
        >
          <span class="lt-item-text">{{ lbl }}</span>
          <span class="lt-rm">✕</span>
        </div>
        <div v-if="!selected.length" class="lt-empty">Click items on the left to select</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] },
  historyKey: { type: String, default: 'sprint-label' },
})
const emit = defineEmits(['update:modelValue'])

const STORAGE_KEY = `input-history:${props.historyKey}`
const selected = computed(() => props.modelValue)
const historyLabels = ref([])
const newLabel = ref('')

const available = computed(() =>
  historyLabels.value.filter(l => !selected.value.includes(l))
)

onMounted(() => {
  historyLabels.value = window.myscriptAPI?.getPref(STORAGE_KEY) ?? []
})

function addLabel(lbl) {
  if (!selected.value.includes(lbl)) {
    emit('update:modelValue', [...selected.value, lbl])
  }
}

function removeLabel(lbl) {
  emit('update:modelValue', selected.value.filter(l => l !== lbl))
}

function clearAll() {
  emit('update:modelValue', [])
}

function addCustom() {
  const lbl = newLabel.value.trim()
  if (!lbl) return
  if (!historyLabels.value.includes(lbl)) {
    historyLabels.value = [lbl, ...historyLabels.value].slice(0, 20)
    window.myscriptAPI?.setPref(STORAGE_KEY, historyLabels.value)
  }
  addLabel(lbl)
  newLabel.value = ''
}

function refreshHistory() {
  historyLabels.value = window.myscriptAPI?.getPref(STORAGE_KEY) ?? []
}
defineExpose({ refreshHistory })
</script>

<style scoped>
.lt {
  display: flex;
  gap: 0;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
  height: 160px;
}
.lt-panel {
  flex: 1;
  display: flex;
  flex-direction: column;
  min-width: 0;
}
.lt-panel + .lt-panel {
  border-left: 1px solid var(--border);
}
.lt-head {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 5px 8px;
  background: var(--bg2);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.lt-title { font-size: 10px; font-weight: 700; color: var(--text2); text-transform: uppercase; letter-spacing: .06em; }
.lt-count { font-size: 10px; color: var(--text3); background: var(--bg3); padding: 1px 5px; border-radius: 10px; }
.lt-clear { margin-left: auto; background: none; border: none; color: var(--text3); cursor: pointer; font-size: 11px; padding: 0 2px; }
.lt-clear:hover { color: var(--red); }
.lt-list {
  flex: 1;
  overflow-y: auto;
  padding: 4px 0;
  scrollbar-width: thin;
}
.lt-item {
  padding: 4px 10px;
  font-size: 11.5px;
  cursor: pointer;
  color: var(--text);
  display: flex;
  align-items: center;
  gap: 4px;
}
.lt-item-text { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.lt-item:hover { background: color-mix(in srgb, var(--accent) 12%, transparent); color: var(--accent); }
.lt-item-sel:hover { background: color-mix(in srgb, var(--red) 10%, transparent); color: var(--red); }
.lt-rm { font-size: 10px; opacity: 0.5; flex-shrink: 0; }
.lt-empty { padding: 10px; font-size: 11px; color: var(--text3); text-align: center; font-style: italic; }
.lt-add {
  padding: 4px 6px;
  border-top: 1px solid var(--border);
  flex-shrink: 0;
}
.lt-input {
  padding: 3px 6px;
  font-size: 11px;
  width: 100%;
  box-sizing: border-box;
}
</style>
