---
name: refine
description: >
  Optimize a rough prompt into a specific, context-rich version with relevant
  files injected. Takes a vague ask ("fix the bug") and rewrites it with exact
  file paths, function names, and constraints from the codebase. Shows model
  recommendation and estimated cost. Use before /delegate for best results.
allowed-tools: mcp__context_server__classify_task_tool, mcp__context_server__get_relevant_files, Read
argument-hint: "<rough prompt>"
---

# Prompt Refiner

Turn a vague prompt into a specific, actionable one enriched with real code context.

## Steps

1. **Take the rough prompt** from `$ARGUMENTS`

2. **Classify the task** — call `classify_task_tool` with the prompt:
   - Note: `model`, `tier`, `reason`, `cost_per_model`

3. **Find relevant files** — call `get_relevant_files` with:
   - `task_description` = the rough prompt
   - `max_files` = 5
   - If the result contains "Error" or "No graph database" → skip to step 5 (fallback mode)

4. **Read the top 1–2 files** (highest score from step 3):
   - Look for: specific function names, line numbers, variable names, test file references
   - Note any test files found (to add "don't break X" constraints)

5. **Rewrite the prompt** — incorporate everything found:
   - Replace vague verbs with specific ones: "fix" → "correct the condition at line X in `func()`"
   - Add exact file paths: "In `src/auth/middleware.ts`..."
   - Add function/class names from signatures: "the `validateToken()` function"
   - Add line numbers if visible from reading: "(line 47)"
   - Add test constraints if test files found: "without breaking `tests/auth.test.ts`"
   - Keep the rewritten prompt under ~150 words — specific but not bloated

6. **Output the result** in this format:

```markdown
## Refined Prompt

**Original:** {original_prompt}

**Optimized:**
{rewritten_prompt — specific, file-aware, action-oriented}

---
**Files included ({N} files, ~{total_tokens} tokens):**
- `path/to/file.ts` — {top 2-3 function signatures}
- `path/to/test.ts` — {test coverage note}

**Model recommendation:** {model} · Est. ${cost_per_model[model]} ({reason})

**Next step:** `/delegate "{optimized_prompt}"`
```

## Fallback (no graph.db or no files found)

If `get_relevant_files` returns an error or empty result, skip file context and still improve the prompt using language analysis only:
- Make the action more specific ("fix" → "identify and fix the root cause of")
- Add constraints ("without changing the public API")
- Clarify the expected outcome ("so that X works correctly")

Show the output without the "Files included" section, and add a note:
```
> No project graph found. Run `/scan` first for file-aware prompt optimization.
```

## Example

**Input:** `/refine "fix the login bug"`

**Output:**
```markdown
## Refined Prompt

**Original:** fix the login bug

**Optimized:**
In `src/auth/middleware.ts`, the `validateToken()` function is failing
JWT validation. Check the token expiry comparison — it likely uses
`Date.now()` instead of `Date.now() / 1000`. Correct the condition
without breaking the tests in `tests/auth/middleware.test.ts`.

---
**Files included (2 files, ~620 tokens):**
- `src/auth/middleware.ts` — validateToken(), checkExpiry(), refreshToken()
- `tests/auth/middleware.test.ts` — 4 test cases covering token validation

**Model recommendation:** haiku · Est. $0.0021 (Matched keywords: fix)

**Next step:** `/delegate "In src/auth/middleware.ts, the validateToken()..."`
```
