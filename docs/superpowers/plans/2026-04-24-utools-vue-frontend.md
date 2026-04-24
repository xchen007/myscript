# uTools Vue Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the plain HTML/JS uTools frontend with a Vue 3 + Vite app that supports concurrent multi-instance jobs, a history list, an extensible Jiratools panel, and a light/dark/system theme.

**Architecture:** Vue 3 (Composition API) + Vite build inside `utools/`. `preload.js` is extended to key processes by caller-supplied UUID jobIds instead of toolIds, enabling concurrent jobs. The Python CLIs are untouched.

**Tech Stack:** Vue 3, Vite 5, `@vitejs/plugin-vue`, Node.js `crypto.randomUUID()`

---

## File Map

| File | Create/Modify | Responsibility |
|------|--------------|----------------|
| `utools/package.json` | Create | Vite project config, scripts |
| `utools/vite.config.js` | Create | Vite config: base `./`, output `dist/` |
| `utools/index.html` | Overwrite | Vite HTML entry (replaces old plain HTML) |
| `utools/src/main.js` | Create | Mount Vue app |
| `utools/src/App.vue` | Create | Root: layout, tool switcher, theme inject |
| `utools/src/style.css` | Create | CSS custom properties for all themes |
| `utools/src/composables/useTheme.js` | Create | Theme mode cycling + persistence |
| `utools/src/composables/useJobs.js` | Create | Multi-job state per tool |
| `utools/src/components/ToolNav.vue` | Create | Left sidebar nav + theme toggle |
| `utools/src/components/shared/StatusBadge.vue` | Create | running/done/stopped/error indicator |
| `utools/src/components/shared/LogViewer.vue` | Create | Auto-scrolling log display |
| `utools/src/components/shared/JobList.vue` | Create | Reusable job list (bisync & sync2pod) |
| `utools/src/components/bisync/BisyncForm.vue` | Create | New bisync job form |
| `utools/src/components/bisync/BisyncPanel.vue` | Create | Master-Detail container for bisync |
| `utools/src/components/sync2pod/Sync2podForm.vue` | Create | New sync2pod job form |
| `utools/src/components/sync2pod/Sync2podPanel.vue` | Create | Master-Detail container for sync2pod |
| `utools/src/components/jiratools/OperationList.vue` | Create | Static list of Jira operations |
| `utools/src/components/jiratools/operations/SprintReport.vue` | Create | Sprint report form + results |
| `utools/src/components/jiratools/JiratoolsPanel.vue` | Create | Operation list + detail layout |
| `utools/preload.js` | Modify | Change `toolId` → `jobId`, remove auto-kill on rerun |
| `utools/plugin.json` | Modify | `main`: `"dist/index.html"` |
| `utools/app.js` | Delete | Replaced by Vue components |
| `utools/style.css` | Delete | Replaced by `src/style.css` |
| `.gitignore` | Modify | Add `node_modules/` |
| `Makefile` | Modify | Add `utools-build`, `utools-dev` targets |

---

## Task 1: Project scaffold

**Files:**
- Create: `utools/package.json`
- Create: `utools/vite.config.js`
- Overwrite: `utools/index.html`
- Create: `utools/src/main.js`
- Create: `utools/src/App.vue` (skeleton only)
- Modify: `utools/plugin.json`
- Modify: `.gitignore`
- Modify: `Makefile`

- [ ] **Step 1.1: Create `utools/package.json`**

```json
{
  "name": "myscript-utools",
  "private": true,
  "version": "0.1.0",
  "type": "module",
  "scripts": {
    "dev": "vite",
    "build": "vite build"
  },
  "dependencies": {
    "vue": "^3.4.0"
  },
  "devDependencies": {
    "@vitejs/plugin-vue": "^5.0.0",
    "vite": "^5.0.0"
  }
}
```

- [ ] **Step 1.2: Create `utools/vite.config.js`**

```js
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
})
```

- [ ] **Step 1.3: Overwrite `utools/index.html`**

```html
<!DOCTYPE html>
<html lang="en">
  <head>
    <meta charset="UTF-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1.0" />
    <title>myscript</title>
  </head>
  <body>
    <div id="app"></div>
    <script type="module" src="/src/main.js"></script>
  </body>
</html>
```

- [ ] **Step 1.4: Create `utools/src/main.js`**

```js
import { createApp } from 'vue'
import App from './App.vue'
import './style.css'

createApp(App).mount('#app')
```

- [ ] **Step 1.5: Create skeleton `utools/src/App.vue`**

```vue
<template>
  <div class="app-shell">
    <p>Loading...</p>
  </div>
</template>

<script setup>
</script>

<style scoped>
.app-shell {
  width: 100vw;
  height: 100vh;
  display: flex;
}
</style>
```

