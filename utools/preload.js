'use strict'

const { spawn, execSync } = require('child_process')
const path = require('path')
const fs = require('fs')
const os = require('os')

// ── Project root ───────────────────────────────────────────────────────────────
// preload.js lives at <project>/utools/preload.js — project root is one level up.
const PROJECT_ROOT = path.resolve(__dirname, '..')

function isProjectRootValid() {
  return fs.existsSync(path.join(PROJECT_ROOT, 'pyproject.toml'))
}

// ── Login-shell PATH ──────────────────────────────────────────────────────────
// Finder-launched apps get a minimal PATH. Read the real PATH from the login
// shell so that tools installed via Homebrew, Go, pyenv, etc. are found.
function getLoginShellPath() {
  try {
    const shell = process.env.SHELL || '/bin/zsh'
    return execSync(`${shell} -l -c 'echo $PATH'`, { timeout: 3000 }).toString().trim()
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
    return (process.env.PATH || '') + ':' + extras.join(':')
  }
}

const LOGIN_SHELL_PATH = getLoginShellPath()

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

// ── INI parser ────────────────────────────────────────────────────────────────
// Mirrors Python's configparser so ~/.my_jira_config is read correctly.
function parseIni(content) {
  const sections = {}
  let current = null
  for (const raw of content.split('\n')) {
    const line = raw.trim()
    if (!line || line.startsWith('#') || line.startsWith(';')) continue
    const sectionMatch = line.match(/^\[(.+)\]$/)
    if (sectionMatch) {
      current = sectionMatch[1]
      sections[current] = {}
      continue
    }
    const kvMatch = line.match(/^([^=]+?)\s*=\s*(.*)$/)
    if (kvMatch && current) {
      sections[current][kvMatch[1].trim()] = kvMatch[2].trim()
    }
  }
  return sections
}

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

    // Stream output line-by-line, stripping ANSI sequences
    let buf = ''
    const handleChunk = (data) => {
      buf += stripAnsi(data.toString('utf8'))
      const parts = buf.split('\n')
      buf = parts.pop() // keep incomplete trailing line
      for (const line of parts) {
        if (line !== '') onData(line)
      }
    }

    proc.stdout.on('data', handleChunk)
    proc.stderr.on('data', handleChunk)

    proc.on('close', (code, signal) => {
      // Flush any buffered text that arrived without a trailing newline
      if (buf.trim()) { onData(buf.trim()); buf = '' }
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

  loadJiraConfig() {
    const configFile = path.join(os.homedir(), '.my_jira_config')
    try {
      const ini = parseIni(fs.readFileSync(configFile, 'utf8'))
      return {
        user: ini.jira?.user || '',
        label: ini.jira?.label || '',
        found: true,
      }
    } catch {
      return { user: '', label: '', found: false }
    }
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
