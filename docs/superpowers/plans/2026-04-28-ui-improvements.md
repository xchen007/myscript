# UI Improvements Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Implement 4 UI improvements: icon-only nav, height slider in Settings, full-width Run CTA, and Sprint label Transfer selector.

**Architecture:** All changes are frontend-only (Vue 3 components + one preload.js addition). No backend changes needed. Tasks are independent — implement in order.

**Tech Stack:** Vue 3 `<script setup>`, CSS custom properties, uTools `setExpendHeight` API, `window.myscriptAPI` bridge.

---

## File Map

| File | Change |
|------|--------|
| `utools/preload.js` | Add `setExpendHeight(h)` to `window.myscriptAPI` |
| `utools/src/components/ToolNav.vue` | Icon-only, 40px wide, title tooltips |
| `utools/src/components/settings/SettingsPanel.vue` | Height slider section |
| `utools/src/components/jiratools/operations/SprintReport.vue` | Full-width Run CTA, wire LabelTransfer |
| `utools/src/components/jiratools/operations/LabelTransfer.vue` | **New** — dual-panel label selector |

---

### Task 1: Icon-only nav (ToolNav.vue)

**Files:**
- Modify: `utools/src/components/ToolNav.vue`

- [ ] **Step 1: Remove labels, add title attributes, narrow width**

Replace the entire `.tool-nav` style block and template nav-btn label spans:

```vue
<!-- template: remove <span class="nav-label"> from every nav-btn -->
<button
  v-for="tool in tools"
  :key="tool.id"
  class="nav-btn"
  :class="{ active: activeTool === tool.id }"
  :title="tool.label"
  @click="$emit('select', tool.id)"
>
  <span class="nav-icon">
    <template v-if="tool.id === 'jiratools'">
      <!-- jira SVG unchanged -->
    </template>
    <template v-else>{{ tool.icon }}</template>
  </span>
</button>

<!-- settings button -->
<button
  class="nav-btn settings-btn"
  :class="{ active: activeTool === 'settings' }"
  @click="$emit('select', 'settings')"
  title="Settings"
>
  <span class="nav-icon">⚙️</span>
</button>

<!-- theme button -->
<button class="nav-btn theme-btn" @click="cycleTheme" :title="`Theme: ${mode}`">
  <span class="nav-icon">{{ themeIcon[mode] }}</span>
</button>
```

CSS changes (replace `.tool-nav` and `.nav-label`):

```css
.tool-nav {
  width: 40px;
  flex-shrink: 0;
  background: var(--bg2);
  border-right: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  padding: 8px 2px;
  gap: 2px;
}

.nav-btn {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 8px 0;
  border: none;
  background: transparent;
  border-radius: var(--radius);
  cursor: pointer;
  color: var(--text2);
  transition: background 0.12s, color 0.12s;
  width: 100%;
}
/* Remove .nav-label entirely */
```

- [ ] **Step 2: Verify in browser** — nav shows only icons, hovering shows OS tooltip with tool name, width is ~40px.

- [ ] **Step 3: Commit**

```bash
cd /Users/xchen17/workspace/myscript
git add utools/src/components/ToolNav.vue
git commit -m "feat(nav): icon-only sidebar, 40px, title tooltips

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 2: Full-width Run CTA (SprintReport.vue)

**Files:**
- Modify: `utools/src/components/jiratools/operations/SprintReport.vue`

The form currently has a small Run button inside `form-header-actions`. Replace with a full-width button at the bottom of the expanded form.

- [ ] **Step 1: Remove Run/Stop from form-header-actions, add full-width CTA below form**

In the template, remove the buttons from `form-header-actions`:
```vue
<!-- REMOVE these two lines from form-header-actions div -->
<button type="button" class="btn btn-primary btn-sm" ...>...</button>
<button v-if="..." type="button" class="btn btn-danger btn-sm" ...>■</button>
```

Keep `form-header-actions` as an empty div (or remove it if unused after). Add after the closing `</form>` tag inside `.form-section`:
```vue
<!-- Full-width CTA (only visible when form is expanded) -->
<div v-show="!formCollapsed" class="form-cta">
  <button
    type="button"
    class="btn cta-run"
    :disabled="appState === 'loading' || !jiraBin || !user || !label"
    @click="run"
  >
    {{ appState === 'loading' ? '⏳ Running…' : '▶ Run' }}
  </button>
  <button
    v-if="appState === 'loading'"
    type="button"
    class="btn cta-stop"
    @click="stop"
  >■ Stop</button>
