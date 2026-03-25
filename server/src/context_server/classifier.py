"""Rule-based task classifier for tiered Claude model routing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Classification:
    """Result of classifying a task."""

    model: str  # haiku, sonnet, opus
    confidence: float
    reason: str


# Keyword sets for each tier (keyword -> weight)
HAIKU_KEYWORDS = {
    "format": 1.0,
    "rename": 1.0,
    "sort": 0.8,
    "imports": 0.5,
    "organize": 0.8,
    "move": 0.7,
    "delete": 0.6,
    "remove": 0.5,
    "lint": 1.0,
    "prettify": 0.9,
    "cleanup": 0.7,
    "typo": 0.9,
    "spelling": 0.8,
    "simple": 0.5,
    "basic": 0.4,
    "list": 0.3,
    "show": 0.3,
    "print": 0.3,
    "log": 0.3,
    "comment": 0.5,
    "type hint": 0.6,
    "annotation": 0.5,
}

SONNET_KEYWORDS = {
    "explain": 1.0,
    "summarize": 0.9,
    "document": 0.9,
    "documentation": 0.9,
    "test": 0.7,
    "tests": 0.7,
    "unit test": 0.8,
    "what does": 0.8,
    "how does": 0.7,
    "describe": 0.7,
    "review": 0.8,
    "code review": 0.9,
    "generate": 0.6,
    "api doc": 0.9,
    "readme": 0.7,
    "translate": 0.6,
    "convert": 0.5,
    "simple refactor": 0.7,
    "extract": 0.5,
    "interface": 0.4,
    "types": 0.4,
}

OPUS_KEYWORDS = {
    "design": 1.0,
    "architect": 1.0,
    "architecture": 1.0,
    "system": 0.7,
    "refactor": 0.8,
    "restructure": 0.9,
    "debug": 0.8,
    "debugging": 0.8,
    "security": 1.0,
    "vulnerability": 1.0,
    "performance": 0.9,
    "optimize": 0.8,
    "migration": 0.9,
    "database": 0.7,
    "schema": 0.7,
    "complex": 0.6,
    "multi": 0.4,
    "across": 0.4,
    "entire": 0.4,
    "codebase": 0.5,
    "strategy": 0.8,
    "pattern": 0.5,
    "algorithm": 0.8,
    "concurrency": 0.9,
    "async": 0.5,
    "race condition": 1.0,
    "deadlock": 1.0,
    "memory leak": 0.9,
    "scalab": 0.8,
}

# Scope indicators (multi-file/system-level raise the tier)
SCOPE_ESCALATORS = {
    "across the": 0.5,
    "entire project": 0.6,
    "all files": 0.4,
    "codebase": 0.5,
    "multiple": 0.3,
    "system-wide": 0.6,
    "end-to-end": 0.5,
    "full stack": 0.5,
    "middleware": 0.3,
    "pipeline": 0.3,
    "workflow": 0.3,
}


def classify_task(task: str) -> Classification:
    """Classify a task description into a Claude model tier.

    Args:
        task: The task description from the user.

    Returns:
        Classification with model name, confidence, and reason.
    """
    task_lower = task.lower()

    # Check for explicit overrides
    if task_lower.startswith("[haiku]") or task_lower.startswith("--haiku"):
        return Classification(model="haiku", confidence=1.0, reason="Explicit override")
    if task_lower.startswith("[sonnet]") or task_lower.startswith("--sonnet"):
        return Classification(model="sonnet", confidence=1.0, reason="Explicit override")
    if task_lower.startswith("[opus]") or task_lower.startswith("--opus"):
        return Classification(model="opus", confidence=1.0, reason="Explicit override")

    # Score each tier
    scores = {
        "haiku": 0.0,
        "sonnet": 0.0,
        "opus": 0.0,
    }
    matched_keywords: dict[str, list[str]] = {
        "haiku": [],
        "sonnet": [],
        "opus": [],
    }

    for keyword, weight in HAIKU_KEYWORDS.items():
        if keyword in task_lower:
            scores["haiku"] += weight
            matched_keywords["haiku"].append(keyword)

    for keyword, weight in SONNET_KEYWORDS.items():
        if keyword in task_lower:
            scores["sonnet"] += weight
            matched_keywords["sonnet"].append(keyword)

    for keyword, weight in OPUS_KEYWORDS.items():
        if keyword in task_lower:
            scores["opus"] += weight
            matched_keywords["opus"].append(keyword)

    # Scope escalation
    scope_boost = 0.0
    for phrase, weight in SCOPE_ESCALATORS.items():
        if phrase in task_lower:
            scope_boost += weight

    scores["opus"] += scope_boost * 0.5
    scores["sonnet"] += scope_boost * 0.2

    # Question format detection (tends toward sonnet)
    if any(task_lower.startswith(q) for q in ("what ", "how ", "why ", "where ", "when ", "can ")):
        scores["sonnet"] += 0.5

    # Complexity from task length (longer = likely more complex)
    word_count = len(task.split())
    if word_count > 30:
        scores["opus"] += 0.3
    elif word_count > 15:
        scores["sonnet"] += 0.2

    # Determine winner
    total = sum(scores.values()) or 1.0
    best_model = max(scores, key=lambda k: scores[k])
    confidence = scores[best_model] / total if total > 0 else 0.33

    # If no clear signal, default to sonnet
    if max(scores.values()) < 0.3:
        best_model = "sonnet"
        confidence = 0.4
        reason = "No strong signal detected, defaulting to Sonnet"
    else:
        top_keywords = matched_keywords[best_model][:3]
        reason = f"Matched keywords: {', '.join(top_keywords)}" if top_keywords else "Scope/complexity analysis"

    return Classification(
        model=best_model,
        confidence=round(confidence, 2),
        reason=reason,
    )


# Model ID mapping
MODEL_IDS = {
    "haiku": "claude-haiku-4-5-20251001",
    "sonnet": "claude-sonnet-4-20250514",
    "opus": "claude-opus-4-20250514",
}


def get_model_id(model: str) -> str:
    """Get the full Anthropic model ID for a tier name."""
    return MODEL_IDS.get(model, MODEL_IDS["sonnet"])
