"""Shared mixins and bindings for nnav UI."""

from typing import Any

from textual.binding import Binding
from textual.widgets import DataTable

from nnav.ui.widgets import FilterInput

# Common vim-style cursor navigation bindings
CURSOR_BINDINGS: list[Binding] = [
    Binding("j", "cursor_down", "Down", show=False),
    Binding("k", "cursor_up", "Up", show=False),
    Binding("g", "cursor_top", "Top", show=False),
    Binding("G", "cursor_bottom", "Bottom", show=False),
]

# Fullscreen toggle binding
FULLSCREEN_BINDING = Binding("F", "toggle_fullscreen", "Fullscreen")


class FullscreenMixin:
    """Mixin providing fullscreen toggle functionality.

    Requires the app to have FULLSCREEN_CSS in its CSS and
    FULLSCREEN_BINDING in its BINDINGS.
    """

    _fullscreen: bool = False

    def action_toggle_fullscreen(self: Any) -> None:
        """Toggle fullscreen mode (hide header/footer/status bar)."""
        self._fullscreen = not self._fullscreen
        if self._fullscreen:
            self.add_class("fullscreen")
        else:
            self.remove_class("fullscreen")


class FilterMixin:
    """Mixin providing filter input behavior.

    Requires:
    - FilterInput widget with id="filter" in compose()
    - filter_text: str attribute on the class
    """

    filter_text: str

    def action_start_filter(self: Any) -> None:
        """Show filter input and focus it."""
        filter_input = self.query_one("#filter", FilterInput)
        filter_input.add_class("visible")
        filter_input.value = self.filter_text
        filter_input.focus()

    def _hide_filter_input(self: Any) -> None:
        """Hide filter input and clear its value."""
        filter_input = self.query_one("#filter", FilterInput)
        if filter_input.has_class("visible"):
            filter_input.remove_class("visible")
            filter_input.value = ""

    def _focus_table(self: Any) -> None:
        """Focus the data table."""
        self.query_one(DataTable).focus()