</div>
```

- [ ] **Step 2: Add CSS**

```css
.form-cta {
  display: flex;
  gap: 8px;
  padding: 0 12px 10px;
}
.cta-run {
  flex: 1;
  justify-content: center;
  font-size: 13px;
  font-weight: 600;
  padding: 8px 0;
  background: var(--accent);
  color: #fff;
  border-radius: var(--radius);
}
.cta-run:hover:not(:disabled) { background: var(--accent-h); }
.cta-run:disabled { opacity: 0.45; cursor: not-allowed; }
.cta-stop {
  padding: 8px 16px;
  background: var(--red);
  color: #fff;
  font-size: 13px;
  font-weight: 600;
  border-radius: var(--radius);
}
.cta-stop:hover { filter: brightness(0.9); }
```

- [ ] **Step 3: Verify** — Run button is full-width at the bottom of the form. When form is collapsed the button is hidden. Stop appears alongside Run when running.

- [ ] **Step 4: Commit**

```bash
git add utools/src/components/jiratools/operations/SprintReport.vue
git commit -m "feat(sprint): full-width Run/Stop CTA at bottom of form

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 3: Add setExpendHeight to preload + height slider in Settings

**Files:**
- Modify: `utools/preload.js`
- Modify: `utools/src/components/settings/SettingsPanel.vue`

- [ ] **Step 1: Expose setExpendHeight in preload.js**

Inside `window.myscriptAPI = { ... }`, add before the closing `}` (after `openExternal`):

```js
setExpendHeight(height) {
  try { utools.setExpendHeight(height) } catch { /* not in utools env */ }
},
```

- [ ] **Step 2: Add height slider to SettingsPanel.vue**

Add a new section in the template, **before** the `<div class="settings-footer">`:

```vue
<!-- Window Height -->
<div class="settings-section">
  <div class="section-label">Window</div>
  <div class="setting-row">
    <label>Plugin Height</label>
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
</div>
```

- [ ] **Step 3: Add windowHeight ref and applyHeight function in `<script setup>`**

```js
const WINDOW_HEIGHT_KEY = 'window_height'
const windowHeight = ref(700)

// In onMounted, after loading settings:
const savedH = window.myscriptAPI?.getPref(WINDOW_HEIGHT_KEY)
if (savedH) windowHeight.value = savedH

function applyHeight() {
  const h = Math.max(480, Math.min(1000, windowHeight.value))
  windowHeight.value = h
  window.myscriptAPI?.setExpendHeight(h)
  window.myscriptAPI?.setPref(WINDOW_HEIGHT_KEY, h)
}
```

Also apply height on mount after loading the saved pref:
```js
// at end of onMounted:
if (savedH) window.myscriptAPI?.setExpendHeight(savedH)
```

- [ ] **Step 4: Add CSS**

```css
.height-ctrl {
  display: flex;
  align-items: center;
  gap: 10px;
}
.height-slider {
  flex: 1;
  width: auto;
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
```

- [ ] **Step 5: Verify** — Settings page shows "Plugin Height" slider (480–1000). Dragging the slider immediately resizes the uTools window. Value persists after closing and reopening the plugin.

- [ ] **Step 6: Commit**

