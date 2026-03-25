# llm-context-decision

A Claude Code plugin that optimizes AI-assisted development by intelligently routing tasks to the right Claude model tier and sending only the minimal necessary context.

## Features

### 🔍 Smart Context Selection
- **Tree-sitter AST parsing** across Python, TypeScript, and JavaScript
- **Dependency graph** stored in SQLite (`.claude/context/graph.db`)
- **Blast radius analysis** — understand which files are affected by a change
- **5-50x token reduction** by sending only relevant code instead of the entire codebase

### 🎯 Tiered Model Routing
- **Haiku** ($) — Simple tasks: formatting, renaming, explanations
- **Sonnet** ($$) — Balanced: code review, documentation, test generation
- **Opus** ($$$) — Complex: system design, security audits, multi-file refactors

### 🚀 Auto-Optimization
- `/optimize` skill automatically selects relevant context for coding tasks
- Incremental graph updates on file changes (via git hooks)
- `/delegate` routes simple tasks to cheaper models automatically

## Requirements

- Claude Code ≥ 1.x
- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/) package manager (`brew install uv` on macOS)

**Optional:** `ANTHROPIC_API_KEY` (only needed for `/delegate` to route tasks to cheaper models)

## Installation

### 1. Install the Plugin

Run these slash commands inside Claude Code chat:

```
/plugin marketplace add https://github.com/hungduydo/llm-context-decision
/plugin install llm-context-decision@hungduydo-llm-context-decision
```

Or use the interactive UI (`/plugin` → Discover tab).

To install locally from a clone:

```bash
git clone https://github.com/hungduydo/llm-context-decision
cd llm-context-decision
claude plugins validate .
```

### 2. Set Up MCP Server

```bash
cd server && uv sync
```

### 3. Fix `uv` Path (macOS Homebrew)

The `.mcp.json` uses the Homebrew `uv` path by default. If your `uv` is elsewhere, run:

```bash
# Auto-detect and update .mcp.json
sed -i '' "s|/opt/homebrew/bin/uv|$(which uv)|g" .mcp.json
```

> On Linux: use `sed -i` (no `''`). On Windows: edit `.mcp.json` manually and set `"command"` to the output of `where uv`.

The MCP server is configured in `.mcp.json` to run via `uv` when Claude Code starts.

### 3. First Run

In any project:

```bash
/scan
```

This will:
- Walk your project directory (respecting `.gitignore`)
- Parse all Python/TypeScript/JavaScript files with Tree-sitter
- Build a dependency graph in `.claude/context/graph.db`
- Store incremental state for fast updates

## Usage

### View Project Structure

```bash
/map
```

Shows the project tree and graph statistics (nodes, edges, dependencies).

### Find Blast Radius

Before making changes, see what's affected:

```bash
/context src/auth/middleware.ts
```

Shows:
- All files that depend on this file
- Test coverage
- Uncovered functions
- Token estimate

### Get Optimized Context

The `/optimize` skill auto-activates when you ask about code:

```
User: "Add rate limiting to the auth middleware"
→ Plugin auto-computes blast radius for src/auth/middleware.ts
→ Sends only relevant context to Claude (3 files instead of 50)
→ 17x token reduction
```

### Delegate to Cheaper Models (Optional)

```bash
/delegate "format this file according to prettier"
```

Routes tasks to the most cost-effective Claude model:
- **Haiku** — Simple tasks (10x cheaper than Opus)
- **Sonnet** — Balanced tasks
- **Opus** — Complex tasks (only when needed)