- [ ] **Step 1.6: Update `utools/plugin.json` — change only the `main` field**

In `utools/plugin.json`, change the single line:
```
  "main": "index.html",
```
to:
```
  "main": "dist/index.html",
```
All other fields (pluginName, features, etc.) stay unchanged.

- [ ] **Step 1.7: Add `node_modules/` to `.gitignore`**

Append to `.gitignore`:
```
node_modules/
```

- [ ] **Step 1.8: Add Makefile targets**

Add after `utools-logo` target in `Makefile`:
```makefile
# Install uTools plugin Node dependencies
utools-install:
	cd utools && npm install

# Build uTools plugin (outputs to utools/dist/)
utools-build: utools-install
	cd utools && npm run build

# Start Vite dev server for uTools plugin
utools-dev:
	cd utools && npm run dev
```

Also update `.PHONY` line to add `utools-install utools-build utools-dev`.

- [ ] **Step 1.9: Install dependencies and verify build runs**

```bash
cd utools && npm install
npm run build
```

Expected: `dist/index.html` and `dist/assets/` created. No errors.

- [ ] **Step 1.10: Commit**

```bash
git add utools/package.json utools/vite.config.js utools/index.html \
        utools/src/main.js utools/src/App.vue utools/plugin.json \
        .gitignore Makefile
git commit -m "feat(utools): scaffold Vue 3 + Vite project"
```

---

## Task 2: Extend `preload.js` for multi-job

**Files:**
- Modify: `utools/preload.js`

The only change: `toolId` → `jobId`, and remove the `this.stopTool(toolId)` auto-kill at the top of `runTool`. Multiple jobs with the same CLI command can now run concurrently.

- [ ] **Step 2.1: Update the process registry comment**

Change line 101:
```js
// ── Process registry ──────────────────────────────────────────────────────────
// Keyed by jobId (UUID supplied by the caller). Supports concurrent jobs.
const procs = {}
```

- [ ] **Step 2.2: Update `runTool` signature and remove auto-kill**

Replace the `runTool` method (lines 124–192):
```js
  // Run a tool process.
  // jobId    — caller-supplied UUID; uniquely identifies this job instance
  // toolName — the CLI command name (e.g. 'bisync', 'jira-analyzer', 'sync2pod')
  // args     — array of CLI arguments
  // onData(line) — called with each stripped output line
  // onExit(code) — called on exit; code is -1 if killed by signal
  runTool(jobId, toolName, args, onData, onExit) {
    if (!isProjectRootValid()) {
      onData(`[error] Project root not found at: ${PROJECT_ROOT}`)
      onData('[error] Ensure utools/ is inside the myscript project and run: make install')
      onExit(1)
      return
    }

    const resolved = resolveToolBin(toolName)
    if (!resolved) {
      onData('[error] Could not find tool binary.')
      onData('[error] Run: make install  (creates .venv with all tools)')
      onData('[error] Or install uv: https://docs.astral.sh/uv/getting-started/installation/')
      onExit(1)
      return
    }

    const { program, prefixArgs } = resolved
    const fullArgs = [...prefixArgs, ...args]

    onData(`$ ${toolName} ${args.join(' ')}`)

    const proc = spawn(program, fullArgs, {
      cwd: PROJECT_ROOT,
      env: { ...process.env, PATH: LOGIN_SHELL_PATH },
      detached: true,
      stdio: ['pipe', 'pipe', 'pipe'],
    })

    procs[jobId] = proc

    proc.stdin.end()

    let buf = ''
    const handleChunk = (data) => {
      buf += stripAnsi(data.toString('utf8'))
      const parts = buf.split('\n')
      buf = parts.pop()
      for (const line of parts) {
        if (line !== '') onData(line)
      }
    }

    proc.stdout.on('data', handleChunk)
    proc.stderr.on('data', handleChunk)

    proc.on('close', (code, signal) => {
      if (buf.trim()) { onData(buf.trim()); buf = '' }
      delete procs[jobId]
      onExit(signal ? -1 : (code ?? 0))
    })

    proc.on('error', (err) => {
      delete procs[jobId]
      onData(`[error] ${err.message}`)
      onExit(1)
    })
  },
```

- [ ] **Step 2.3: Update `stopTool` parameter name**

Replace the `stopTool` method:
```js
  stopTool(jobId) {
    const proc = procs[jobId]
    if (!proc) return
    const pid = proc.pid
    delete procs[jobId]
    try {
      process.kill(-pid, 'SIGTERM')
    } catch { /* process may have already exited */ }
    setTimeout(() => {
      try { process.kill(-pid, 'SIGKILL') } catch { /* already gone */ }
    }, 3000)
  },
```

- [ ] **Step 2.4: Verify JS syntax**

```bash
node --check utools/preload.js
```

Expected: no output (clean).

