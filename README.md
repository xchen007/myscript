# myscript

Personal productivity CLI tools with a uTools plugin UI.

## Tools

| Command | Description |
|---------|-------------|
| `bisync` | Local bidirectional file sync (Unison-based, FSEvents real-time) |
| `jira-analyzer` | JIRA sprint worklog & statistics analyzer |
| `sync2pod` | Sync local directory to a Kubernetes pod |

---

## Prerequisites

| Tool | Install | Required by |
|------|---------|-------------|
| [uv](https://docs.astral.sh/uv/) | `curl -LsSf https://astral.sh/uv/install.sh \| sh` | Package manager |
| unison | `brew install unison` | bisync |
| fswatch | `brew install fswatch` | bisync (optional, real-time mode) |
| jira CLI | See team wiki | jiratools |
| kubectl / tess | See team wiki | sync2pod |

---

## Development Setup

```bash
git clone <repo>
cd myscript
make install          # creates .venv with Python 3.12 + all deps

# Run any CLI tool
uv run bisync --help
uv run jira-analyzer --help
uv run sync2pod --help
```

---

## CLI Usage

### bisync
```bash
# First sync (source → target), then watch bidirectionally
uv run bisync ~/Documents/notes ~/Dropbox/notes

# Named profile, protect source from remote deletes
uv run bisync ~/src ~/dst --name my-project --nodeletion-source

# Preview only
uv run bisync ~/src ~/dst --dry-run
```

### jira-analyzer
```bash
# Configure once: ~/.my_jira_config
# [jira]
# user = xchen17
# label = SDS-CP-Sprint08-2026
# jira_url = https://jirap.corp.ebay.com

uv run jira-analyzer           # summary from config file
uv run jira-analyzer -r        # + sprint report table
uv run jira-analyzer -a        # all sections
```

### sync2pod
```bash
# Initialize a project config (then edit ~/.sync2pod/<name>/sync_config.json)
uv run sync2pod --init-config --project my-project --local-path ~/workspace/myrepo

uv run sync2pod --list-projects
uv run sync2pod --project my-project
uv run sync2pod --project my-project --dry-run
uv run sync2pod --project my-project --force
```

---

## uTools Plugin

The `utools/` directory contains a plugin that exposes all three tools inside
[uTools](https://u.tools/), the macOS/Windows/Linux launcher.

### Setup

1. Run `make install` (creates `.venv` with all CLI tools).
2. Open uTools → Developer → **导入源码工程** → select `utools/plugin.json`.
3. The plugin reads tools from `.venv/bin/` (created by `make install`).
   If the venv isn't found it falls back to `uv run <tool>`.

### Keywords

| Keyword | Opens |
|---------|-------|
| `myscript` | bisync tab (default) |
| `bisync` | bisync tab |
| `jiratools` or `jira-analyzer` | jiratools tab |
| `sync2pod` | sync2pod tab |

### Notes

- **sync2pod** defaults `--skip-verify` to checked — the plugin runs
  non-interactively and closes stdin, so interactive confirmation prompts
  would otherwise hang the process.
- **Stop** sends `SIGTERM` to the entire process group (handles child
  processes like `fswatch`, `kubectl`, etc.).
- The Python source files are not modified; the plugin is a pure wrapper.

---

## Project Structure

```
myscript/
├── bisync/                  # Bidirectional file sync tool
│   ├── __init__.py
│   └── bisync.py
├── jiratools/               # JIRA sprint analyzer
│   ├── __init__.py
│   └── jira_analyzer.py
├── sync2pod/                # Kubernetes pod sync tool
│   ├── __init__.py
│   └── sync_local_to_pod.py
├── utools/                  # uTools plugin (HTML/JS wrapper)
│   ├── plugin.json          # Plugin manifest
│   ├── preload.js           # Node.js bridge → Python CLIs
│   ├── index.html           # 3-tab UI
│   ├── app.js               # Frontend logic
│   ├── style.css            # Dark/light theme
│   └── logo.png             # Plugin icon
├── pyproject.toml           # Package config & entry points
└── Makefile                 # install / utools-logo / clean
```
