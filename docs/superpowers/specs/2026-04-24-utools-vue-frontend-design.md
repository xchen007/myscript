# uTools Plugin Vue Frontend — Design Spec

Date: 2026-04-24

## Problem

The current `utools/` frontend is plain HTML/CSS/JS. It is single-task only (running a tool again overwrites the previous process), has no component reuse, and is hard to extend or beautify. The user needs multi-instance concurrent job support, history retention, an expandable Jiratools panel, and a proper theme system.

## Approach

Replace the vanilla frontend with **Vue 3 + Vite**. The Node.js `preload.js` bridge is extended to support concurrent jobs by ID. All Python CLI tools are unchanged.

---

## Architecture

### Build

| Item | Value |
|------|-------|
| Framework | Vue 3 (Composition API) |
| Build tool | Vite |
| Source root | `utools/src/` |
| Build output | `utools/dist/` (gitignored) |
| Plugin entry | `plugin.json` → `main: "dist/index.html"` |
| Dev command | `npm run dev` (Vite dev server) |
| Build command | `npm run build` |
| Makefile targets | `utools-dev`, `utools-build` added |

`preload.js` remains at `utools/preload.js` (loaded by Electron before the renderer). It exposes `window.myscriptAPI` as before, extended for multi-job support.

---

## Layout Structure

```
App
 ├── ToolNav          Left sidebar: tool switcher + theme toggle
 ├── BisyncPanel      Master-Detail, multi-instance
 ├── Sync2podPanel    Master-Detail, multi-instance (reuses shared components)
 └── JiratoolsPanel   Operation list + detail panel
```

### ToolNav
- Vertical icon+label buttons for Bisync / Jiratools / Sync2pod
- Theme toggle at the bottom (light / dark / system)
- Active tool highlighted with accent color

### BisyncPanel & Sync2podPanel (shared pattern)

Both use the same **Master-Detail** layout:

**Left column — Job list:**
- Each job shown as a card: short label (args summary), status badge, elapsed time
- Status: 🔵 running (pulsing dot) / ✅ done / ❌ error / ⏹ stopped
- "＋ New job" button at the top opens the form

**Right column — Job detail:**
- Top: read-only summary of the job's parameters
- Middle: real-time `<LogViewer>` (ANSI-stripped, auto-scroll)
- Bottom: Stop button (only visible while running)

Jobs persist in memory for the plugin session. Closing the plugin clears history.

### JiratoolsPanel

**Left column — Operation list:**
- Static list of available Jira operations
- Currently: "Sprint Report"
- Future operations added here as new `operations/` components
- Active operation highlighted

**Right column — Operation detail:**
- Each operation defines its own form (parameters) + "Run" button
- Output shown below the form as formatted result cards (not raw terminal log)
- Supports re-running: each run replaces the previous result in that panel

---

## Multi-Instance State (`preload.js` + `useJobs`)

### preload.js API changes

```js
window.myscriptAPI = {
  // Start a new job; returns jobId (caller-supplied UUID)
  runTool(jobId, cmd, args, onLine, onClose),

  // Kill a specific job by jobId
  stopTool(jobId),

  // Existing helpers unchanged
  listSync2podProjects(),
  loadJiraConfig(),
  isReady(),
  getProjectRoot(),
  getHomeDir(),
}
```

Each job has its own child process entry keyed by `jobId`. Multiple jobs with the same `cmd` can run concurrently.

### useJobs composable (Vue side)

```ts
interface Job {
  id: string           // UUID
  tool: string         // 'bisync' | 'sync2pod'
  label: string        // short display label (e.g. "docs → Dropbox")
  args: string[]       // full CLI args
  status: 'running' | 'done' | 'stopped' | 'error'
  lines: string[]      // log lines
  startedAt: Date
  exitCode: number | null
}
```

`useJobs(tool)` returns: `{ jobs, addJob, stopJob, clearDone }`

New jobs are prepended (newest first). No persistence across plugin restarts.

---

## Theme System

- CSS custom properties (already established pattern)
- Three modes: `light` | `dark` | `system`
- `system` uses `prefers-color-scheme` media query
- Selected theme stored in `localStorage` key `myscript-theme`
- Toggle button in ToolNav cycles through the three modes
- Initial default: `system`

---

## Component Tree

```
utools/
  plugin.json          ← main: "dist/index.html"
  preload.js           ← extended for multi-job
  src/
    main.js
    App.vue            ← root: tool switcher, theme provider
    components/
      ToolNav.vue      ← sidebar nav + theme toggle
      shared/
        JobList.vue    ← reused by Bisync & Sync2pod
        LogViewer.vue  ← ANSI-stripped scrollable log
        StatusBadge.vue ← running/done/stopped/error
      bisync/
        BisyncPanel.vue  ← Master-Detail container
        BisyncForm.vue   ← new job form (source, target, options)
      sync2pod/
        Sync2podPanel.vue  ← Master-Detail container
        Sync2podForm.vue   ← new job form (project select, options)
      jiratools/
        JiratoolsPanel.vue   ← operation list + detail
        OperationList.vue    ← static list of operations
        operations/
          SprintReport.vue   ← form + result cards
  vite.config.js
  package.json
  dist/                ← gitignored
```

---

## Files Removed / Replaced

| File | Action |
|------|--------|
| `utools/index.html` | Overwritten — becomes the Vite HTML entry template (references `src/main.js`) |
| `utools/app.js` | Replaced by Vue components |
| `utools/style.css` | Replaced by per-component `<style>` + global CSS variables |
| `utools/preload.js` | Extended (not replaced) |
| `utools/plugin.json` | Updated: `main` → `"dist/index.html"` |

---

## Out of Scope

- Pinia / Vuex (simple composables are sufficient)
- Unit tests for Vue components
- Backend changes to Python CLI tools
- Persisting job history across plugin restarts
