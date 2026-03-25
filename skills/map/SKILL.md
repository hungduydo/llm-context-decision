---
name: map
description: >
  Display the project map and dependency graph. Shows the project tree structure,
  graph statistics, and allows querying the dependency graph.
  Use when the user wants to understand project structure or find specific code.
allowed-tools: mcp__context_server__get_project_map, mcp__context_server__get_stats, mcp__context_server__query_graph
argument-hint: "[search_term]"
---

# Project Map

View the project structure and query the code dependency graph.

## Steps

1. Show the project tree using `get_project_map`
2. Show graph statistics using `get_stats`
3. If `$ARGUMENTS` is provided, search the graph for matching nodes using `query_graph` with query_type "search"

## Output

Present a clear overview of:
- Project directory structure (tree view)
- Code entity counts (functions, classes, modules)
- Relationship counts (imports, calls, inheritance)
- Search results if a search term was provided