- [ ] **Step 2.5: Commit**

```bash
git add utools/preload.js
git commit -m "feat(utools): extend preload.js for concurrent multi-job support"
```

---

## Task 3: Global CSS + theme system

**Files:**
- Create: `utools/src/style.css`
- Create: `utools/src/composables/useTheme.js`

- [ ] **Step 3.1: Create `utools/src/style.css`**

```css
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

/* ── Light theme (default) ─────────────────────────────────────────── */
:root {
  --bg:       #ffffff;
  --bg2:      #f9fafb;
  --bg3:      #f3f4f6;
  --border:   #e5e7eb;
  --text:     #111827;
  --text2:    #6b7280;
  --accent:   #2563eb;
  --accent-h: #1d4ed8;
  --green:    #16a34a;
  --red:      #dc2626;
  --yellow:   #d97706;
  --radius:   6px;
  --mono:     'Menlo', 'Monaco', 'Consolas', monospace;
}

/* ── Dark theme ────────────────────────────────────────────────────── */
[data-theme="dark"] {
  --bg:       #111827;
  --bg2:      #1f2937;
  --bg3:      #374151;
  --border:   #374151;
  --text:     #f9fafb;
  --text2:    #9ca3af;
  --accent:   #3b82f6;
  --accent-h: #2563eb;
  --green:    #4ade80;
  --red:      #f87171;
  --yellow:   #fbbf24;
}

/* ── System dark (no override) ─────────────────────────────────────── */
@media (prefers-color-scheme: dark) {
  :root:not([data-theme="light"]) {
    --bg:       #111827;
    --bg2:      #1f2937;
    --bg3:      #374151;
    --border:   #374151;
    --text:     #f9fafb;
    --text2:    #9ca3af;
    --accent:   #3b82f6;
    --accent-h: #2563eb;
    --green:    #4ade80;
    --red:      #f87171;
    --yellow:   #fbbf24;
  }
}

body {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  font-size: 13px;
  background: var(--bg);
  color: var(--text);
  height: 100vh;
  overflow: hidden;
}

/* ── Shared utilities ──────────────────────────────────────────────── */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  padding: 5px 12px;
  border-radius: var(--radius);
  border: none;
  cursor: pointer;
  font-size: 12px;
  font-weight: 500;
  transition: background 0.15s;
}

.btn-primary {
  background: var(--accent);
  color: #fff;
}
.btn-primary:hover:not(:disabled) { background: var(--accent-h); }
.btn-primary:disabled { opacity: 0.45; cursor: not-allowed; }

.btn-danger {
  background: var(--red);
  color: #fff;
}
.btn-danger:hover:not(:disabled) { filter: brightness(0.9); }

.btn-ghost {
  background: transparent;
  color: var(--text2);
  border: 1px solid var(--border);
}
.btn-ghost:hover:not(:disabled) { background: var(--bg3); color: var(--text); }

input, select, textarea {
  width: 100%;
  padding: 5px 8px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--bg);
  color: var(--text);
  font-size: 12px;
  outline: none;
}
input:focus, select:focus { border-color: var(--accent); }

label {
  font-size: 11px;
  color: var(--text2);
  font-weight: 500;
  display: block;
  margin-bottom: 3px;
}

.form-group { display: flex; flex-direction: column; gap: 10px; }

.checkbox-label {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  color: var(--text2);
  cursor: pointer;
}
.checkbox-label input[type="checkbox"] {
  width: auto;
  accent-color: var(--accent);
}

.divider {
  border: none;
  border-top: 1px solid var(--border);
  margin: 4px 0;
}

.section-label {
  font-size: 10px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.07em;
  color: var(--text2);
}
```

- [ ] **Step 3.2: Create `utools/src/composables/useTheme.js`**

```js
import { ref, watch } from 'vue'

const THEME_KEY = 'myscript-theme'
const MODES = ['system', 'light', 'dark']
const ICONS = { system: '💻', light: '☀️', dark: '🌙' }

function applyTheme(mode) {
  const el = document.documentElement
  if (mode === 'light') {
    el.setAttribute('data-theme', 'light')
  } else if (mode === 'dark') {
    el.setAttribute('data-theme', 'dark')
  } else {
    el.removeAttribute('data-theme')
  }
  localStorage.setItem(THEME_KEY, mode)
}

export function useTheme() {
  const mode = ref(localStorage.getItem(THEME_KEY) || 'system')

  watch(mode, applyTheme, { immediate: true })

  function cycleTheme() {
    const next = (MODES.indexOf(mode.value) + 1) % MODES.length
    mode.value = MODES[next]
  }

  return { mode, cycleTheme, themeIcon: ICONS }
}
```

- [ ] **Step 3.3: Commit**

```bash
git add utools/src/style.css utools/src/composables/useTheme.js
git commit -m "feat(utools): global CSS variables + theme composable"
```

