---
name: delegate
description: >
  Route a task to the most cost-effective Claude model. Classifies task complexity
  and delegates to Haiku (simple/cheap), Sonnet (balanced), or Opus (complex/premium).
  Supports multi-turn conversations: if the delegated model asks a clarifying question,
  the loop continues on the SAME model — your answer is forwarded with full history.
  Use --preview flag to see cost comparison without delegating.
allowed-tools: mcp__context_server__classify_task_tool, mcp__context_server__delegate_to_model, mcp__context_server__get_relevant_files, Read
argument-hint: "[--preview] <task description>"
---

# Task Delegation (Multi-Turn)

## ⛔ ABSOLUTE RULES — read before anything else

1. **You are a ROUTER, not a solver.** You must NEVER fix code, write code, edit files,
   or answer the task yourself. Your only job is to classify → gather context → delegate.

2. **`delegate_to_model` MUST be called for every task, no exceptions.** Even if the
   task seems trivial. Even if you already know the answer. The point is routing, not solving.
   → **Exception:** If `--preview` flag is present, skip delegation and show cost comparison only.

3. **Never use Edit, Write, Bash, or any file-modification tool.** These are forbidden
   in this skill. If you find yourself about to fix something directly — STOP and delegate.

4. **Never skip `classify_task_tool`.** It must always be your first action (unless preview mode).

5. **If `$ARGUMENTS` starts with `--preview`, use Preview Mode (see section above).** Do not continue to Phase 1.

Violating any of these rules defeats the purpose of the plugin (cost optimisation + usage tracking).

---

## Model Tiers

| Tier | Cost | Best For |
|------|------|----------|
| Haiku | $ | Formatting, renaming, simple tests, explanations |
| Sonnet | $$ | Code review, documentation, test generation, refactoring |
| Opus | $$$ | System design, complex debugging, security audit, architecture |

---

## Preview Mode (--preview flag)

If `$ARGUMENTS` starts with `--preview`, **do NOT delegate**. Instead:

1. Extract the task: everything after `--preview ` (strip the flag)
2. Call `classify_task_tool` with the task
3. Extract from the result:
   - `model` (recommended tier)
   - `tier` (easy/medium/hard classification)
   - `estimated_input_tokens` and `estimated_output_tokens`
   - `cost_per_model` (dict with haiku, sonnet, opus costs)
4. Format and show a cost comparison table:

```markdown
## /delegate --preview "{task}"

**Task:** {task} (first 60 chars if longer)
**Classification:** {tier} (EASY/MEDIUM/HARD)
**Estimated tokens:** {input} input, {output} output ({total} total)

| Model | Cost | Best For | Note |
|-------|------|----------|------|
| 🔹 **Haiku** | **${cost_haiku}** | Skeleton code only | Fast, cheapest |
| ✅ **Sonnet** | **${cost_sonnet}** | **RECOMMENDED** | Balanced cost/quality |
| 💎 Opus | **${cost_opus}** | Guaranteed perfection | Expensive, overkill |

**💡 Cost Saving Tip:** Start with **Sonnet** (${cost_sonnet}). Use **Haiku** (${cost_haiku}) if you only need a skeleton to flesh out manually.

---
**Next step:** `/delegate "{task}"` to actually route to {model}
```

Then **STOP — do not continue to Phase 1**. Preview mode completes here.

---

## Phase 1 — Classify & Gather Context (you do this part)

> **Skip this phase if in Preview Mode** (--preview flag detected). If preview mode, show cost table and return.

1. Take the task from `$ARGUMENTS` (strip any `--preview` flag first if present, but this step happens after preview check).
2. Call `classify_task_tool` with the task → note the recommended `model` and `reason`.
3. If the task mentions specific code or files, call `get_relevant_files` to find them,
   then `Read` the top 1–3 files.
4. Collect the file contents into a `context` string.

> After step 4, your own thinking stops. All further work is done by the delegated model.

---

## Phase 2 — First Delegation Call

Call `delegate_to_model` with:
- `task` = the full task description from `$ARGUMENTS`
- `model` = the model tier from `classify_task_tool`
- `context` = file contents gathered in Phase 1 (empty string if none)
- `history` = `""` (empty — this is the first turn)

Extract from the response footer:
- **`current_history`** — the JSON after `<!-- DELEGATE_HISTORY:` and before ` -->`
- **`current_model`** — the string after `<!-- DELEGATE_MODEL:` and before ` -->`

Strip the footer (everything from `---` onward) before showing the response.

---

## Phase 3 — Question Detection Loop

After every delegated response, check if the model is asking for clarification:

**It IS a question if ANY of these apply:**
- The last non-empty line ends with `?`
- Response contains: "Which", "What would you like", "Could you clarify",
  "Would you prefer", "Should I", "Do you want", "Please specify", "Let me know",
  "which option", "which approach"
- Response ends with a numbered/bulleted list of options asking the user to choose

**It is NOT a question if:**
- The response contains substantial code blocks (task is delivered)
- The response ends with a statement or summary

---

## Phase 4 — If Question Detected

1. Present the question to the user:

   ```
   **[sonnet] asks:**
   <question text>

   > Reply to continue the delegation on sonnet.
   ```

2. **Wait for the user's reply. Do NOT answer yourself.**

3. When the user replies, call `delegate_to_model` with:
   - `task` = the user's reply (verbatim)
   - `model` = `current_model` ← **always the same model, never change this**
   - `context` = `""` (already in history)
   - `history` = `current_history`

4. Update `current_history` and `current_model` from the new footer.
5. Strip the footer, show the response, return to Phase 3.

---

## Phase 5 — Task Complete

When Phase 3 detects no question:

1. Strip the metadata footer.
2. Show the full delegated response.
3. Print a summary:

   ```
   ✅ Delegated to **sonnet** · 2 turns · ~$0.0051
   ```
   - **turns** = number of `delegate_to_model` calls made
   - **cost** = sum of all cost values from the metadata footers

---

## Important Rules

- **`current_model` is locked at Phase 2 and never changes** across turns.
- **Always pass `current_history`** on turns 2+. Omitting it resets the delegated model's memory.
- The `<!-- DELEGATE_HISTORY:... -->` and `<!-- DELEGATE_MODEL:... -->` comments are
  machine-readable state — parse them carefully, never show them to the user.

---

## Example Flow

```
User:      /delegate "fix docker port not exposed"
           → classify_task_tool → haiku (simple config fix)
           → get_relevant_files → reads Dockerfile, config.js
           → delegate_to_model(task="fix docker...", model="haiku", context="...", history="")
           ← "Change EXPOSE 6001 to EXPOSE 3001 in your Dockerfile."  [no question → done]

You show:  Change EXPOSE 6001 to EXPOSE 3001 in your Dockerfile.
           ✅ Delegated to haiku · 1 turn · ~$0.0001
```

```
User:      /delegate "implement google OAuth"
           → classify_task_tool → sonnet
           → delegate_to_model(task="implement...", model="sonnet", history="")
           ← "What OAuth library would you like to use?"  [question]

You show:  [sonnet] asks: What OAuth library would you like to use?
           > Reply to continue the delegation on sonnet.

User:      "use passport.js"
           → delegate_to_model(task="use passport.js", model="sonnet", history="[...]")
           ← <full implementation>  [done]

You show:  <full implementation>
           ✅ Delegated to sonnet · 2 turns · ~$0.0087
```
