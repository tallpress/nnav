"""NATS subject pattern matching utilities."""

import re


def matches_nats_pattern(subject: str, pattern: str) -> bool:
    """Check if subject matches NATS wildcard pattern.

    NATS wildcards:
    - * matches a single token (no dots)
    - > matches one or more tokens (greedy, only valid at end)

    Args:
        subject: The NATS subject to check
        pattern: The pattern with optional wildcards

    Returns:
        True if subject matches the pattern
    """
    # Convert NATS wildcards to regex
    regex_pattern = (
        pattern.replace(".", r"\.").replace("*", r"[^.]+").replace(">", r".+")
    )
    try:
        return bool(re.match(f"^{regex_pattern}$", subject))
    except re.error:
        return False