---

## Task 4: App.vue + ToolNav

**Files:**
- Create: `utools/src/components/ToolNav.vue`
- Overwrite: `utools/src/App.vue`

- [ ] **Step 4.1: Create `utools/src/components/ToolNav.vue`**

```vue
<template>
  <nav class="tool-nav">
    <div class="nav-items">
      <button
        v-for="tool in tools"
        :key="tool.id"
        class="nav-btn"
        :class="{ active: activeTool === tool.id }"
        @click="$emit('select', tool.id)"
      >
        <span class="nav-icon">{{ tool.icon }}</span>
        <span class="nav-label">{{ tool.label }}</span>
      </button>
    </div>

    <button class="nav-btn theme-btn" @click="cycleTheme" :title="`Theme: ${mode}`">
      <span class="nav-icon">{{ themeIcon[mode] }}</span>
      <span class="nav-label">{{ mode }}</span>
    </button>
  </nav>
</template>

<script setup>
import { useTheme } from '../composables/useTheme.js'

defineProps({ activeTool: String })
defineEmits(['select'])

const tools = [
  { id: 'bisync',    icon: '🔄', label: 'Bisync' },
  { id: 'jiratools', icon: '📋', label: 'Jira' },
  { id: 'sync2pod',  icon: '☸️',  label: 'Sync2pod' },
]

const { mode, cycleTheme, themeIcon } = useTheme()
</script>

<style scoped>
.tool-nav {
  width: 76px;
  flex-shrink: 0;
  background: var(--bg2);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 8px 4px;
  gap: 2px;
}

.nav-items {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.nav-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  padding: 7px 4px;
  border: none;
  background: transparent;
  border-radius: var(--radius);
  cursor: pointer;
  color: var(--text2);
  transition: background 0.12s, color 0.12s;
  width: 100%;
}

.nav-btn:hover { background: var(--bg3); color: var(--text); }
.nav-btn.active { background: var(--accent); color: #fff; }

.nav-icon { font-size: 16px; line-height: 1; }
.nav-label { font-size: 9px; font-weight: 500; }

.theme-btn { margin-top: auto; opacity: 0.7; }
.theme-btn:hover { opacity: 1; }
</style>
```

- [ ] **Step 4.2: Overwrite `utools/src/App.vue`**

```vue
<template>
  <div class="app-shell">
    <ToolNav :activeTool="activeTool" @select="activeTool = $event" />

    <main class="app-main">
      <div v-if="!isReady" class="error-banner">
        ⚠️ Project root not found. Run <code>make install</code> inside the myscript directory.
      </div>

      <BisyncPanel    v-show="activeTool === 'bisync'" />
      <JiratoolsPanel v-show="activeTool === 'jiratools'" />
      <Sync2podPanel  v-show="activeTool === 'sync2pod'" />
    </main>
  </div>
</template>

<script setup>
import { ref, onMounted, onUnmounted } from 'vue'
import ToolNav        from './components/ToolNav.vue'
import BisyncPanel    from './components/bisync/BisyncPanel.vue'
import JiratoolsPanel from './components/jiratools/JiratoolsPanel.vue'
import Sync2podPanel  from './components/sync2pod/Sync2podPanel.vue'

const activeTool = ref('bisync')
const isReady = ref(true)

const CODE_TO_TOOL = {
  myscript:        'bisync',
  bisync:          'bisync',
  jiratools:       'jiratools',
  'jira-analyzer': 'jiratools',
  sync2pod:        'sync2pod',
}

// preload.js already calls utools.onPluginEnter and dispatches the
// 'utoolsEnter' custom event — listen here instead of re-registering.
function onUtoolsEnter(e) {
  activeTool.value = CODE_TO_TOOL[e.detail?.code] ?? 'bisync'
  isReady.value = window.myscriptAPI?.isReady() ?? false
}

onMounted(() => {
  isReady.value = window.myscriptAPI?.isReady() ?? false
  window.addEventListener('utoolsEnter', onUtoolsEnter)
})

onUnmounted(() => {
  window.removeEventListener('utoolsEnter', onUtoolsEnter)
})
</script>

<style scoped>
.app-shell {
  width: 100vw;
  height: 100vh;
  display: flex;
  overflow: hidden;
}

.app-main {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: var(--bg);
}

.error-banner {
  background: #fef2f2;
  color: #b91c1c;
  padding: 6px 12px;
  font-size: 12px;
  border-bottom: 1px solid #fecaca;
  flex-shrink: 0;
}

.error-banner code {
  font-family: var(--mono);
  background: #fee2e2;
  padding: 1px 4px;
  border-radius: 3px;
}
</style>
```

- [ ] **Step 4.3: Build and verify no errors**

```bash
cd utools && npm run build
```

