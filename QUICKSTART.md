# Quick Start

## Installation

```bash
# Validate the plugin
claude plugins validate /path/to/llm-context-decision

# Install dependencies (Python MCP server)
cd server && uv sync
```

## First Time in a Project

```bash
# Scan the project to build the dependency graph
/scan

# View the project structure
/map

# See statistics
```

Output: Creates `.claude/context/graph.db` with all functions, classes, and dependencies.

## Typical Workflow

### 1. Ask about code
```
"Add authentication to the login API endpoint"
```

**What happens:**
- `/optimize` skill auto-activates
- Plugin finds files related to "login", "auth", "API"
- Sends only relevant files instead of entire codebase
- **Result:** 10-50x fewer tokens

### 2. Check impact before changes
```bash
/context src/api/auth.ts
```

**Output:**
- Files affected if you change this file
- Tests covering this code
- Uncovered functions
- Token estimate

### 3. Route simple tasks to cheap models
```bash
/delegate "format this code with prettier"
```

**Result:** Routes to Haiku (10x cheaper than Opus)

## Common Tasks

### Find where a function is called
```bash
/map authenticate
```

### Understand a module
```bash
/delegate "explain what src/auth/jwt.ts does"
→ Routes to Sonnet (balanced cost)
```

### See test coverage
```bash
/context src/auth/middleware.ts
→ Shows "Uncovered Functions" section
```

### Update the graph after changes
The graph auto-updates via git hooks when you save files. Manual update:
```bash
/scan
```

## Tips

1. **First task is always `/scan`** — builds the dependency graph that powers everything else
2. **Let `/optimize` work for you** — just write natural coding prompts, it auto-selects context
3. **Use `/delegate` for non-coding tasks** — documentation, formatting, explanations = cheaper models
4. **Run `/context` before major refactors** — see what breaks if you change something
5. **`.code-contextignore` file** — add patterns just like `.gitignore` to exclude directories

## Token Savings Example

Without plugin:
```
- Files in codebase: 47
- Average tokens per file: 2,000
- Context sent to Claude: ~94,000 tokens (full codebase)
- Cost: $2.82 with Opus
```

With plugin:
```
- Task: "Add rate limiting to auth middleware"
- Relevant files found: 3 (auth/middleware, auth/types, config)
- Context sent: ~850 tokens
- Cost: $0.04 with Opus
- Savings: 98% fewer tokens, 70x cheaper
```

## Troubleshooting

### "No such file or directory: .claude/context/graph.db"
→ Run `/scan` first

### "No relevant files found"
→ Run `/scan` again to update the graph
→ Or be more specific in your task description

### MCP server doesn't start
→ Run `cd server && uv sync` to install dependencies
→ Check `ANTHROPIC_API_KEY` is set (for `/delegate` to work)

## Next Steps

- Read the [full README](README.md) for detailed documentation
- Check the [plan](../.claude/plans/calm-snacking-lighthouse.md) for architecture
- Explore the [skills](skills/) to understand what each does
