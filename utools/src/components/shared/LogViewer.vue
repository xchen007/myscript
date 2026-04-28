<template>
  <div class="log-viewer" ref="el">
    <!-- Slim status bar -->
    <div class="term-bar">
      <span class="term-label">OUTPUT</span>
      <span class="term-sep">│</span>
      <span class="term-count">{{ lines.length }} lines</span>
      <span v-if="running" class="term-status running">⬤ RUNNING</span>
      <span v-else-if="lines.length > 0" class="term-status done">⬤ DONE</span>
    </div>

    <!-- Output body -->
    <div class="term-body">
      <div v-if="lines.length === 0" class="term-empty">
        <span class="prompt">❯</span>
        <span class="cursor">▋</span>
      </div>
      <div
        v-for="(line, i) in lines"
        :key="i"
        class="term-line"
        :class="lineClass(line)"
      ><span class="line-num">{{ i + 1 }}</span><span class="line-txt">{{ line }}</span></div>
      <div v-if="running" class="term-line term-caret">
        <span class="line-num"> </span><span class="prompt">❯</span><span class="cursor">▋</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, watch, nextTick } from 'vue'

const props = defineProps({
  lines:   { type: Array,   required: true },
  running: { type: Boolean, default: false },
})
const el = ref(null)

watch(() => props.lines.length, () => {
  nextTick(() => {
    if (!el.value) return
    const body = el.value.querySelector('.term-body')
    if (body) body.scrollTop = body.scrollHeight
  })
})

function lineClass(line) {
  if (line.startsWith('❌') || line.startsWith('[error]') || line.startsWith('✕')) return 'err'
  if (line.startsWith('⚠️') || line.startsWith('⚠'))  return 'warn'
  if (line.startsWith('$'))  return 'cmd'
  if (line.startsWith('✓') || line.startsWith('✅') || line.startsWith('[exited with code 0]')) return 'ok'
  if (line.startsWith('■') || line.startsWith('●') || line.startsWith('[')) return 'info'
  return ''
}
</script>

<style scoped>
.log-viewer {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
  background: #0d1117;
  border-top: 1px solid #21262d;
  font-family: var(--mono);
  font-size: 11.5px;
  line-height: 1.6;
}

/* ── Status bar ─────────────────────────────────────────────────────────────── */
.term-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 3px 14px;
  background: #161b22;
  border-bottom: 1px solid #21262d;
  flex-shrink: 0;
  user-select: none;
}
.term-label {
  font-size: 10px;
  font-weight: 700;
  color: #484f58;
  letter-spacing: .1em;
}
.term-sep { color: #21262d; }
.term-count { font-size: 10px; color: #484f58; }
.term-status {
  margin-left: auto;
  font-size: 10px;
  font-weight: 600;
  letter-spacing: .06em;
}
.term-status.running { color: #3fb950; animation: blink 1.2s ease-in-out infinite; }
.term-status.done    { color: #484f58; }

/* ── Body ───────────────────────────────────────────────────────────────────── */
.term-body {
  flex: 1;
  overflow-y: auto;
  overflow-x: auto;
  min-width: 0;
  padding: 8px 0;
  scrollbar-width: thin;
  scrollbar-color: #21262d transparent;
}
.term-body::-webkit-scrollbar { width: 5px; height: 5px; }
.term-body::-webkit-scrollbar-thumb { background: #21262d; border-radius: 3px; }
.term-body::-webkit-scrollbar-corner { background: transparent; }

/* ── Lines ──────────────────────────────────────────────────────────────────── */
.term-line {
  display: flex;
  align-items: baseline;
  padding-right: 14px;
  min-height: 1.6em;
  min-width: max-content;
}
.term-line:hover { background: rgba(255,255,255,0.025); }

.line-num {
  display: inline-block;
  width: 38px;
  min-width: 38px;
  text-align: right;
  padding-right: 12px;
  color: #21262d;
  font-size: 10px;
  user-select: none;
  flex-shrink: 0;
  border-right: 1px solid #21262d;
  margin-right: 10px;
}
.line-txt { color: #8b949e; white-space: pre; }

/* Semantic colours */
.term-line.cmd  .line-txt { color: #79c0ff; }
.term-line.ok   .line-txt { color: #56d364; }
.term-line.err  .line-txt { color: #f85149; }
.term-line.warn .line-txt { color: #e3b341; }
.term-line.info .line-txt { color: #6e7681; }

.term-line.cmd { background: rgba(121,192,255,.03); }
.term-line.err { background: rgba(248,81,73,.06);   border-left: 2px solid #f85149; }
.term-line.ok  { background: rgba(86,211,100,.03);  }

/* ── Prompt / cursor ────────────────────────────────────────────────────────── */
.term-empty {
  padding: 4px 0 0 60px;
  color: #21262d;
  display: flex;
  gap: 4px;
  align-items: center;
}
.term-caret { gap: 4px; }
.prompt { color: #3fb950; font-weight: bold; }
.cursor { color: #3fb950; animation: blink 1s step-start infinite; }

@keyframes blink { 0%,100%{opacity:1} 50%{opacity:0} }
</style>
