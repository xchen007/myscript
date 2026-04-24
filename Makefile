.PHONY: install clean utools-logo utools-install utools-build utools-dev

SHELL := /bin/bash

# Find uv: check PATH first, then the default install location (~/.local/bin)
UV := $(shell command -v uv 2>/dev/null || echo $(HOME)/.local/bin/uv)

## ── Development ─────────────────────────────────────────────────────

# Install / reinstall in editable mode; CLIs become available inside the venv
install:
	$(UV) pip install -e . --reinstall
	@echo "✅  Done. Activate with: source .venv/bin/activate"
	@echo "   Or run directly:     uv run bisync --help"

## ── uTools plugin ────────────────────────────────────────────────────

# Regenerate utools/logo.png (stdlib-only, no Pillow required)
utools-logo:
	$(UV) run python utools/make_logo.py

# Install uTools plugin Node dependencies
utools-install:
	cd utools && npm install

# Build uTools plugin (outputs to utools/dist/)
utools-build: utools-install
	cd utools && npm run build

# Start Vite dev server for uTools plugin
utools-dev:
	cd utools && npm run dev

## ── Utilities ────────────────────────────────────────────────────────

clean:
	rm -rf build/ dist/ *.egg-info .venv/
	find . -name "__pycache__" -type d -exec rm -rf {} + 2>/dev/null || true
	@echo "✅  Cleaned"