Expected: builds cleanly. Ignore "missing component" warnings — panels will be created in later tasks. If there are import errors for BisyncPanel / JiratoolsPanel / Sync2podPanel, create empty placeholder `.vue` files (each just `<template><div /></template>`) to unblock the build.

- [ ] **Step 4.4: Commit**

```bash
git add utools/src/App.vue utools/src/components/ToolNav.vue
git commit -m "feat(utools): App shell + ToolNav with theme toggle"
```

---

## Task 5: Shared components

**Files:**
- Create: `utools/src/components/shared/StatusBadge.vue`
- Create: `utools/src/components/shared/LogViewer.vue`
- Create: `utools/src/components/shared/JobList.vue`

- [ ] **Step 5.1: Create `utools/src/components/shared/StatusBadge.vue`**

```vue
<template>
  <span class="badge" :class="status">{{ labels[status] }}</span>
</template>

<script setup>
defineProps({ status: { type: String, required: true } })

const labels = {
  running: '● Running',
  done:    '✓ Done',
  stopped: '⏹ Stopped',
  error:   '✕ Error',
}
</script>

<style scoped>
.badge {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 10px;
  white-space: nowrap;
}
.running { color: var(--accent); animation: pulse 1.4s ease-in-out infinite; }
.done    { color: var(--green); }
.stopped { color: var(--text2); }
.error   { color: var(--red); }

@keyframes pulse { 0%, 100% { opacity: 1 } 50% { opacity: 0.45 } }
</style>
```

- [ ] **Step 5.2: Create `utools/src/components/shared/LogViewer.vue`**

```vue
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
    if (el.value) el.value.scrollTop = el.value.scrollHeight
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
```

- [ ] **Step 5.3: Create `utools/src/components/shared/JobList.vue`**

```vue
<template>
  <div class="job-list">
    <button class="btn btn-primary new-job-btn" @click="$emit('new-job')">＋ New job</button>

    <div v-if="jobs.length === 0" class="empty">No jobs yet.</div>

    <div
      v-for="job in jobs"
      :key="job.id"
      class="job-card"
      :class="[job.status, { selected: job.id === selectedId }]"
      @click="$emit('select', job.id)"
    >
      <div class="job-top">
        <span class="job-label">{{ job.label }}</span>
        <StatusBadge :status="job.status" />
      </div>
      <div class="job-meta">
        {{ formatTime(job.startedAt) }}
        <span v-if="job.lines.length"> · {{ job.lines.length }} lines</span>
      </div>
    </div>
  </div>
</template>

<script setup>
import StatusBadge from './StatusBadge.vue'

defineProps({
  jobs:       { type: Array,  required: true },
  selectedId: { type: String, default: null  },
})
defineEmits(['select', 'new-job'])

function formatTime(date) {
  return date ? new Date(date).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' }) : ''
}
</script>

<style scoped>
.job-list {
  width: 180px;
  flex-shrink: 0;
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 4px;
  padding: 8px 6px;
  overflow-y: auto;
  background: var(--bg2);
}

.new-job-btn { width: 100%; justify-content: center; margin-bottom: 4px; }

.empty { font-size: 11px; color: var(--text2); text-align: center; padding: 20px 0; }

.job-card {
  padding: 7px 8px;
  border-radius: var(--radius);
  border: 1px solid var(--border);
  background: var(--bg);
  cursor: pointer;
  transition: border-color 0.12s;
  border-left-width: 3px;
}
.job-card:hover { border-color: var(--accent); }
.job-card.selected { background: var(--bg3); border-color: var(--accent); }
.job-card.running { border-left-color: var(--accent); }
.job-card.done    { border-left-color: var(--green); }
.job-card.stopped { border-left-color: var(--text2); }
.job-card.error   { border-left-color: var(--red); }

.job-top { display: flex; justify-content: space-between; align-items: flex-start; gap: 4px; }
.job-label { font-size: 11px; font-weight: 600; color: var(--text); flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.job-meta { font-size: 10px; color: var(--text2); margin-top: 2px; }
</style>
```

- [ ] **Step 5.4: Commit**

```bash
git add utools/src/components/shared/
git commit -m "feat(utools): shared StatusBadge, LogViewer, JobList components"
```

---

## Task 6: `useJobs` composable + BisyncPanel

**Files:**
- Create: `utools/src/composables/useJobs.js`
- Create: `utools/src/components/bisync/BisyncForm.vue`
- Create: `utools/src/components/bisync/BisyncPanel.vue`

- [ ] **Step 6.1: Create `utools/src/composables/useJobs.js`**

