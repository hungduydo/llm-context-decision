#!/usr/bin/env bash
# Incremental graph update — triggered by PostToolUse hook after file writes.
# Only re-scans if the graph database exists (project has been scanned before).

set -euo pipefail

CONTEXT_DIR=".claude/context"
GRAPH_DB="$CONTEXT_DIR/graph.db"

# Only run if graph exists (project has been scanned)
if [ ! -f "$GRAPH_DB" ]; then
    exit 0
fi

# Check if the MCP server is available
if ! command -v uv &>/dev/null; then
    exit 0
fi

# Run incremental scan via the MCP server's scan_project tool
# This is lightweight — it only re-parses files whose SHA-256 hash has changed
cd "$(git rev-parse --show-toplevel 2>/dev/null || pwd)"
uv run --directory "$(dirname "$0")/../server" python -c "
from context_server.server import scan_project
print(scan_project())
" 2>/dev/null || true
