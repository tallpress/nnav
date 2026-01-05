"""Clipboard utilities for nnav."""

import subprocess


def copy_to_clipboard(text: str) -> bool:
    """Copy text to system clipboard.

    Tries pbcopy (macOS) first, then xclip (Linux).

    Args:
        text: Text to copy to clipboard

    Returns:
        True if successful, False otherwise
    """
    # Try macOS pbcopy first
    try:
        subprocess.run(["pbcopy"], input=text.encode(), check=True)
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    # Try Linux xclip
    try:
        subprocess.run(
            ["xclip", "-selection", "clipboard"],
            input=text.encode(),
            check=True,
        )
        return True
    except (subprocess.SubprocessError, FileNotFoundError):
        pass

    return False
