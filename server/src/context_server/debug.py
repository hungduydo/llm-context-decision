"""Debug logging module for llm-context-decision plugin.

Writes structured JSONL entries to .claude/context/debug.log when debug mode is ON.
Debug mode is toggled by the presence of .claude/context/debug.enabled flag file.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# Pricing table (USD per million tokens, as of 2026-03)
# ---------------------------------------------------------------------------
_PRICING: dict[str, dict[str, float]] = {
    "haiku": {"input": 0.80, "output": 4.00},
    "sonnet": {"input": 3.00, "output": 15.00},
    "opus": {"input": 15.00, "output": 75.00},
}


def _ctx_dir(project_root: str) -> Path:
    return Path(project_root) / ".claude" / "context"


def _log_path(project_root: str) -> Path:
    return _ctx_dir(project_root) / "debug.log"


def _flag_path(project_root: str) -> Path:
    return _ctx_dir(project_root) / "debug.enabled"


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------


def is_debug_enabled(project_root: str) -> bool:
    """Return True if the debug.enabled flag file exists."""
    return _flag_path(project_root).exists()


def enable_debug(project_root: str) -> None:
    """Create the debug.enabled flag file (enables debug mode)."""
    d = _ctx_dir(project_root)
    d.mkdir(parents=True, exist_ok=True)
    _flag_path(project_root).touch()


def disable_debug(project_root: str) -> None:
    """Remove the debug.enabled flag file (disables debug mode)."""
    p = _flag_path(project_root)
    if p.exists():
        p.unlink()


def log_entry(project_root: str, entry: dict) -> None:
    """Append one JSON line to debug.log. No-op if debug mode is OFF."""
    if not is_debug_enabled(project_root):
        return
    d = _ctx_dir(project_root)
    d.mkdir(parents=True, exist_ok=True)
    with _log_path(project_root).open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def read_log(project_root: str, last_n: int = 20) -> list[dict]:
    """Read the last N entries from debug.log."""
    p = _log_path(project_root)
    if not p.exists():
        return []
    lines = p.read_text(encoding="utf-8").splitlines()
    entries: list[dict] = []
    for line in lines:
        line = line.strip()
        if not line:
            continue
        try:
            entries.append(json.loads(line))
        except json.JSONDecodeError:
            pass
    return entries[-last_n:]


def clear_log(project_root: str) -> None:
    """Truncate debug.log to empty."""
    p = _log_path(project_root)
    if p.exists():
        p.write_text("", encoding="utf-8")


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Compute estimated USD cost from token counts."""
    tier = model.lower()
    # Normalize aliases (e.g. "claude-haiku-..." → "haiku")
    for key in _PRICING:
        if key in tier:
            tier = key
            break
    pricing = _PRICING.get(tier, _PRICING["sonnet"])
    cost = (input_tokens / 1_000_000) * pricing["input"]
    cost += (output_tokens / 1_000_000) * pricing["output"]
    return round(cost, 6)


def now_iso() -> str:
    """Return current UTC timestamp in ISO-8601 format."""
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# ---------------------------------------------------------------------------
# Report formatter
# ---------------------------------------------------------------------------


def format_debug_report(entries: list[dict], debug_on: bool) -> str:
    """Render debug log entries as a markdown table + session summary."""
    status_label = "🟢 ON" if debug_on else "🔴 OFF"

    if not entries:
        return (
            f"## Debug Mode: {status_label}\n\n"
            "_No entries in debug log._\n\n"
            "Run `/debug on` to start recording, then use `/delegate` to see stats."
        )

    lines = [f"## Debug Mode: {status_label}  ·  {len(entries)} recorded entries\n"]

    # Table header
    lines.append(
        "| # | Time | Tool | Model | Tokens In | Tokens Out | Cost | Duration |"
    )
    lines.append(
        "|---|------|------|-------|----------:|----------:|------|---------|"
    )

    total_in = 0
    total_out = 0
    total_cost = 0.0
    model_counts: dict[str, int] = {}
    all_context_files: set[str] = set()

    for i, e in enumerate(entries, 1):
        # Time — show HH:MM:SS only
        ts = e.get("ts", "")
        try:
            time_part = ts[11:19]  # "HH:MM:SS"
        except Exception:
            time_part = ts

        tool = e.get("tool", "—")
        model = e.get("model", "—")
        t_in = e.get("tokens_in") or 0
        t_out = e.get("tokens_out") or 0
        cost = e.get("cost_usd") or 0.0
        dur = e.get("duration_ms")
        dur_str = f"{int(dur):,}ms" if dur is not None else "—"

        # Accumulate
        total_in += t_in
        total_out += t_out
        total_cost += cost
        if model and model != "—":
            model_counts[model] = model_counts.get(model, 0) + 1
        for cf in e.get("context_files") or []:
            all_context_files.add(cf)

        t_in_str = f"{t_in:,}" if t_in else "—"
        t_out_str = f"{t_out:,}" if t_out else "—"
        cost_str = f"${cost:.4f}" if cost else "$0"

        lines.append(
            f"| {i} | {time_part} | {tool} | {model} "
            f"| {t_in_str} | {t_out_str} | {cost_str} | {dur_str} |"
        )

    # Session summary
    lines.append("")
    lines.append("### Session Summary")

    api_calls = sum(1 for e in entries if e.get("tokens_in"))
    model_dist = ", ".join(f"{m}×{c}" for m, c in sorted(model_counts.items()))
    lines.append(f"- **Total API calls:** {api_calls}  ({model_dist or 'none'})")
    lines.append(
        f"- **Total tokens:** {total_in + total_out:,}  "
        f"(input: {total_in:,} | output: {total_out:,})"
    )
    lines.append(f"- **Total cost:** ~${total_cost:.4f}")
    if all_context_files:
        lines.append(f"- **Unique context files sent:** {len(all_context_files)}")

    # Last classification detail (most recent delegate entry)
    last_delegate = next(
        (e for e in reversed(entries) if e.get("tool") == "delegate_to_model"), None
    )
    if last_delegate:
        lines.append("")
        lines.append("### Last Delegation Detail")
        lines.append(f"- **Task:** {last_delegate.get('task_preview', '—')}")
        lines.append(
            f"- **Model:** {last_delegate.get('model', '—')} "
            f"({last_delegate.get('model_id', '')})"
        )
        reason = last_delegate.get("classification_reason", "")
        confidence = last_delegate.get("classification_confidence")
        if reason or confidence is not None:
            conf_str = f" (confidence: {confidence:.2f})" if confidence else ""
            lines.append(f"- **Classification:** {reason}{conf_str}")
        cf = last_delegate.get("context_files") or []
        if cf:
            lines.append(f"- **Context files:** {', '.join(cf)}")

    return "\n".join(lines)
