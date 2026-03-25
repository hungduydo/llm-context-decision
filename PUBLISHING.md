# Publishing Guide — llm-context-decision Plugin

A step-by-step checklist to publish this plugin to the Claude Code marketplace.

---

## 1. Pre-flight Checklist

### 1.1 Update Author Info

Replace placeholder values in `.claude-plugin/marketplace.json`:

```json
"owner": {
  "name": "YOUR_GITHUB_USERNAME",
  "email": "your@email.com"
}
```

And in `.claude-plugin/plugin.json`:

```json
"author": {
  "name": "YOUR_GITHUB_USERNAME",
  "url": "https://github.com/YOUR_GITHUB_USERNAME"
}
```

---

### 1.2 Add a LICENSE File

The README mentions MIT but there is no `LICENSE` file. Create one:

```bash
curl -s https://choosealicense.com/licenses/mit/ \
  | sed -n 's/.*<pre id="license-text">\(.*\)<\/pre>.*/\1/p' \
  | sed 's/\[year\]/2025/; s/\[fullname\]/YOUR_NAME/'
```

Or just create `LICENSE` manually with the MIT text and your name/year.

---

### 1.3 Fix the Cross-Platform `uv` Path

The current `.mcp.json` uses a hardcoded macOS Homebrew path:

```json
"command": "/opt/homebrew/bin/uv"
```

This breaks on Linux and Windows. Two options:

**Option A — Document it** (simplest): Tell users in README to replace with their own `uv` path. Add a setup script:

```bash
# scripts/install.sh
UVX_PATH=$(which uv)
sed -i '' "s|/opt/homebrew/bin/uv|$UVX_PATH|g" .mcp.json
echo "Updated .mcp.json with uv path: $UVX_PATH"
```

**Option B — Use `uvx` entrypoint** (recommended if supported by Claude Code):

```json
{
  "mcpServers": {
    "context_server": {
      "type": "stdio",
      "command": "uvx",
      "args": ["--from", ".", "context-server"],
      "cwd": "server"
    }
  }
}
```

Currently Option A is safer — document the known limitation in README.

---

### 1.4 Verify All Skills Load

Run through each skill manually before publishing:

```
/scan                          → should build .claude/context/graph.db
/map                           → should show project tree + stats
/context src/index.js          → should show blast radius
/delegate explain the auth flow → should route to Sonnet
/usage on                      → should enable tracking
/usage show                    → should show log (after /delegate call)
```

---

### 1.5 Verify MCP Server Starts

```bash
# Test the server starts without errors
/opt/homebrew/bin/uv run --directory server context-server &
sleep 2 && kill %1
# Expected: process starts (no ENOENT or import errors), killed with SIGTERM
```

---

## 2. GitHub Repository Setup

### 2.1 Create the Repository

```bash
gh repo create llm-context-decision \
  --public \
  --description "Claude Code plugin: smart context selection + tiered model routing (Haiku/Sonnet/Opus)" \
  --clone=false
```

### 2.2 Push Code

```bash
cd /Users/user/Documents/workspace/Personal/llm-context-decision
git init
git add .
git commit -m "Initial release: v1.0.0"
git remote add origin https://github.com/YOUR_USERNAME/llm-context-decision.git
git push -u origin main
```

### 2.3 Create a Release Tag

```bash
git tag -a v1.0.0 -m "Initial release"
git push origin v1.0.0
```

Then create a GitHub release via:

```bash
gh release create v1.0.0 \
  --title "v1.0.0 — Initial Release" \
  --notes "Multi-LLM orchestration with Tree-sitter AST context selection."
```

---

## 3. Plugin Submission

### 3.1 Claude Code Marketplace (Official Channel)

Submit via the Claude Code CLI in your project directory:

```bash
claude plugins marketplace publish
```

This reads `.claude-plugin/marketplace.json` and submits to the marketplace registry. The review process is manual — expect 1-5 business days.

### 3.2 Alternative — Share Directly

Users can install directly from GitHub without marketplace approval:

```bash
# User installs from your GitHub repo
claude plugins add https://github.com/YOUR_USERNAME/llm-context-decision
```

Or manually: user clones the repo and adds it as a local plugin in their Claude Code settings.

---

## 4. README Improvements Before Publishing

The current README is solid but add these sections:

### Add: Requirements Section

```markdown
## Requirements

- Claude Code ≥ 1.x
- Python ≥ 3.11
- [uv](https://docs.astral.sh/uv/) package manager
- `ANTHROPIC_API_KEY` in environment (required for `/delegate` only)
```

### Add: Platform Notes

```markdown
## Platform Notes

**macOS (Homebrew):** The default `.mcp.json` uses `/opt/homebrew/bin/uv`.
Run `scripts/install.sh` to auto-detect your `uv` path.

**Linux / Windows:** Replace `/opt/homebrew/bin/uv` in `.mcp.json`
with the output of `which uv` (Linux) or `where uv` (Windows).
```

### Add: Troubleshooting — MCP Server Failed

```markdown
### MCP server shows "✘ failed" in Claude Code

This is almost always a PATH issue. GUI apps launch with a restricted PATH.

1. Find your uv path: `which uv`
2. Edit `.mcp.json` → replace `"command"` value with the full path
3. Restart Claude Code
```

---

## 5. Post-Publish Tasks

- [ ] Add `claude-code-plugin` topic to GitHub repo
- [ ] Post to Claude community Discord / forum
- [ ] Add a demo GIF to README (`/scan` + `/delegate` in action)
- [ ] Set up GitHub Actions to run `uv sync && python -c "from context_server.server import *"` on PRs

---

## 6. Known Limitations to Document

| Limitation | Workaround |
|---|---|
| `uv` path is hardcoded for macOS Homebrew | Run `scripts/install.sh` after cloning |
| `/delegate` is single-turn (multi-turn in progress) | Use `/delegate` again with follow-up task |
| Tree-sitter only supports Python, JS, TS | Other languages fall back to regex parsing |
| `ANTHROPIC_API_KEY` required for delegation | Without it, `/map`, `/scan`, `/context` still work |
