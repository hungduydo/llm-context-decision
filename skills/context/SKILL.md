---
name: context
description: >
  Show the blast radius and dependency graph for a specific file or set of files.
  Displays all affected dependents, test coverage, and token estimates.
  Use when the user wants to understand the impact of changing specific files.
allowed-tools: mcp__context_server__get_blast_radius, mcp__context_server__query_graph, mcp__context_server__get_review_context
argument-hint: "<file_path> [file_path2...]"
---

# Blast Radius Viewer

Show the impact radius of changing specific files.

## Steps

1. Parse `$ARGUMENTS` to get file path(s)
2. Call `get_blast_radius` with the file paths
3. Show the structural summary including:
   - Changed files with their function signatures
   - All affected dependent files
   - Test files that cover the changed code
   - Uncovered functions (no tests detected)
   - Token estimate for the full context
4. Optionally use `query_graph` to show callers/callees for specific functions

## Output

Present a clear blast radius report showing:
- What files would be affected by changes
- Which tests cover the changed code
- Where test gaps exist
- How many tokens the full context would cost