```bash
git add utools/preload.js utools/src/components/settings/SettingsPanel.vue
git commit -m "feat(settings): window height slider via utools.setExpendHeight

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

### Task 4: Sprint label Transfer selector

**Files:**
- Create: `utools/src/components/jiratools/operations/LabelTransfer.vue`
- Modify: `utools/src/components/jiratools/operations/SprintReport.vue`

#### 4a — Create LabelTransfer.vue

- [ ] **Step 1: Create the component**

`utools/src/components/jiratools/operations/LabelTransfer.vue`:

```vue
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
        <div v-if="!available.length" class="lt-empty">No history yet</div>
      </div>
      <!-- Add custom label -->
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
        >{{ lbl }} <span class="lt-rm">✕</span></div>
        <div v-if="!selected.length" class="lt-empty">Click items on the left to select</div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'

const props = defineProps({
  modelValue: { type: Array, default: () => [] }, // selected labels
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
  // Add to history if not already there
  if (!historyLabels.value.includes(lbl)) {
    historyLabels.value = [lbl, ...historyLabels.value].slice(0, 20)
    window.myscriptAPI?.setPref(STORAGE_KEY, historyLabels.value)
  }
  addLabel(lbl)
  newLabel.value = ''
}

// Expose method for parent to refresh history after a run
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
  justify-content: space-between;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
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
}
</style>
```

- [ ] **Step 2: Verify component renders** — open the sprint report, see two panels side by side.

#### 4b — Wire into SprintReport.vue

- [ ] **Step 3: Import and use LabelTransfer**

In `<script setup>`, add:
```js
import LabelTransfer from './LabelTransfer.vue'
const labelTransferRef = ref(null)
```

Change the `label` ref from a string to an array, and update its usage:
```js
// was: const label = ref('')
const labelArr = ref([])  // array of selected labels

// Derived string for backward-compat args
const label = computed(() => labelArr.value.join(','))
```

- [ ] **Step 4: Replace InputWithHistory for labels with LabelTransfer in template**

```vue
<!-- REMOVE: -->
<div class="form-group">
  <label>Sprint label(s)</label>
  <InputWithHistory ref="labelRef" v-model="label" storageKey="sprint-label" ... />
</div>

<!-- ADD: -->
<div class="form-group form-group-full">
  <label>Sprint label(s)</label>
  <LabelTransfer ref="labelTransferRef" v-model="labelArr" historyKey="sprint-label" />
</div>
```

- [ ] **Step 5: Remove labelRef.push() calls, add refreshHistory after run**

In the `run()` function, remove `labelRef.value?.push(label.value)` and instead call after the run starts:
```js
// After run starts, persist each selected label to history:
for (const lbl of labelArr.value) {
  // Merge into input-history:sprint-label
  const STORAGE_KEY = 'input-history:sprint-label'
  const hist = (window.myscriptAPI?.getPref(STORAGE_KEY) ?? []).filter(x => x !== lbl)
  hist.unshift(lbl)
  window.myscriptAPI?.setPref(STORAGE_KEY, hist.slice(0, 20))
}
labelTransferRef.value?.refreshHistory()
```

Also update the `required` check on the CTA button:
```vue
:disabled="appState === 'loading' || !jiraBin || !user || labelArr.length === 0"
```

- [ ] **Step 6: Add form-group-full CSS** (label transfer spans full width when beside user field)

```css
.form-group-full { flex: 2; }
```

- [ ] **Step 7: Verify end-to-end** — Select 2 labels in the transfer panel, click Run, confirm `--label A --label B` args are passed correctly (visible in the log terminal's first line), and labels appear in the Available panel next run.

- [ ] **Step 8: Commit**

```bash
git add utools/src/components/jiratools/operations/LabelTransfer.vue \
        utools/src/components/jiratools/operations/SprintReport.vue
git commit -m "feat(sprint): dual-panel label transfer selector

Co-authored-by: Copilot <223556219+Copilot@users.noreply.github.com>"
```

---

## Build & Test

```bash
cd /Users/xchen17/workspace/myscript/utools
npm run build
# Load dist/index.html in uTools developer mode to verify
```
