"""Shared widgets for nnav UI."""

from textual.events import Key
from textual.widgets import Input


class FilterInput(Input):
    """Input widget for filtering with visibility toggle and history.

    Hidden by default, shown when the 'visible' class is added.
    Supports up/down arrow keys to navigate filter history.
    """

    DEFAULT_CSS = """
    FilterInput {
        dock: bottom;
        display: none;
    }

    FilterInput.visible {
        display: block;
    }
    """

    def __init__(self, *args: object, **kwargs: object) -> None:
        super().__init__(*args, **kwargs)  # type: ignore[arg-type]
        self._history: list[str] = []
        self._history_index: int = -1
        self._current_input: str = ""

    def set_history(self, history: list[str]) -> None:
        """Set the filter history list."""
        self._history = history
        self._history_index = -1

    def add_to_history(self, text: str) -> None:
        """Add a filter to history (dedupe, most recent last)."""
        text = text.strip()
        if not text:
            return
        # Remove if already exists to avoid duplicates
        if text in self._history:
            self._history.remove(text)
        self._history.append(text)
        # Limit history size
        if len(self._history) > 50:
            self._history = self._history[-50:]
        self._history_index = -1

    def get_history(self) -> list[str]:
        """Get the current history list."""
        return self._history.copy()

    def on_key(self, event: Key) -> None:
        """Handle up/down arrow keys for history navigation."""
        if event.key == "up":
            if not self._history:
                return
            # Save current input if starting navigation
            if self._history_index == -1:
                self._current_input = self.value
            # Move back in history
            if self._history_index < len(self._history) - 1:
                self._history_index += 1
                self.value = self._history[-(self._history_index + 1)]
                self.cursor_position = len(self.value)
            event.prevent_default()
            event.stop()
        elif event.key == "down":
            if self._history_index > 0:
                self._history_index -= 1
                self.value = self._history[-(self._history_index + 1)]
                self.cursor_position = len(self.value)
            elif self._history_index == 0:
                # Return to current input
                self._history_index = -1
                self.value = self._current_input
                self.cursor_position = len(self.value)
            event.prevent_default()
            event.stop()

    def on_focus(self) -> None:
        """Reset history index when focused."""
        self._history_index = -1
        self._current_input = ""
