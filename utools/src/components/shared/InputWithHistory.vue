<template>
  <div class="ihw" ref="wrap">
    <input
      class="ih-input"
      :value="modelValue"
      v-bind="$attrs"
      @input="$emit('update:modelValue', $event.target.value)"
      @focus="onFocus"
      @keydown.down.prevent="moveSelection(1)"
      @keydown.up.prevent="moveSelection(-1)"
      @keydown.enter="onEnter"
      @keydown.escape="showDrop = false"
    />
    <button
      v-if="history.length"
      type="button"
      class="ih-btn"
      tabindex="-1"
      @mousedown.prevent
      @click="toggleDrop"
    >▾</button>
    <div v-if="showDrop && history.length" class="ih-drop">
      <div
        v-for="(val, i) in history"
        :key="val"
        class="ih-item"
        :class="{ active: selectedIdx === i }"
        @mousedown.prevent
        @click="select(val)"
      >{{ val }}</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted, onBeforeUnmount } from 'vue'

defineOptions({ inheritAttrs: false })

const props = defineProps({
  modelValue: String,
  storageKey: { type: String, required: true },
  maxItems:   { type: Number, default: 10 },
})
const emit = defineEmits(['update:modelValue'])

const STORAGE_KEY = `input-history:${props.storageKey}`
const showDrop    = ref(false)
const selectedIdx = ref(-1)
const history     = ref([])
const wrap        = ref(null)

function loadHistory() {
  return window.myscriptAPI?.getPref(STORAGE_KEY) ?? []
}

function onFocus() {
  history.value = loadHistory()
  if (history.value.length) { showDrop.value = true; selectedIdx.value = -1 }
}

function toggleDrop() {
  history.value = loadHistory()
  showDrop.value = !showDrop.value
  selectedIdx.value = -1
}

function select(val) {
  emit('update:modelValue', val)
  showDrop.value = false
  selectedIdx.value = -1
}

function moveSelection(delta) {
  if (!showDrop.value) { showDrop.value = true; return }
  selectedIdx.value = Math.max(-1, Math.min(history.value.length - 1, selectedIdx.value + delta))
}

function onEnter(e) {
  if (showDrop.value && selectedIdx.value >= 0) {
    e.preventDefault()
    select(history.value[selectedIdx.value])
  } else {
    showDrop.value = false
  }
}

// Called by parent form on submit to persist the value
function push(value) {
  const v = value?.trim()
  if (!v || v.length < 2) return
  const hist = loadHistory().filter(x => x !== v)
  hist.unshift(v)
  hist.splice(props.maxItems)
  window.myscriptAPI?.setPref(STORAGE_KEY, hist)
  history.value = hist
}

function onDocClick(e) {
  if (wrap.value && !wrap.value.contains(e.target)) showDrop.value = false
}

onMounted(() => {
  history.value = loadHistory()
  document.addEventListener('click', onDocClick)
})
onBeforeUnmount(() => document.removeEventListener('click', onDocClick))

defineExpose({ push })
</script>

<style scoped>
.ihw {
  position: relative;
  display: flex;
  align-items: center;
}

.ih-input {
  flex: 1;
  min-width: 0;
  padding-right: 22px; /* room for ▾ button */
}

.ih-btn {
  position: absolute;
  right: 4px;
  background: none;
  border: none;
  color: var(--text2, #888);
  cursor: pointer;
  font-size: 11px;
  padding: 0 2px;
  line-height: 1;
}
.ih-btn:hover { color: var(--fg, #eee); }

.ih-drop {
  position: absolute;
  top: calc(100% + 2px);
  left: 0;
  right: 0;
  background: var(--bg2, #2a2a2a);
  border: 1px solid var(--border, #444);
  border-radius: 4px;
  max-height: 200px;
  overflow-y: auto;
  z-index: 999;
  box-shadow: 0 4px 12px rgba(0,0,0,.4);
}

.ih-item {
  padding: 5px 10px;
  font-size: 12px;
  cursor: pointer;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  color: var(--fg, #eee);
}
.ih-item:hover,
.ih-item.active {
  background: var(--accent, #4a90e2);
  color: #fff;
}
</style>
