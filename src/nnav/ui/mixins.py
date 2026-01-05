"""Shared mixins and bindings for nnav UI."""

from typing import Any

from textual.binding import Binding

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