```js
import { reactive, ref } from 'vue'

/**
 * Manages a list of concurrent tool jobs.
 * @param {string} cmd - CLI command name (e.g. 'bisync')
 */
export function useJobs(cmd) {
  // reactive array so nested job property mutations (lines.push, status =) are tracked
  const jobs = reactive([])
  const selectedId = ref(null)

  function addJob(label, args) {
    const id = crypto.randomUUID()
    const job = reactive({
      id,
      label,
      args,
      status: 'running',
      lines: [],
      startedAt: new Date(),
      exitCode: null,
    })

    jobs.unshift(job)
    selectedId.value = id

    window.myscriptAPI.runTool(
      id,
      cmd,
      args,
      (line) => job.lines.push(line),
      (code) => {
        job.exitCode = code
        job.status = code === -1 ? 'stopped' : code === 0 ? 'done' : 'error'
      },
    )

    return job
  }

  function stopJob(id) {
    window.myscriptAPI.stopTool(id)
  }

  function removeJob(id) {
    const idx = jobs.findIndex(j => j.id === id)
    if (idx !== -1) {
      if (selectedId.value === id) {
        selectedId.value = jobs[idx + 1]?.id ?? jobs[idx - 1]?.id ?? null
      }
      jobs.splice(idx, 1)
    }
  }

  function selectJob(id) {
    selectedId.value = id
  }

  const selectedJob = () => jobs.find(j => j.id === selectedId.value) ?? null

  return { jobs, selectedId, selectedJob, addJob, stopJob, removeJob, selectJob }
}
```

- [ ] **Step 6.2: Create `utools/src/components/bisync/BisyncForm.vue`**

```vue
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

defineEmits(['submit', 'cancel'])
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
```

- [ ] **Step 6.3: Create `utools/src/components/bisync/BisyncPanel.vue`**

```vue
<template>
  <div class="panel">
    <!-- LEFT: job list -->
    <JobList
      :jobs="jobs"
      :selectedId="selectedId"
      @select="selectJob"
      @new-job="showForm = true"
    />

    <!-- RIGHT: form OR detail -->
    <div class="panel-right">
      <!-- New job form -->
      <template v-if="showForm">
        <div class="panel-header">New bisync job</div>
        <BisyncForm
          @submit="onSubmit"
          @cancel="showForm = false"
        />
      </template>

      <!-- Job detail -->
      <template v-else-if="currentJob">
        <div class="panel-header">
          <span class="job-title">{{ currentJob.label }}</span>
          <StatusBadge :status="currentJob.status" />
          <button
            v-if="currentJob.status === 'running'"
            class="btn btn-danger btn-sm"
            @click="stopJob(currentJob.id)"
          >Stop</button>
          <button
            v-else
            class="btn btn-ghost btn-sm"
            @click="removeJob(currentJob.id)"
          >✕</button>
        </div>
        <div class="args-line">{{ currentJob.args.join(' ') }}</div>
        <LogViewer :lines="currentJob.lines" />
      </template>

      <!-- Empty state -->
      <template v-else>
        <div class="empty-state">Click "＋ New job" to start a bisync.</div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useJobs }    from '../../composables/useJobs.js'
import JobList        from '../shared/JobList.vue'
import LogViewer      from '../shared/LogViewer.vue'
import StatusBadge    from '../shared/StatusBadge.vue'
import BisyncForm     from './BisyncForm.vue'

const { jobs, selectedId, selectedJob, addJob, stopJob, removeJob, selectJob } = useJobs('bisync')

const showForm   = ref(false)
const currentJob = computed(() => selectedJob())

function onSubmit({ label, args }) {
  addJob(label, args)
  showForm.value = false
}
</script>

<style scoped>
.panel {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.panel-right {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 0;
}

.panel-header {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--bg2);
  flex-shrink: 0;
  font-size: 12px;
  font-weight: 600;
}

.job-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }

.args-line {
  padding: 4px 12px;
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text2);
  background: var(--bg2);
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.empty-state {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text2);
  font-size: 13px;
}

.btn-sm { padding: 3px 8px; font-size: 11px; }

/* LogViewer needs padding from parent */
:deep(.log-viewer) { margin: 8px; border-radius: var(--radius); }
</style>
```

- [ ] **Step 6.4: Build and verify**

```bash
cd utools && npm run build
```

Expected: clean build. The BisyncPanel should be wired up and visible when the plugin opens.

- [ ] **Step 6.5: Commit**

```bash
git add utools/src/composables/useJobs.js \
        utools/src/components/bisync/
git commit -m "feat(utools): useJobs composable + BisyncPanel (multi-instance)"
```

---

## Task 7: Sync2podPanel

**Files:**
- Create: `utools/src/components/sync2pod/Sync2podForm.vue`
- Create: `utools/src/components/sync2pod/Sync2podPanel.vue`

- [ ] **Step 7.1: Create `utools/src/components/sync2pod/Sync2podForm.vue`**

