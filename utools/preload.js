'use strict'

const { spawn, execSync } = require('child_process')
const path = require('path')
const fs = require('fs')
const os = require('os')

// ── Project root ───────────────────────────────────────────────────────────────
// Walk up from __dirname to find the directory containing pyproject.toml.
// This is more robust than a hard-coded '../' in case uTools or Electron resolves
// __dirname differently depending on how the plugin is loaded.
function findProjectRoot() {
  let dir = __dirname
  for (let i = 0; i < 5; i++) {
    if (fs.existsSync(path.join(dir, 'pyproject.toml'))) return dir
    const parent = path.dirname(dir)
    if (parent === dir) break  // reached filesystem root
    dir = parent
  }
  // Last resort: one level up from __dirname (original assumption)
  return path.resolve(__dirname, '..')
}

const PROJECT_ROOT = findProjectRoot()

function isProjectRootValid() {
  return fs.existsSync(path.join(PROJECT_ROOT, 'pyproject.toml'))
}

// ── Login-shell environment ───────────────────────────────────────────────────
// Finder-launched apps get a minimal set of environment variables. Read the full
// environment from the login shell so that tools relying on custom env vars
// (e.g. JIRA_API_TOKEN, JIRA_API_BASE_URL) work correctly.
function getLoginShellEnv() {
  try {
    const shell = process.env.SHELL || '/bin/zsh'
    const raw = execSync(`${shell} -l -c 'source ~/.zshrc >/dev/null 2>&1; env'`, { timeout: 5000 }).toString().trim()
    const env = {}
    for (const line of raw.split('\n')) {
      const idx = line.indexOf('=')
      if (idx > 0) {
        env[line.substring(0, idx)] = line.substring(idx + 1)
      }
    }
    return env
  } catch {
    // Fallback: extend current PATH with the most common extra locations
    const extras = [
      path.join(os.homedir(), '.local', 'bin'),
      path.join(os.homedir(), 'go', 'bin'),
      '/opt/homebrew/bin',
      '/opt/homebrew/sbin',
      '/usr/local/bin',
      '/usr/bin',
      '/bin',
    ]
    return { ...process.env, PATH: (process.env.PATH || '') + ':' + extras.join(':') }
  }
}

const LOGIN_SHELL_ENV = getLoginShellEnv()

// ── Tool binary discovery ──────────────────────────────────────────────────────
// Returns { program, prefixArgs } or null.
function resolveToolBin(toolName) {
  // 1. Try the venv binary directly — fastest and most reliable after `make install`
  const venvBin = path.join(PROJECT_ROOT, '.venv', 'bin', toolName)
  if (fs.existsSync(venvBin)) {
    return { program: venvBin, prefixArgs: [] }
  }

  // 2. Try `uv run <toolName>` — works even without an activated venv
  const uvCandidates = [
    'uv',
    path.join(os.homedir(), '.local', 'bin', 'uv'),
    path.join(os.homedir(), '.cargo', 'bin', 'uv'),
    '/opt/homebrew/bin/uv',
    '/usr/local/bin/uv',
  ]
  for (const uv of uvCandidates) {
    try {
      execSync(`"${uv}" --version`, { stdio: 'ignore', timeout: 2000 })
      return { program: uv, prefixArgs: ['run', toolName] }
    } catch { /* try next */ }
  }

  return null
}

// ── ANSI escape sequence stripper ─────────────────────────────────────────────
// bisync uses loguru (colors), jira-analyzer emits terminal hyperlinks.
// Strip all escape sequences before sending lines to the renderer.
function stripAnsi(str) {
  return str
    .replace(/\x1b\[[0-9;]*[A-Za-z]/g, '')            // CSI: colors, cursor
    .replace(/\x1b\][^\x07\x1b]*(\x07|\x1b\\)/g, '')  // OSC: hyperlinks, title
    .replace(/\x1b[PX^_][^\x1b]*\x1b\\/g, '')         // DCS/SOS/APC/PM/ST
    .replace(/\x1b./g, '')                             // remaining 2-char escapes
}

// ── Settings key registry ─────────────────────────────────────────────────────
// dbStorage keys follow the pattern: settings/<name>
// e.g. settings/jira_bin, settings/jira_user
const SETTING_KEYS = [
  'jira_bin', 'tess_bin', 'unison_bin', 'fswatch_bin',
  'jira_user', 'jira_label', 'jira_url',
]
const SETTINGS_PREFIX = 'settings/'

// ── Process registry ──────────────────────────────────────────────────────────
// Keyed by jobId (UUID supplied by the caller). Supports concurrent jobs.
const procs = {}

