"""MCP server for codebase context optimization."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from .graph import CodeGraph
from .parser import parse_file, detect_tests
from .blast_radius import compute_blast_radius, get_relevant_files_for_task
from .classifier import classify_task, get_model_id
from .utils.file_walker import walk_project, generate_tree
from .utils.hasher import hash_file, get_changed_files, save_hashes
from .utils.token_counter import estimate_tokens, format_tokens
from . import debug as dbg

mcp = FastMCP(
    "context-server",
    instructions="Codebase context optimization with Tree-sitter AST parsing and tiered Claude model routing",
)


def _get_project_root() -> str:
    """Get the project root from environment or current directory."""
    return os.environ.get("PROJECT_ROOT", os.getcwd())


def _get_context_dir() -> Path:
    """Get the .claude/context directory path."""
    return Path(_get_project_root()) / ".claude" / "context"


def _get_graph() -> CodeGraph:
    """Get or create the code graph."""
    ctx_dir = _get_context_dir()
    return CodeGraph(ctx_dir / "graph.db")


# --- Scan Tool ---


@mcp.tool()
def scan_project(
    project_path: str | None = None,
    max_file_size_kb: int = 100,
) -> str:
    """Scan a project with Tree-sitter AST parsing and build a dependency graph.

    This creates a SQLite graph database in .claude/context/graph.db containing
    all functions, classes, imports, and their relationships.

    Args:
        project_path: Path to project root. Defaults to current directory.
        max_file_size_kb: Skip files larger than this (default 100KB).
    """
    root = Path(project_path) if project_path else Path(_get_project_root())
    if not root.exists():
        return f"Error: Project path does not exist: {root}"

    ctx_dir = root / ".claude" / "context"
    ctx_dir.mkdir(parents=True, exist_ok=True)

    graph = CodeGraph(ctx_dir / "graph.db")
    hashes_path = ctx_dir / "file_hashes.json"

    # Walk project
    files = walk_project(root, max_file_size_kb=max_file_size_kb)
    if not files:
        graph.close()
        return "No supported source files found in project."

    # Check for incremental update
    changed_files, deleted_paths, new_hashes = get_changed_files(files, hashes_path)

    # Remove deleted files from graph
    for deleted in deleted_paths:
        graph.remove_file(deleted)

    # Parse changed files
    parsed_count = 0
    total_nodes = 0
    total_edges = 0
    errors: list[str] = []

    for file_info in changed_files:
        try:
            result = parse_file(
                file_info["path"],
                file_info["language"],
            )
            # Use relative paths in graph for portability
            for node in result.nodes:
                node.id = node.id.replace(file_info["path"], file_info["relative_path"])
                node.file_path = file_info["relative_path"]
            for edge in result.edges:
                edge.source_id = edge.source_id.replace(
                    file_info["path"], file_info["relative_path"]
                )
                # target_id may still have '?::' prefix, leave as-is for resolution

            # Detect test relationships
            test_edges = detect_tests(file_info["relative_path"], result.nodes)
            result.edges.extend(test_edges)

            # Remove old data for this file, then insert new
            graph.remove_file(file_info["relative_path"])
            graph.upsert_nodes(result.nodes)
            graph.upsert_edges(result.edges)
            graph.upsert_file(
                file_info["relative_path"],
                new_hashes[file_info["relative_path"]],
                file_info["language"],
            )

            parsed_count += 1
            total_nodes += len(result.nodes)
            total_edges += len(result.edges)

        except Exception as e:
            errors.append(f"{file_info['relative_path']}: {e}")

    # Resolve cross-file edges
    resolved = graph.resolve_edges()

    # Save hashes
    save_hashes(hashes_path, new_hashes)

    # Build report
    stats = graph.get_stats()
    graph.close()

    report_lines = [
        "## Scan Complete",
        "",
        f"- **Files scanned:** {len(files)} total, {parsed_count} parsed (changed/new)",
        f"- **Deleted:** {len(deleted_paths)} files removed",
        f"- **Nodes:** {stats['total_nodes']} ({', '.join(f'{k}: {v}' for k, v in stats['nodes_by_kind'].items())})",
        f"- **Edges:** {stats['total_edges']} ({', '.join(f'{k}: {v}' for k, v in stats['edges_by_kind'].items())})",
        f"- **Cross-file edges resolved:** {resolved}",
        f"- **Graph stored at:** .claude/context/graph.db",
    ]

    if errors:
        report_lines.append(f"\n### Parse Errors ({len(errors)})")
        for err in errors[:10]:
            report_lines.append(f"- {err}")

    return "\n".join(report_lines)


# --- Context Tools ---


@mcp.tool()
def get_blast_radius(
    file_paths: list[str],
    depth: int = 2,
    token_budget: int | None = None,
) -> str:
    """Compute the blast radius for changed files — all affected dependents, tests, and token estimate.

    Args:
        file_paths: List of changed file paths (relative to project root).
        depth: How many hops of transitive dependents to follow (default 2).
        token_budget: Optional max token budget for context.
    """
    graph = _get_graph()
    try:
        result = compute_blast_radius(
            graph,
            file_paths,
            _get_project_root(),
            depth=depth,
            token_budget=token_budget,
        )
        return result.structural_summary
    finally:
        graph.close()


@mcp.tool()
def get_relevant_files(
    task_description: str,
    max_files: int = 10,
) -> str:
    """Find relevant files for a coding task using the dependency graph.

    Searches function names, class names, and file paths for keywords from the task.

    Args:
        task_description: Description of the coding task.
        max_files: Maximum number of files to return (default 10).
    """
    graph = _get_graph()
    try:
        results = get_relevant_files_for_task(
            graph, task_description, _get_project_root(), max_files=max_files
        )
        if not results:
            return "No relevant files found. Try running /scan first to build the graph."

        lines = ["## Relevant Files\n"]
        total_tokens = 0
        for r in results:
            lines.append(f"### {r['file_path']} (score: {r['score']:.1f}, {r['nodes_count']} entities, {format_tokens(r['tokens'])} tokens)")
            for sig in r["signatures"]:
                lines.append(f"  - {sig}")
            total_tokens += r["tokens"]

        lines.append(f"\n**Total tokens:** {format_tokens(total_tokens)}")
        return "\n".join(lines)
    finally:
        graph.close()


@mcp.tool()
def get_review_context(
    file_paths: list[str],
) -> str:
    """Get a compact structural summary of files for code review.

    Returns function signatures, class hierarchies, and dependency info
    instead of full source code. Much more token-efficient.

    Args:
        file_paths: List of file paths to summarize.
    """
    graph = _get_graph()
    try:
        lines = ["## Structural Summary\n"]
        total_tokens = 0

        for fp in file_paths:
            nodes = graph.get_nodes_in_file(fp)
            deps = graph.get_file_dependencies(fp)
            dependents = graph.get_file_dependents(fp)
            tests = graph.get_tests_for_file(fp)

            lines.append(f"### {fp}")
            lines.append(f"Dependencies: {', '.join(deps) if deps else 'none'}")
            lines.append(f"Dependents: {', '.join(dependents) if dependents else 'none'}")
            lines.append(f"Tests: {len(tests)} test functions")
            lines.append("")

            for n in nodes:
                if n["kind"] != "module" and n.get("signature"):
                    lines.append(f"  - [{n['kind']}] {n['signature']} (L{n['start_line']}-{n['end_line']})")

            lines.append("")

            # Estimate tokens for summary vs full file
            summary_text = "\n".join(lines[-10:])
            total_tokens += estimate_tokens(summary_text)

        lines.append(f"**Summary tokens:** {format_tokens(total_tokens)}")
        return "\n".join(lines)
    finally:
        graph.close()


@mcp.tool()
def query_graph(
    query_type: str,
    target: str,
) -> str:
    """Query the dependency graph directly.

    Args:
        query_type: One of: callers, callees, dependents, dependencies, tests, search, nodes
        target: File path or node ID or search term depending on query_type.
    """
    graph = _get_graph()
    try:
        if query_type == "callers":
            results = graph.get_callers(target)
            if not results:
                return f"No callers found for {target}"
            lines = [f"## Callers of {target}\n"]
            for r in results:
                lines.append(f"- {r['id']} ({r['kind']}) in {r['file_path']}")
            return "\n".join(lines)

        elif query_type == "callees":
            results = graph.get_callees(target)
            if not results:
                return f"No callees found for {target}"
            lines = [f"## Functions called by {target}\n"]
            for r in results:
                lines.append(f"- {r['id']} ({r['kind']}) in {r['file_path']}")
            return "\n".join(lines)

        elif query_type == "dependents":
            results = graph.get_file_dependents(target)
            if not results:
                return f"No dependents found for {target}"
            return f"## Files depending on {target}\n\n" + "\n".join(f"- {r}" for r in results)

        elif query_type == "dependencies":
            results = graph.get_file_dependencies(target)
            if not results:
                return f"No dependencies found for {target}"
            return f"## Files imported by {target}\n\n" + "\n".join(f"- {r}" for r in results)

        elif query_type == "tests":
            results = graph.get_tests_for_file(target)
            if not results:
                return f"No tests found for {target}"
            lines = [f"## Tests for {target}\n"]
            for r in results:
                lines.append(f"- {r['name']} in {r['file_path']}")
            return "\n".join(lines)

        elif query_type == "search":
            results = graph.search_nodes(target)
            if not results:
                return f"No nodes found matching '{target}'"
            lines = [f"## Search results for '{target}'\n"]
            for r in results:
                lines.append(f"- [{r['kind']}] {r['id']}: {r.get('signature', '')}")
            return "\n".join(lines)

        elif query_type == "nodes":
            results = graph.get_nodes_in_file(target)
            if not results:
                return f"No nodes found in {target}"
            lines = [f"## Nodes in {target}\n"]
            for r in results:
                if r["kind"] != "module":
                    lines.append(f"- [{r['kind']}] {r['name']}: {r.get('signature', '')} (L{r['start_line']}-{r['end_line']})")
            return "\n".join(lines)

        else:
            return f"Unknown query type: {query_type}. Use: callers, callees, dependents, dependencies, tests, search, nodes"
    finally:
        graph.close()


# --- Classification & Delegation ---


@mcp.tool()
def classify_task_tool(
    task_description: str,
) -> str:
    """Classify a task's complexity and recommend the optimal Claude model tier.

    Returns the recommended model (haiku/sonnet/opus), confidence score, and reasoning.

    Args:
        task_description: Description of the coding task.
    """
    t0 = time.monotonic()
    result = classify_task(task_description)
    duration_ms = int((time.monotonic() - t0) * 1000)

    # Write debug log entry (free — no API call, no tokens)
    dbg.log_entry(
        _get_project_root(),
        {
            "ts": dbg.now_iso(),
            "tool": "classify_task_tool",
            "task_preview": task_description[:120],
            "model": result.model,
            "model_id": get_model_id(result.model),
            "classification_reason": result.reason,
            "classification_confidence": round(result.confidence, 3),
            "tokens_in": None,
            "tokens_out": None,
            "tokens_total": None,
            "cost_usd": 0.0,
            "duration_ms": duration_ms,
            "status": "success",
        },
    )

    return json.dumps(
        {
            "model": result.model,
            "model_id": get_model_id(result.model),
            "confidence": result.confidence,
            "reason": result.reason,
            "cost_tier": {
                "haiku": "$ (cheapest)",
                "sonnet": "$$ (balanced)",
                "opus": "$$$ (premium)",
            }[result.model],
        },
        indent=2,
    )


@mcp.tool()
def delegate_to_model(
    task: str,
    model: str = "sonnet",
    context: str = "",
    max_tokens: int = 4096,
    history: str = "",
) -> str:
    """Delegate a task to a specific Claude model tier via the Anthropic API.

    Supports multi-turn conversations: pass the previous exchange via `history`
    so the delegated model retains full context across follow-up questions.

    Args:
        task: The new user message to send (latest turn).
        model: Model tier - "haiku", "sonnet", or "opus". Default: "sonnet".
        context: Optional context for the FIRST turn only (file contents, summaries).
                 Ignored when `history` is provided.
        max_tokens: Maximum response tokens (default 4096).
        history: JSON array of prior messages: [{"role": "user"|"assistant", "content": "..."}].
                 When provided, `task` is appended as the next user message.
                 Leave empty for a fresh single-turn call.
    """
    try:
        import anthropic
    except ImportError:
        return "Error: anthropic package not installed. Run: pip install anthropic"

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        return "Error: ANTHROPIC_API_KEY environment variable not set."

    model_id = get_model_id(model)
    client = anthropic.Anthropic(api_key=api_key)

    # --- Build messages list ---
    # Multi-turn: restore history and append the new user message
    if history:
        try:
            messages = json.loads(history)
            if not isinstance(messages, list):
                raise ValueError("history must be a JSON array")
        except (json.JSONDecodeError, ValueError) as e:
            return f"Error: invalid history JSON — {e}"
        messages.append({"role": "user", "content": task})
        turn = len([m for m in messages if m["role"] == "user"])
    else:
        # Single-turn (first call): embed context into the first user message
        if context:
            messages = [{"role": "user", "content": f"Context:\n{context}\n\nTask: {task}"}]
        else:
            messages = [{"role": "user", "content": task}]
        turn = 1

    # Detect context files from the context string (best-effort, first turn only)
    context_files: list[str] = []
    if context and not history:
        for line in context.splitlines():
            line = line.strip()
            if line.startswith("###") and ("." in line):
                candidate = line.lstrip("#").strip()
                if "/" in candidate or candidate.endswith(
                    (".py", ".ts", ".js", ".go", ".java", ".rs")
                ):
                    context_files.append(candidate)
    context_tokens = estimate_tokens(context) if (context and not history) else 0

    t0 = time.monotonic()
    try:
        response = client.messages.create(
            model=model_id,
            max_tokens=max_tokens,
            messages=messages,
        )
        duration_ms = int((time.monotonic() - t0) * 1000)
        result_text = response.content[0].text

        # Build updated history for the caller to pass on the next turn
        messages.append({"role": "assistant", "content": result_text})
        updated_history = json.dumps(messages, ensure_ascii=False)

        # Metadata footer
        usage = response.usage
        turn_label = f"turn {turn}" if turn > 1 else "single-turn"
        meta = (
            f"\n\n---\n"
            f"_Model: {model} ({model_id}) | {turn_label} | "
            f"Input: {usage.input_tokens} tokens | Output: {usage.output_tokens} tokens_"
            f"\n<!-- DELEGATE_HISTORY:{updated_history} -->"
            f"\n<!-- DELEGATE_MODEL:{model} -->"
        )

        # Debug log
        dbg.log_entry(
            _get_project_root(),
            {
                "ts": dbg.now_iso(),
                "tool": "delegate_to_model",
                "task_preview": task[:120],
                "model": model,
                "model_id": model_id,
                "turn": turn,
                "classification_reason": None,
                "classification_confidence": None,
                "context_files": context_files or None,
                "context_tokens": context_tokens,
                "tokens_in": usage.input_tokens,
                "tokens_out": usage.output_tokens,
                "tokens_total": usage.input_tokens + usage.output_tokens,
                "cost_usd": dbg.estimate_cost(model, usage.input_tokens, usage.output_tokens),
                "duration_ms": duration_ms,
                "status": "success",
            },
        )

        return result_text + meta

    except Exception as e:
        duration_ms = int((time.monotonic() - t0) * 1000)
        dbg.log_entry(
            _get_project_root(),
            {
                "ts": dbg.now_iso(),
                "tool": "delegate_to_model",
                "task_preview": task[:120],
                "model": model,
                "model_id": model_id,
                "turn": turn,
                "tokens_in": None,
                "tokens_out": None,
                "tokens_total": None,
                "cost_usd": 0.0,
                "duration_ms": duration_ms,
                "status": f"error: {e}",
            },
        )
        return f"Error calling {model_id}: {e}"


# --- Debug Tools ---


@mcp.tool()
def toggle_debug(enable: bool) -> str:
    """Enable or disable debug mode for the plugin.

    When enabled, every call to delegate_to_model and classify_task_tool writes
    a structured entry to .claude/context/debug.log containing the model used,
    token counts, estimated cost, and duration.

    Args:
        enable: True to turn debug mode ON, False to turn it OFF.
    """
    root = _get_project_root()
    if enable:
        dbg.enable_debug(root)
        return (
            "✅ **Debug mode ON**\n\n"
            "All `delegate_to_model` and `classify_task_tool` calls will now be logged to "
            "`.claude/context/debug.log`.\n\n"
            "Run `/debug show` to view the log."
        )
    else:
        dbg.disable_debug(root)
        return (
            "⏹ **Debug mode OFF**\n\n"
            "Logging stopped. Existing entries in `.claude/context/debug.log` are preserved.\n"
            "Run `/debug show` to review past entries, or `/debug clear` to wipe them."
        )


@mcp.tool()
def get_debug_log(last_n: int = 10, clear: bool = False) -> str:
    """Read and display the plugin debug log.

    Shows a table of recent tool calls with model, token usage, estimated cost,
    and duration. Also prints a session summary (total tokens, total cost, model mix).

    Args:
        last_n: Number of most recent entries to display (default 10).
        clear: If True, truncate the log after reading (default False).
    """
    root = _get_project_root()
    entries = dbg.read_log(root, last_n=last_n)
    debug_on = dbg.is_debug_enabled(root)

    report = dbg.format_debug_report(entries, debug_on)

    if clear:
        dbg.clear_log(root)
        report += "\n\n_Log cleared._"

    return report


# --- Stats & Map ---


@mcp.tool()
def get_project_map(
    max_depth: int = 4,
) -> str:
    """Generate a tree view of the project structure.

    Args:
        max_depth: Maximum directory depth to display (default 4).
    """
    root = Path(_get_project_root())
    tree = generate_tree(root, max_depth=max_depth)
    return f"## Project Map\n\n```\n{tree}\n```"


@mcp.tool()
def get_stats() -> str:
    """Get graph statistics including node/edge counts and token savings estimates."""
    graph = _get_graph()
    try:
        stats = graph.get_stats()

        lines = [
            "## Graph Statistics\n",
            f"- **Files:** {stats['total_files']}",
            f"- **Nodes:** {stats['total_nodes']}",
            f"- **Edges:** {stats['total_edges']}",
            "",
            "### Nodes by Kind",
        ]
        for kind, count in stats["nodes_by_kind"].items():
            lines.append(f"  - {kind}: {count}")

        lines.append("\n### Edges by Kind")
        for kind, count in stats["edges_by_kind"].items():
            lines.append(f"  - {kind}: {count}")

        return "\n".join(lines)
    finally:
        graph.close()


def main():
    """Entry point for the MCP server."""
    mcp.run()


if __name__ == "__main__":
    main()