```vue
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
        <label class="checkbox-label"><input type="checkbox" v-model="skipVerify" checked /> --skip-verify</label>
        <label class="checkbox-label"><input type="checkbox" v-model="dryRun" /> --dry-run</label>
        <label class="checkbox-label"><input type="checkbox" v-model="debug" /> --debug</label>
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
const debug       = ref(false)
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
    if (debug.value)      args.push('--debug')
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
```

- [ ] **Step 7.2: Create `utools/src/components/sync2pod/Sync2podPanel.vue`**

```vue
<template>
  <div class="panel">
    <JobList
      :jobs="jobs"
      :selectedId="selectedId"
      @select="selectJob"
      @new-job="showForm = true"
    />

    <div class="panel-right">
      <template v-if="showForm">
        <div class="panel-header">New sync2pod job</div>
        <Sync2podForm @submit="onSubmit" @cancel="showForm = false" />
      </template>

      <template v-else-if="currentJob">
        <div class="panel-header">
          <span class="job-title">{{ currentJob.label }}</span>
          <StatusBadge :status="currentJob.status" />
          <button v-if="currentJob.status === 'running'" class="btn btn-danger btn-sm" @click="stopJob(currentJob.id)">Stop</button>
          <button v-else class="btn btn-ghost btn-sm" @click="removeJob(currentJob.id)">✕</button>
        </div>
        <div class="args-line">{{ currentJob.args.join(' ') }}</div>
        <LogViewer :lines="currentJob.lines" />
      </template>

      <template v-else>
        <div class="empty-state">Click "＋ New job" to start a sync2pod operation.</div>
      </template>
    </div>
  </div>
</template>

<script setup>
import { ref, computed } from 'vue'
import { useJobs }     from '../../composables/useJobs.js'
import JobList         from '../shared/JobList.vue'
import LogViewer       from '../shared/LogViewer.vue'
import StatusBadge     from '../shared/StatusBadge.vue'
import Sync2podForm    from './Sync2podForm.vue'

const { jobs, selectedId, selectedJob, addJob, stopJob, removeJob, selectJob } = useJobs('sync2pod')

const showForm   = ref(false)
const currentJob = computed(() => selectedJob())

function onSubmit({ label, args }) {
  addJob(label, args)
  showForm.value = false
}
</script>

<style scoped>
.panel { display: flex; flex: 1; overflow: hidden; }
.panel-right { flex: 1; display: flex; flex-direction: column; overflow: hidden; }
.panel-header {
  display: flex; align-items: center; gap: 8px;
  padding: 8px 12px; border-bottom: 1px solid var(--border);
  background: var(--bg2); flex-shrink: 0; font-size: 12px; font-weight: 600;
}
.job-title { flex: 1; min-width: 0; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.args-line {
  padding: 4px 12px; font-family: var(--mono); font-size: 10px;
  color: var(--text2); background: var(--bg2); border-bottom: 1px solid var(--border); flex-shrink: 0;
}
.empty-state { flex: 1; display: flex; align-items: center; justify-content: center; color: var(--text2); font-size: 13px; }
.btn-sm { padding: 3px 8px; font-size: 11px; }
:deep(.log-viewer) { margin: 8px; border-radius: var(--radius); }
</style>
```

- [ ] **Step 7.3: Commit**

```bash
git add utools/src/components/sync2pod/
git commit -m "feat(utools): Sync2podPanel with multi-instance + list/init operations"
```

---

## Task 8: JiratoolsPanel

**Files:**
- Create: `utools/src/components/jiratools/OperationList.vue`
- Create: `utools/src/components/jiratools/operations/SprintReport.vue`
- Create: `utools/src/components/jiratools/JiratoolsPanel.vue`

- [ ] **Step 8.1: Create `utools/src/components/jiratools/OperationList.vue`**

```vue
<template>
  <div class="op-list">
    <div
      v-for="op in operations"
      :key="op.id"
      class="op-item"
      :class="{ active: op.id === activeId }"
      @click="$emit('select', op.id)"
    >
      <span class="op-icon">{{ op.icon }}</span>
      <span class="op-name">{{ op.name }}</span>
    </div>
  </div>
</template>

<script setup>
defineProps({ activeId: { type: String, default: null } })
defineEmits(['select'])

const operations = [
  { id: 'sprint-report', icon: '📊', name: 'Sprint Report' },
  // Future operations added here
]
</script>

<style scoped>
.op-list {
  width: 140px;
  flex-shrink: 0;
  background: var(--bg2);
  border-right: 1px solid var(--border);
  padding: 8px 4px;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.op-item {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 7px 8px;
  border-radius: var(--radius);
  cursor: pointer;
  color: var(--text2);
  font-size: 12px;
  font-weight: 500;
  transition: background 0.12s;
}
.op-item:hover { background: var(--bg3); color: var(--text); }
.op-item.active { background: var(--accent); color: #fff; }
.op-icon { font-size: 14px; }
</style>
```

