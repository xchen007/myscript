# Copilot Instructions

## Repository Overview

Personal productivity CLI tools with a uTools plugin GUI. Three Python CLI tools share a single `pyproject.toml` package, each living in its own subdirectory. A separate Vite+Vue 3 project in `utools/` wraps all three tools in a desktop launcher UI.

## Build & Run

```bash
# Python package (all three CLIs)
make install                  # editable install into .venv via uv
uv run bisync --help
uv run jira-analyzer --help
uv run sync2pod --help

# uTools plugin (Vue 3 frontend) — production build only
cd utools && npm install      # first time only
cd utools && npm run build    # outputs to utools/dist/, loaded by uTools via dist/index.html
```

There are no automated tests or linters configured in this repository.

## Architecture

### Python CLIs (`bisync/`, `jiratools/`, `sync2pod/`)

Each tool is a standalone Python module registered as a console script in `pyproject.toml`:

```toml
[project.scripts]
bisync        = "bisync.bisync:main"
jira-analyzer = "jiratools.jira_analyzer:main"
sync2pod      = "sync2pod.sync_local_to_pod:main"
```

- **bisync** wraps `unison` (external binary) with optional `fswatch`/`watchdog` for real-time mode. State is persisted in `~/.bisync/<profile>/state.json`.
- **jira-analyzer** shells out to the `jira_cli` CLI binary (`/usr/local/bin/jira_cli`). Config is read from `~/.my_jira_config` (INI format, `[jira]` section). Requires `JIRA_API_TOKEN` env var (set in `~/.zshrc`).
- **sync2pod** wraps `tess kubectl` to sync files into a running K8s pod. Project configs live in `~/.sync2pod/<project>/sync_config.json`.

### uTools Plugin (`utools/`)

The plugin is a Vite+Vue 3 SPA that bridges the uTools desktop launcher to the Python CLIs.

- **`preload.js`** — Node.js bridge (CommonJS). uTools requires the preload to be a `.js` file. Because of this, `utools/package.json` does NOT set `"type": "module"`, and `vite.config.mjs` uses the `.mjs` extension to opt into ESM. Runs in the privileged renderer context, exposes `window.myscriptAPI` to the Vue app, handles binary discovery (venv first, then `uv run`), spawns processes as detached process groups, strips ANSI sequences from output.
- **`src/App.vue`** — Root component with a three-tab layout (bisync / jiratools / sync2pod). Tab switching is driven by the uTools keyword that launched the plugin via a `utoolsEnter` custom DOM event dispatched by `preload.js`.
- **`src/composables/useJobs.js`** — Shared composable for all tool panels. Manages a reactive list of concurrent jobs, each with `{ id, label, args, status, lines[], exitCode }`.
- **`src/components/<tool>/`** — One subdirectory per tool containing its panel component(s).

## Key Conventions

### Python

- Use `loguru` for all logging (not `logging`). Call `logger.remove()` then `logger.add(sys.stderr, ...)` at startup.
- Config objects use `@dataclass` with a `from_dict(cls, d)` classmethod and `__post_init__` for derived fields (see `SyncConfig` in `sync_local_to_pod.py`).
- Include `from __future__ import annotations` at the top of every Python file.
- `bisync/bisync.py` contains Chinese-language comments; preserve this convention when editing that file.

### uTools Frontend

- All Vue components use `<script setup>` (Composition API).
- Tool processes are managed exclusively through the `useJobs(cmd)` composable — never call `window.myscriptAPI.runTool` directly from a component.
- `stdin` is always closed immediately after spawning a tool process. Tools must not block on interactive input. Use `--skip-verify` / `--dry-run` flags for non-interactive operation.
- Stopping a tool sends `SIGTERM` to the entire process group (`process.kill(-pid, 'SIGTERM')`) to also terminate child processes (e.g., `fswatch`, `kubectl`).
- CSS variables (`--bg`, `--fg`, `--mono`, etc.) provide dark/light theming; never hardcode colors.

### Project-wide

- The package manager is `uv`. Always use `uv run <tool>` or activate `.venv` — never `pip install` directly.
- `make install` is the single setup command; it creates `.venv` and installs in editable mode.
- The `utools/dist/` directory is the plugin's built output and is gitignored; always run `npm run build` before loading the plugin in uTools.

## Troubleshooting: uTools Shell Environment

uTools (Electron) apps launched from Finder/Dock inherit a **minimal** shell environment, not the full terminal environment. This causes two classes of issues:

### 1. Missing PATH entries → `command not found`

Electron's `/bin/sh` only has `/usr/bin:/bin:/usr/sbin:/sbin`. Tools installed via Homebrew (`/opt/homebrew/bin`), Go, Cargo, or custom locations (`/usr/local/bin`) won't be found.

**Solution in `preload.js`**: `getLoginShellEnv()` runs `$SHELL -l -c 'source ~/.zshrc >/dev/null 2>&1; env'` at startup to capture the full login environment (PATH + all env vars), then passes it to every spawned subprocess.

### 2. Missing env vars (e.g. `JIRA_API_TOKEN`) → tool auth failures

Many CLI tools depend on env vars set in `~/.zshrc` (interactive shell config). However:

| zsh flag | Sources `.zprofile` (PATH) | Sources `.zshrc` (env vars) |
|----------|----------------------------|-----------------------------|
| `-l` (login only) | ✅ | ❌ |
| `-i` (interactive only) | ❌ | ✅ |
| `-li` (both) | ✅ | ✅ but startup output pollutes stdout |
| `-l` + `source ~/.zshrc` | ✅ | ✅ clean — **use this** |

**Correct pattern** (used in both `preload.js` and `jira_analyzer.py`):
```bash
/bin/zsh -l -c 'source ~/.zshrc >/dev/null 2>&1; <actual_command>'
```
- `-l` → loads `.zprofile` for full PATH
- `source ~/.zshrc >/dev/null 2>&1` → loads env vars like `JIRA_API_TOKEN`, suppresses startup output (e.g. "SDDZ mode enabled") that would pollute JSON
- This ensures the subprocess has the same environment as a normal terminal session

### Quick diagnosis checklist

If a CLI tool fails inside uTools but works in terminal:
1. **`command not found`** → the tool's directory is not in the base login PATH. Check that `preload.js` passes `LOGIN_SHELL_ENV` to `spawn()`.
2. **Auth / token error** → the required env var is in `~/.zshrc` (interactive-only). Ensure `source ~/.zshrc` is included in the shell wrapper.
3. **Garbled JSON output** → shell startup messages mixed into stdout. Never use `-i` flag directly; use `source ~/.zshrc >/dev/null 2>&1` instead.
