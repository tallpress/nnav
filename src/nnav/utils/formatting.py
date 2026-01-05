"""Formatting utilities for nnav."""


def format_bytes(num_bytes: int) -> str:
    """Format bytes to human readable string.

    Args:
        num_bytes: Number of bytes to format

    Returns:
        Human readable string like "1.5 MB" or "256 KB"
    """
    size = float(num_bytes)
    for unit in ["B", "KB", "MB", "GB", "TB"]:
        if size < 1024:
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{size:.1f} PB"