- [ ] **Step 8.2: Create `utools/src/components/jiratools/operations/SprintReport.vue`**

```vue
<template>
  <div class="sprint-report">
    <form class="op-form" @submit.prevent="run">
      <div class="form-group">
        <label>Jira user</label>
        <input v-model="user" placeholder="xchen17" required />
      </div>
      <div class="form-group">
        <label>Sprint label</label>
        <input v-model="label" placeholder="SDS-CP-Sprint08-2026" required />
      </div>
      <div class="form-group">
        <label class="checkbox-label"><input type="checkbox" v-model="all" /> --all (full detail)</label>
        <label class="checkbox-label"><input type="checkbox" v-model="report" /> --report (table)</label>
      </div>
      <div class="config-hint">{{ configHint }}</div>
      <button type="submit" class="btn btn-primary" :disabled="running">
        {{ running ? '⏳ Running…' : '▶ Run' }}
      </button>
    </form>

    <div class="op-output">
      <LogViewer v-if="lines.length > 0" :lines="lines" />
      <div v-else class="output-empty">Results will appear here.</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import LogViewer from '../../shared/LogViewer.vue'

const user    = ref('')
const label   = ref('')
const all     = ref(false)
const report  = ref(false)
const running = ref(false)
const lines   = ref([])

const configHint = ref('')

onMounted(() => {
  const cfg  = window.myscriptAPI?.loadJiraConfig() ?? {}
  const home = window.myscriptAPI?.getHomeDir() ?? '~'
  if (cfg.user)  user.value  = cfg.user
  if (cfg.label) label.value = cfg.label
  configHint.value = cfg.found
    ? `Config loaded from ${home}/.my_jira_config`
    : `No config at ${home}/.my_jira_config`
})

function run() {
  if (!user.value || !label.value) return
  const args = ['--user', user.value, '--label', label.value]
  if (all.value)    args.push('--all')
  else if (report.value) args.push('--report')

  lines.value = []
  running.value = true

  const jobId = crypto.randomUUID()
  window.myscriptAPI.runTool(
    jobId,
    'jira-analyzer',
    args,
    (line) => lines.value.push(line),
    (_code) => { running.value = false },
  )
}
</script>

<style scoped>
.sprint-report {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.op-form {
  padding: 12px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}

.form-group { display: flex; flex-direction: column; gap: 4px; }

.config-hint { font-size: 10px; color: var(--text2); font-style: italic; }

.op-output {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  padding: 8px;
}

.output-empty {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text2);
  font-size: 12px;
}

:deep(.log-viewer) { border-radius: var(--radius); }
</style>
```

- [ ] **Step 8.3: Create `utools/src/components/jiratools/JiratoolsPanel.vue`**

```vue
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
```

- [ ] **Step 8.4: Commit**

```bash
git add utools/src/components/jiratools/
git commit -m "feat(utools): JiratoolsPanel with extensible operation list"
```

---

## Task 9: Build, cleanup, final commit

**Files:**
- Delete: `utools/app.js`
- Delete: `utools/style.css`
- Modify: `Makefile` — add new targets to `.PHONY`

- [ ] **Step 9.1: Full build**

```bash
cd utools && npm run build
```

Expected: `dist/index.html` created, no errors, no missing imports.

- [ ] **Step 9.2: Delete old files**

```bash
rm utools/app.js utools/style.css
```

- [ ] **Step 9.3: Update `.PHONY` in Makefile**

Change line 1 of Makefile to:
```makefile
.PHONY: install clean utools-logo utools-install utools-build utools-dev
```

- [ ] **Step 9.4: Verify `node --check` on preload.js**

```bash
node --check utools/preload.js
```

Expected: no output.

- [ ] **Step 9.5: Load plugin in uTools and smoke-test**

1. Open uTools → Developer → 导入源码工程 → select `utools/plugin.json`
2. Type `bisync` in uTools search bar → plugin opens on Bisync tab
3. Click "＋ New job" → fill in two paths → click Run → verify live log appears
4. Type `jiratools` → opens Jira panel → verify Sprint Report form loads with prefilled config
5. Type `sync2pod` → opens Sync2pod panel → click "＋ New job" → verify project list loads

- [ ] **Step 9.6: Final commit**

```bash
git add -A
git commit -m "feat(utools): complete Vue 3 + Vite frontend with multi-instance jobs

- Replace plain HTML/JS with Vue 3 + Vite
- bisync & sync2pod: Master-Detail with concurrent job support + history
- jiratools: extensible operation list + detail panel
- Theme system: light/dark/system via CSS vars + localStorage
- preload.js: multi-job keyed by UUID (concurrent jobs of same type)

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```
