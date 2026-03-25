---
name: usage
description: >
  Toggle usage tracking for the llm-context-decision plugin. When ON, every
  delegate_to_model and classify_task_tool call is logged to
  .claude/context/debug.log with the model chosen, token breakdown,
  estimated USD cost, and duration. Use: /usage [on|off|show|clear]
allowed-tools: mcp__context_server__toggle_debug, mcp__context_server__get_debug_log
argument-hint: "[on|off|show|clear]"
---

# Plugin Usage Tracking

View real-time stats on which model was used, how many tokens were consumed,
and the estimated cost for every prompt routed through the plugin.

## Arguments

| Argument | Action |
|----------|--------|
| `on` | Enable debug mode — start logging all tool calls |
| `off` | Disable debug mode — stop logging (existing log preserved) |
| `show` | Display the last 10 log entries + session summary _(default)_ |
| `clear` | Show the log, then wipe it |
| _(none)_ | Same as `show` |

## Steps

1. Parse `$ARGUMENTS` (trim whitespace, lowercase).

2. **`on`** → call `toggle_debug(enable=true)`, show the confirmation message.

3. **`off`** → call `toggle_debug(enable=false)`, show the confirmation message.

4. **`clear`** → call `get_debug_log(last_n=20, clear=true)`, show the report,
   then confirm the log was cleared.

5. **`show`** or no argument → call `get_debug_log(last_n=10)`, display the report.

## Output

The report includes:

- A table of recent calls: timestamp · tool · model · tokens in · tokens out · cost · duration
- A session summary: total API calls, total tokens (input + output), total cost, unique context files
- Detail on the most recent delegation: task preview, model chosen, classification reason

### Example

```
## Debug Mode: 🟢 ON  ·  4 recorded entries

| # | Time     | Tool              | Model  | Tokens In | Tokens Out | Cost    | Duration |
|---|----------|-------------------|--------|----------:|----------:|---------|----------|
| 4 | 10:35:02 | delegate_to_model | sonnet |       850 |       312 | $0.0035 |  2,340ms |
| 3 | 10:33:44 | classify_task_tool| —      |         — |         — | $0      |      2ms |
| 2 | 10:31:10 | delegate_to_model | haiku  |       420 |       180 | $0.0005 |    890ms |
| 1 | 10:28:30 | delegate_to_model | opus   |     2,100 |       890 | $0.0980 |  5,200ms |

### Session Summary
- **Total API calls:** 3  (haiku×1, sonnet×1, opus×1)
- **Total tokens:** 4,752  (input: 3,370 | output: 1,382)
- **Total cost:** ~$0.1020
- **Unique context files sent:** 5
```

## Notes

- The log persists across Claude Code sessions in `.claude/context/debug.log`
- Debug mode state persists via `.claude/context/debug.enabled` flag file
- Turning debug OFF does **not** clear the log; use `/usage clear` for that
- `classify_task_tool` entries always show `$0` cost — they use the local keyword
  classifier with no API call
