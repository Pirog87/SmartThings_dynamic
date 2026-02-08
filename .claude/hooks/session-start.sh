#!/bin/bash
set -euo pipefail

# Only run in remote (Claude Code on the web) environment
if [ "${CLAUDE_CODE_REMOTE:-}" != "true" ]; then
  exit 0
fi

cd "$CLAUDE_PROJECT_DIR"

# Install dev dependencies (pytest, ruff, etc.)
pip install -e ".[dev]" --quiet
