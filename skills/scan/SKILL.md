---
name: scan
description: >
  Scan the current project with Tree-sitter AST parsing and build a dependency graph.
  Creates .claude/context/graph.db with all functions, classes, imports, and their relationships.
  Use when starting work on a project or when major file changes have occurred.
allowed-tools: mcp__context_server__scan_project, mcp__context_server__get_stats, mcp__context_server__get_project_map
argument-hint: "[project_path]"
---

# Project Scanner

Scan the project to build a code dependency graph for context optimization.

## Steps

1. Call the `scan_project` tool to parse all source files with Tree-sitter
2. The tool will:
   - Walk the project directory (respecting .gitignore)
   - Parse Python, TypeScript, and JavaScript files
   - Extract functions, classes, imports, and call relationships
   - Store everything in `.claude/context/graph.db`
   - Use incremental updates (only re-parse changed files)
3. After scanning, show the graph statistics using `get_stats`
4. Optionally show the project map using `get_project_map`

## Arguments

If `$ARGUMENTS` is provided, use it as the project path. Otherwise scan the current directory.

## Output

Show a summary including:
- Number of files scanned
- Number of functions, classes, and relationships found
- Any parse errors encountered
- The project tree structure