// ── Public API ────────────────────────────────────────────────────────────────
window.myscriptAPI = {
  isReady() {
    return isProjectRootValid()
  },

  getProjectRoot() {
    return PROJECT_ROOT
  },

  getHomeDir() {
    return os.homedir()
  },

  // Run a tool process.
  // jobId    — caller-supplied UUID; uniquely identifies this job instance
  // toolName — the CLI command name (e.g. 'bisync', 'jira-analyzer', 'sync2pod')
  // args     — array of CLI arguments
  // onData(line)   — called with each stripped stderr line (and command echo)
  // onExit(code)   — called on exit; code is -1 if killed by signal
  // onStdout(line) — optional; when provided, stdout lines go here instead of onData
  runTool(jobId, toolName, args, onData, onExit, onStdout = null) {
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
      env: { ...LOGIN_SHELL_ENV, PYTHONUNBUFFERED: '1' },
      // detached: true creates a new process group (pgid == proc.pid).
      // process.kill(-pid, signal) then kills the entire tree, including
      // any child processes spawned by the tool (fswatch, kubectl, etc.).
      detached: true,
      stdio: ['pipe', 'pipe', 'pipe'],
    })

    procs[jobId] = proc

    // Close stdin immediately to prevent tools from blocking on input().
    // sync2pod's confirmation prompt is bypassed via --skip-verify in the UI.
    proc.stdin.end()

    // Route stdout and stderr to separate callbacks when onStdout is provided;
    // otherwise merge both into onData (backward-compatible behaviour).
    const stdoutCallback = onStdout ?? onData
    let stdoutBuf = ''
    let stderrBuf = ''

    proc.stdout.on('data', (data) => {
      stdoutBuf += stripAnsi(data.toString('utf8'))
      const parts = stdoutBuf.split('\n')
      stdoutBuf = parts.pop()
      for (const line of parts) {
        if (line !== '') stdoutCallback(line)
      }
    })

    proc.stderr.on('data', (data) => {
      stderrBuf += stripAnsi(data.toString('utf8'))
      const parts = stderrBuf.split('\n')
      stderrBuf = parts.pop()
      for (const line of parts) {
        if (line !== '') onData(line)
      }
    })

    proc.on('close', (code, signal) => {
      // Flush any buffered text that arrived without a trailing newline
      if (stdoutBuf.trim()) { stdoutCallback(stdoutBuf.trim()); stdoutBuf = '' }
      if (stderrBuf.trim()) { onData(stderrBuf.trim()); stderrBuf = '' }
      delete procs[jobId]
      // code is null when the process was killed by a signal
      onExit(signal ? -1 : (code ?? 0))
    })

    proc.on('error', (err) => {
      delete procs[jobId]
      onData(`[error] ${err.message}`)
      onExit(1)
    })
  },

  stopTool(jobId) {
    const proc = procs[jobId]
    if (!proc) return
    const pid = proc.pid
    delete procs[jobId]
    try {
      // Kill the whole process group — handles fswatch, kubectl, Python child, etc.
      process.kill(-pid, 'SIGTERM')
    } catch { /* process may have already exited */ }
    // Force-kill after 3 s if SIGTERM was ignored
    setTimeout(() => {
      try { process.kill(-pid, 'SIGKILL') } catch { /* already gone */ }
    }, 3000)
  },

  listSync2podProjects() {
    const dir = path.join(os.homedir(), '.sync2pod')
    try {
      return fs.readdirSync(dir)
        .filter(name => {
          try {
            return (
              fs.statSync(path.join(dir, name)).isDirectory() &&
              fs.existsSync(path.join(dir, name, 'sync_config.json'))
            )
          } catch { return false }
        })
        .sort()
    } catch { return [] }
  },

  // ── Global settings API (uTools dbStorage) ────────────────────────────────
  // Keys: settings/jira_bin, settings/tess_bin, settings/unison_bin, etc.
  loadSettings() {
    const result = {}
    for (const key of SETTING_KEYS) {
      result[key] = utools.dbStorage.getItem(SETTINGS_PREFIX + key) || ''
    }
    return result
  },

  getSetting(key) {
    return utools.dbStorage.getItem(SETTINGS_PREFIX + key) || ''
  },

  saveSettings(settings) {
    try {
      for (const key of SETTING_KEYS) {
        const val = settings[key]
        if (typeof val === 'string' && val) {
          utools.dbStorage.setItem(SETTINGS_PREFIX + key, val)
        } else {
          utools.dbStorage.removeItem(SETTINGS_PREFIX + key)
        }
      }
      return { ok: true }
    } catch (err) {
      return { ok: false, error: err.message }
    }
  },

  // ── Preferences API (uTools dbStorage, JSON values) ───────────────────────
  // For UI preferences that should survive plugin restarts (column visibility,
  // sorting, input history, etc.). Keys are prefixed with "prefs/".
  getPref(key) {
    try {
      const raw = utools.dbStorage.getItem('prefs/' + key)
      return raw != null ? JSON.parse(raw) : null
    } catch { return null }
  },

  setPref(key, value) {
    try {
      if (value == null) {
        utools.dbStorage.removeItem('prefs/' + key)
      } else {
        utools.dbStorage.setItem('prefs/' + key, JSON.stringify(value))
      }
    } catch { /* ignore */ }
  },

  testBinary(binPath, testArgs, onResult) {
    if (!binPath) { onResult({ ok: false, error: 'empty path', output: '' }); return }
    const args = Array.isArray(testArgs) ? testArgs : []
    const proc = spawn(binPath, args, {
      env: LOGIN_SHELL_ENV,
      stdio: ['ignore', 'pipe', 'pipe'],
    })
    let output = ''
    let done = false
    const finish = (result) => {
      if (done) return
      done = true
      clearTimeout(timer)
      onResult({ ...result, output: output.trimEnd() })
    }
    proc.stdout.on('data', (data) => { output += data.toString() })
    proc.stderr.on('data', (data) => { output += data.toString() })
    const timer = setTimeout(() => {
      try { proc.kill() } catch { /* already exited */ }
      finish({ ok: false, error: 'timeout (10s)' })
    }, 10000)
    proc.on('close', (code) => finish({ ok: code === 0, code }))
    proc.on('error', (err) => finish({ ok: false, error: err.message }))
  },

  openExternal(url) {
    if (url) utools.shellOpenExternal(url)
  },
}

// ── uTools lifecycle ──────────────────────────────────────────────────────────
// Dispatch a custom event so app.js can react (tab switching, etc.)
utools.onPluginEnter(({ code }) => {
  window.dispatchEvent(new CustomEvent('utoolsEnter', { detail: { code } }))
})

// Stop all running tools when the plugin window is closed/hidden
utools.onPluginOut(() => {
  Object.keys(procs).forEach(id => window.myscriptAPI.stopTool(id))
})
