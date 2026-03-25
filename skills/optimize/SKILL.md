---
name: optimize
description: >
  Automatically optimize coding prompts by selecting relevant context from the
  project dependency graph. When the user asks to modify, debug, or understand code
  and .claude/context/graph.db exists, compute the blast radius and inject only
  relevant file context. This reduces token usage by 5-50x compared to sending
  the full codebase. Triggers on coding tasks that mention specific files, modules,
  or features.
user-invocable: false
allowed-tools: Read, mcp__context_server__get_blast_radius, mcp__context_server__get_relevant_files, mcp__context_server__get_review_context
---

# Context Optimizer

Automatically provide optimized context for coding tasks.

## When to Activate

Activate when ALL of these are true:
- The user is asking about modifying, debugging, or understanding code
- The file `.claude/context/graph.db` exists (project has been scanned)
- The user mentions specific files, modules, functions, or features

## Steps

1. **Identify target files**: Extract file paths or feature keywords from the user's request

2. **If specific files are mentioned**:
   - Use `get_blast_radius` with those file paths to find all affected files
   - Use `get_review_context` to get a structural summary

3. **If no specific files, but a feature/topic is mentioned**:
   - Use `get_relevant_files` with the task description to find related files
   - Read only the top-scoring files

4. **Provide context to Claude**:
   - Include the structural summary (signatures, dependencies, test coverage)
   - Only read full file contents for the most relevant 2-3 files
   - Skip reading files that are only tangentially related

## Key Principle

Send the **minimum context** needed. A structural summary with function signatures
is often enough for Claude to understand the codebase without reading every line.
Full file content should only be read for files being directly modified.
