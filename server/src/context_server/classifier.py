"""Rule-based task classifier for tiered Claude model routing."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Classification:
    """Result of classifying a task."""

    model: str  # haiku, sonnet, opus
    confidence: float
    reason: str
    tier: str = ""  # easy, medium, hard
    estimated_input_tokens: int = 0
    estimated_output_tokens: int = 0
    cost_per_model: dict[str, float] | None = None  # {model: cost_usd}


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


# Pricing per model (USD per 1M tokens)
_PRICING = {
    "haiku": {"input": 0.80, "output": 4.00},
    "sonnet": {"input": 3.00, "output": 15.00},
    "opus": {"input": 15.00, "output": 75.00},
}


def estimate_task_tokens(task_description: str) -> tuple[int, int]:
    """Estimate input and output tokens for a task.

    Args:
        task_description: The task description.

    Returns:
        Tuple of (estimated_input_tokens, estimated_output_tokens).
    """
    # Heuristic: 1 token per ~4 characters
    task_tokens = max(1, len(task_description) // 4)

    # Add overhead for context, formatting, system prompts (~500 tokens baseline)
    estimated_input = task_tokens + 500

    # Output tokens depend on task complexity (estimated based on task length)
    if len(task_description) < 50:
        estimated_output = 200  # EASY
    elif len(task_description) < 150:
        estimated_output = 500  # MEDIUM
    else:
        estimated_output = 1000  # HARD

    return estimated_input, estimated_output


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    """Estimate USD cost for a model call.

    Args:
        model: Model tier (haiku, sonnet, opus).
        input_tokens: Number of input tokens.
        output_tokens: Number of output tokens.

    Returns:
        Estimated cost in USD.
    """
    pricing = _PRICING.get(model, _PRICING["sonnet"])
    input_cost = (input_tokens / 1_000_000) * pricing["input"]
    output_cost = (output_tokens / 1_000_000) * pricing["output"]
    return round(input_cost + output_cost, 6)


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

    # Determine tier based on best model
    if best_model == "haiku":
        tier = "easy"
    elif best_model == "sonnet":
        tier = "medium"
    else:
        tier = "hard"

    # Estimate tokens and calculate costs
    est_input, est_output = estimate_task_tokens(task)
    cost_per_model = {
        "haiku": estimate_cost("haiku", est_input, est_output),
        "sonnet": estimate_cost("sonnet", est_input, est_output),
        "opus": estimate_cost("opus", est_input, est_output),
    }

    return Classification(
        model=best_model,
        confidence=round(confidence, 2),
        reason=reason,
        tier=tier,
        estimated_input_tokens=est_input,
        estimated_output_tokens=est_output,
        cost_per_model=cost_per_model,
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
