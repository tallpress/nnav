"""Shared CSS styles for nnav UI components."""

# Fullscreen mode - hides header, footer, and status bar
FULLSCREEN_CSS = """
.fullscreen Header {
    display: none;
}

.fullscreen Footer {
    display: none;
}

.fullscreen #status-bar {
    display: none;
}
"""

# Status bar at bottom of screen
STATUS_BAR_CSS = """
#status-bar {
    dock: bottom;
    height: 1;
    padding: 0 1;
    background: $primary-background;
}
"""

# Main container with DataTable layout
MAIN_CONTAINER_CSS = """
#main-container {
    height: 1fr;
}

DataTable {
    height: 1fr;
}
"""

# Base dialog CSS for modal screens
DIALOG_BASE_CSS = """
#dialog {
    border: solid $primary;
    background: $surface;
    padding: 1 2;
}

#title {
    text-style: bold;
    text-align: center;
    padding-bottom: 1;
}

#hint {
    text-align: center;
    color: $text-muted;
    padding-top: 1;
}
"""


def dialog_css(
    screen_name: str,
    width: int | str = 70,
    height: str = "auto",
    max_height: str = "90%",
) -> str:
    """Generate dialog CSS for a modal screen.

    Args:
        screen_name: The class name of the modal screen
        width: Dialog width (int for fixed, str for percentage)
        height: Dialog height
        max_height: Maximum height constraint

    Returns:
        CSS string for the dialog
    """
    width_str = str(width) if isinstance(width, int) else width
    return f"""
{screen_name} {{
    align: center middle;
}}

{screen_name} #dialog {{
    width: {width_str};
    height: {height};
    max-height: {max_height};
    border: solid $primary;
    background: $surface;
    padding: 1 2;
}}

{screen_name} #title {{
    text-style: bold;
    text-align: center;
    padding-bottom: 1;
}}

{screen_name} #hint {{
    text-align: center;
    color: $text-muted;
    padding-top: 1;
}}
"""
