"""Compute the blast radius of file changes — the minimal set of affected files."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from .graph import CodeGraph
from .utils.token_counter import estimate_tokens, format_tokens


@dataclass
class BlastRadius:
    """The impact radius of a set of changed files."""

    changed_files: list[str]
    affected_files: list[str]  # Direct + transitive dependents
    test_files: list[str]
    uncovered_functions: list[str]
    total_tokens: int = 0
    structural_summary: str = ""


def compute_blast_radius(
    graph: CodeGraph,
    changed_files: list[str],
    project_root: str,
    depth: int = 2,
    token_budget: int | None = None,
) -> BlastRadius:
    """Compute the blast radius for a set of changed files.

    Args:
        graph: The code dependency graph.
        changed_files: List of changed file paths (relative to project root).
        project_root: Absolute path to the project root.
        depth: How many hops of transitive dependents to follow.
        token_budget: Optional max token budget for the context.

    Returns:
        BlastRadius with affected files, tests, and structural summary.
    """
    affected: set[str] = set()
    test_files: set[str] = set()
    all_relevant: set[str] = set(changed_files)

    # BFS to find transitive dependents
    frontier = set(changed_files)
    for _ in range(depth):
        next_frontier: set[str] = set()
        for file_path in frontier:
            dependents = graph.get_file_dependents(file_path)
            for dep in dependents:
                if dep not in all_relevant:
                    next_frontier.add(dep)
                    affected.add(dep)
                    all_relevant.add(dep)
        frontier = next_frontier
        if not frontier:
            break

    # Also include direct dependencies (files the changed files import)
    for file_path in changed_files:
        deps = graph.get_file_dependencies(file_path)
        for dep in deps:
            all_relevant.add(dep)

    # Find test files
    for file_path in changed_files:
        tests = graph.get_tests_for_file(file_path)
        for t in tests:
            test_files.add(t["file_path"])
            all_relevant.add(t["file_path"])

    # Find uncovered functions (functions in changed files without test edges)
    uncovered: list[str] = []
    for file_path in changed_files:
        nodes = graph.get_nodes_in_file(file_path)
        tests = graph.get_tests_for_file(file_path)
        tested_targets = {t.get("name", "") for t in tests}
        for node in nodes:
            if node["kind"] in ("function", "method") and node["name"] not in tested_targets:
                uncovered.append(f"{node['file_path']}::{node['name']}")

    # Build structural summary
    summary_parts: list[str] = []
    total_tokens = 0

    summary_parts.append(f"## Blast Radius for {', '.join(changed_files)}")
    summary_parts.append("")

    # Changed files with their signatures
    summary_parts.append("### Changed Files")
    for fp in sorted(changed_files):
        nodes = graph.get_nodes_in_file(fp)
        summary_parts.append(f"\n**{fp}**")
        for n in nodes:
            if n["kind"] != "module" and n.get("signature"):
                summary_parts.append(f"  - {n['signature']} (L{n['start_line']}-{n['end_line']})")

        # Count tokens for this file
        full_path = Path(project_root) / fp
        if full_path.exists():
            content = full_path.read_text(errors="replace")
            total_tokens += estimate_tokens(content)

    # Affected files (dependents)
    if affected:
        summary_parts.append("\n### Affected Files (dependents)")
        for fp in sorted(affected):
            nodes = graph.get_nodes_in_file(fp)
            sigs = [n["signature"] for n in nodes if n["kind"] != "module" and n.get("signature")]
            summary_parts.append(f"- **{fp}**: {len(sigs)} entities")

            full_path = Path(project_root) / fp
            if full_path.exists():
                content = full_path.read_text(errors="replace")
                total_tokens += estimate_tokens(content)

    # Test files
    if test_files:
        summary_parts.append("\n### Test Files")
        for fp in sorted(test_files):
            summary_parts.append(f"- {fp}")

    # Uncovered functions
    if uncovered:
        summary_parts.append("\n### Uncovered Functions (no tests detected)")
        for func in sorted(uncovered):
            summary_parts.append(f"- {func}")

    summary_parts.append(f"\n### Token Estimate: {format_tokens(total_tokens)}")

    # Apply token budget
    if token_budget and total_tokens > token_budget:
        summary_parts.append(
            f"\n⚠️ Context exceeds budget ({format_tokens(total_tokens)} > {format_tokens(token_budget)}). "
            f"Sending structural summary only."
        )

    result = BlastRadius(
        changed_files=changed_files,
        affected_files=sorted(affected),
        test_files=sorted(test_files),
        uncovered_functions=uncovered,
        total_tokens=total_tokens,
        structural_summary="\n".join(summary_parts),
    )
    return result


def get_relevant_files_for_task(
    graph: CodeGraph,
    task_description: str,
    project_root: str,
    max_files: int = 10,
) -> list[dict]:
    """Find relevant files for a task description using graph search.

    Searches node names and file paths for keywords from the task.
    Returns files ranked by relevance.
    """
    # Extract keywords from task (simple word tokenization)
    words = task_description.lower().split()
    stop_words = {
        "the", "a", "an", "is", "are", "was", "were", "be", "been", "being",
        "have", "has", "had", "do", "does", "did", "will", "would", "shall",
        "should", "may", "might", "must", "can", "could", "to", "of", "in",
        "for", "on", "with", "at", "by", "from", "as", "into", "through",
        "and", "or", "but", "not", "this", "that", "these", "those", "it",
        "add", "create", "implement", "fix", "update", "change", "modify",
        "write", "make", "use", "get", "set",
    }
    keywords = [w for w in words if w not in stop_words and len(w) > 2]

    # Search nodes by each keyword
    file_scores: dict[str, float] = {}
    for keyword in keywords:
        matches = graph.search_nodes(keyword)
        for match in matches:
            fp = match["file_path"]
            file_scores[fp] = file_scores.get(fp, 0) + 1.0

        # Also check file paths
        all_files = graph.conn.execute("SELECT path FROM files").fetchall()
        for row in all_files:
            if keyword in row["path"].lower():
                file_scores[row["path"]] = file_scores.get(row["path"], 0) + 2.0

    # Sort by score, take top N
    ranked = sorted(file_scores.items(), key=lambda x: -x[1])[:max_files]

    results = []
    for fp, score in ranked:
        nodes = graph.get_nodes_in_file(fp)
        full_path = Path(project_root) / fp
        tokens = 0
        if full_path.exists():
            content = full_path.read_text(errors="replace")
            tokens = estimate_tokens(content)

        results.append(
            {
                "file_path": fp,
                "score": score,
                "nodes_count": len([n for n in nodes if n["kind"] != "module"]),
                "tokens": tokens,
                "signatures": [
                    n["signature"]
                    for n in nodes
                    if n["kind"] != "module" and n.get("signature")
                ][:10],
            }
        )

    return results
