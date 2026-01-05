"""Shared widgets for nnav UI."""

from textual.widgets import Input


class FilterInput(Input):
    """Input widget for filtering with visibility toggle.

    Hidden by default, shown when the 'visible' class is added.
    """

    CSS = """
    FilterInput {
        dock: top;
        display: none;
    }

    FilterInput.visible {
        display: block;
    }
    """
