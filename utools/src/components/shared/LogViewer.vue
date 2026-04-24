<template>
  <div class="log-viewer" ref="el">
    <pre v-for="(line, i) in lines" :key="i" class="log-line" :class="lineClass(line)">{{ line }}</pre>
    <pre v-if="lines.length === 0" class="log-empty">No output yet.</pre>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'

const props = defineProps({ lines: { type: Array, required: true } })
const el = ref(null)

// Auto-scroll to bottom whenever new lines arrive
watch(() => props.lines.length, () => {
  nextTick(() => {
    if (!el.value) return
    const { scrollTop, scrollHeight, clientHeight } = el.value
    const isAtBottom = scrollTop + clientHeight >= scrollHeight - 10
    if (isAtBottom) el.value.scrollTop = scrollHeight
  })
})

function lineClass(line) {
  if (line.startsWith('[error]') || line.startsWith('✕')) return 'err'
  if (line.startsWith('$'))  return 'cmd'
  if (line.startsWith('✓') || line.startsWith('[exited with code 0]')) return 'ok'
  return ''
}
</script>

<style scoped>
.log-viewer {
  flex: 1;
  overflow-y: auto;
  background: var(--bg2);
  border-radius: var(--radius);
  padding: 8px 10px;
  font-family: var(--mono);
  font-size: 11px;
  line-height: 1.55;
}

.log-line {
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}
.cmd  { color: var(--accent); }
.ok   { color: var(--green); }
.err  { color: var(--red); }
.log-empty { color: var(--text2); font-style: italic; }
</style>
