"""Token estimation for context budgeting."""

from __future__ import annotations


def estimate_tokens(text: str) -> int:
    """Estimate token count using character-based heuristic.

    Roughly 1 token per 4 characters for English/code.
    This avoids importing tiktoken for simple estimates.
    """
    return max(1, len(text) // 4)


def estimate_tokens_accurate(text: str) -> int:
    """Estimate tokens using tiktoken (cl100k_base encoding).

    Falls back to character-based estimation if tiktoken is unavailable.
    """
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except (ImportError, Exception):
        return estimate_tokens(text)


def format_tokens(count: int) -> str:
    """Format token count for display."""
    if count >= 1_000_000:
        return f"{count / 1_000_000:.1f}M"
    if count >= 1_000:
        return f"{count / 1_000:.1f}K"
    return str(count)