> **Requires `ANTHROPIC_API_KEY`** (skip this skill if you don't have one)

## How It Works

### Phase 1: Scan
```
Tree-sitter AST parsing → Extract functions, classes, imports
↓
SQLite graph storage (nodes, edges)
↓
.claude/context/graph.db created
```

### Phase 2: Blast Radius
```
User mentions a file → Graph query
↓
Find all files importing it (direct dependents)
↓
Find files importing those files (transitive dependents)
↓
Find tests that cover the changed code
↓
Structural summary instead of full code
```

### Phase 3: Context Injection
```
User writes coding prompt
↓
/optimize skill auto-activates (if graph exists)
↓
Extract keywords from prompt
↓
Find relevant files via graph search
↓
Include only relevant file content + structural summary
↓
Send to Claude with 5-50x fewer tokens
```

### Phase 4: Model Delegation
```
User asks to /delegate a task
↓
classify_task_tool analyzes complexity
↓
Route to Haiku/Sonnet/Opus
↓
MCP server calls Anthropic API with chosen model
↓
Show result (10-100x cheaper than Opus for simple tasks)
```

## MCP Tools

The embedded Python MCP server provides 9 tools:

| Tool | Purpose |
|------|---------|
| `scan_project` | Full Tree-sitter parse → build/update graph |
| `get_blast_radius` | Trace impact of changing specific files |
| `get_relevant_files` | Find files related to a task |
| `get_review_context` | Structural summary (functions, deps, tests) |
| `query_graph` | Direct graph queries (callers, callees, imports) |
| `classify_task_tool` | Recommend model tier (haiku/sonnet/opus) |
| `delegate_to_model` | Call Anthropic API with chosen model |
| `get_project_map` | Tree view of project structure |
| `get_stats` | Graph statistics (nodes, edges, token estimates) |

## Skills

- **/scan** — Scan project and build dependency graph
- **/map** — View project structure and graph statistics
- **/context \<file\>** — Show blast radius for a file
- **/delegate \<task\>** — Route task to optimal Claude model
- **optimize** (auto) — Auto-optimize context for coding tasks

## Configuration

### Per-Project Settings

Create `.claude/context/config.json`:

```json
{
  "dependency_depth": 2,
  "max_file_size_kb": 100,
  "ignore_patterns": [
    "node_modules/",
    "__pycache__/",
    ".git/"
  ]
}
```

### Ignore Patterns

Create `.code-contextignore` in project root (like `.gitignore`):

```
vendor/
dist/
*.min.js
*.lock
```

## Performance

- **First scan**: ~1-2s for typical projects (100-500 files)
- **Incremental updates**: <100ms (only changed files re-parsed)
- **Token reduction**: 5-50x for most coding tasks (example: 15KB → 300B)

## Limitations

- Supported languages: Python, TypeScript, JavaScript (Go/Java/Rust coming)
- Call graph may miss dynamic imports (e.g., `require(variable)`)
- Test detection heuristic-based (looks for `test_` prefix, `.test.` patterns)

## Future Enhancements

- [ ] Support for more languages (Go, Java, Rust, C#)
- [ ] Semantic code search via embeddings
- [ ] Test coverage analysis
- [ ] Automatic API documentation generation
- [ ] Performance profiling recommendations
- [ ] Security vulnerability detection

## Troubleshooting

**MCP server shows `✘ failed` in Claude Code**

GUI apps launch with a restricted `PATH` that doesn't include Homebrew paths. Fix:
```bash
# Find your uv path and update .mcp.json
sed -i '' "s|/opt/homebrew/bin/uv|$(which uv)|g" .mcp.json
# Restart Claude Code
```

**`/delegate` runs on current model instead of routing**

The skill must call `delegate_to_model` — ensure the MCP server is connected (`✔` in Claude Code's Built-in MCPs list). If it shows `✘ failed`, fix the `uv` path above first.

**`/delegate` not working**

`/delegate` requires `ANTHROPIC_API_KEY` to route tasks to Claude models. Set it:
```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

The other skills (`/scan`, `/map`, `/context`, `/usage`) work without it — they only analyze your local codebase.

## License

MIT — see [LICENSE](LICENSE)

## Contributing

Improvements welcome — [open an issue](https://github.com/hungduydo/llm-context-decision/issues) or submit a PR. Key areas:

1. Add support for more languages in `server/src/context_server/parser.py`
2. Enhance test detection heuristics
3. Optimize import resolution for aliases (`tsconfig.json` paths, Python `sys.path`)
4. Add semantic search via vector embeddings
