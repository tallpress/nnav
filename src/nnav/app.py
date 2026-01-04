"""Textual TUI application for NATS message visualization."""

import json
import re
import subprocess
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from rich.markup import escape as rich_escape
from rich.style import Style
from rich.syntax import Syntax
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    Static,
    TextArea,
    Tree,
)
from textual.widgets.data_table import RowKey
from textual.widgets.tree import TreeNode

from nnav.config import ColumnsConfig, HideConfig
from nnav.nats_client import JetStreamConfig, MessageType, NatsMessage, NatsSubscriber


@dataclass
class StoredMessage:
    """Message stored with row key for retrieval."""

    msg: NatsMessage
    row_key: RowKey | None
    bookmarked: bool = False
    related_index: int | None = None  # Index of matching request/response
    imported: bool = False  # True for messages loaded from file


class HelpScreen(ModalScreen[None]):
    """Help screen showing keyboard shortcuts."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("?", "dismiss", "Close"),
    ]

    CSS = """
    HelpScreen {
        align: center middle;
    }

    #help-dialog {
        width: 70;
        height: auto;
        max-height: 90%;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }

    #help-title {
        text-style: bold;
        text-align: center;
        padding-bottom: 1;
    }

    .help-section {
        padding-top: 1;
        color: $primary;
        text-style: bold;
    }

    .help-row {
        padding-left: 2;
    }

    #help-hint {
        text-align: center;
        color: $text-muted;
        padding-top: 1;
    }
    """

    def compose(self) -> ComposeResult:
        with Container(id="help-dialog"):
            yield Label("NATS Visualizer - Keyboard Shortcuts", id="help-title")

            yield Label("Navigation", classes="help-section")
            yield Label("  j / ↓      Move down", classes="help-row")
            yield Label("  k / ↑      Move up", classes="help-row")
            yield Label("  g          Go to first message", classes="help-row")
            yield Label("  G          Go to last message", classes="help-row")
            yield Label("  Enter      View message details", classes="help-row")
            yield Label("  n          Next bookmarked message", classes="help-row")
            yield Label("  N          Previous bookmarked message", classes="help-row")

            yield Label("Filtering & Search", classes="help-section")
            yield Label(
                "  /          Filter messages (text or /regex/)", classes="help-row"
            )
            yield Label("  Escape     Clear filter", classes="help-row")
            yield Label(
                "  t          Filter by message type (REQ/RES/PUB)", classes="help-row"
            )

            yield Label("Actions", classes="help-section")
            yield Label("  p          Pause/Resume stream", classes="help-row")
            yield Label("  c          Clear all messages", classes="help-row")
            yield Label("  m          Toggle bookmark on message", classes="help-row")
            yield Label("  y          Copy payload to clipboard", classes="help-row")
            yield Label("  Y          Copy subject to clipboard", classes="help-row")
            yield Label("  r          Republish selected message", classes="help-row")
            yield Label("  d          Diff two bookmarked messages", classes="help-row")

            yield Label("Export", classes="help-section")
            yield Label("  e          Export messages to JSON", classes="help-row")
            yield Label("  E          Export filtered messages", classes="help-row")

            yield Label("Views & Panels", classes="help-section")
            yield Label("  T          Subject tree browser", classes="help-row")
            yield Label("  i          Show connection info", classes="help-row")
            yield Label("  ?          Show this help", classes="help-row")
            yield Label("  q          Quit", classes="help-row")

            yield Label("In Message Detail View", classes="help-section")
            yield Label("  j / k      Scroll down / up", classes="help-row")
            yield Label("  g / G      Scroll to top / bottom", classes="help-row")
            yield Label("  /          JSON path query", classes="help-row")
            yield Label(
                "  r          Jump to related request/response", classes="help-row"
            )
            yield Label("  y / Y      Copy payload / subject", classes="help-row")

            yield Label("Press any key to close", id="help-hint")


class MessageDetailScreen(ModalScreen[int | None]):
    """Modal screen to display message details."""

    BINDINGS = [
        Binding("escape", "dismiss_or_reset", "Close"),
        Binding("enter", "focus_query_or_close", "Enter"),
        Binding("q", "dismiss_none", "Close"),
        Binding("y", "copy_payload", "Copy Payload"),
        Binding("Y", "copy_subject", "Copy Subject"),
        Binding("slash", "extract_json_path", "Query Path"),
        Binding("j", "scroll_down", "Scroll Down", show=False),
        Binding("k", "scroll_up", "Scroll Up", show=False),
        Binding("g", "scroll_top", "Scroll Top", show=False),
        Binding("G", "scroll_bottom", "Scroll Bottom", show=False),
        Binding("r", "goto_related", "Go to Response/Request"),
    ]

    CSS = """
    MessageDetailScreen {
        align: center middle;
    }

    #dialog {
        width: 85%;
        height: 85%;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }

    #title {
        dock: top;
        text-style: bold;
        padding-bottom: 1;
        color: $text;
    }

    #metadata {
        dock: top;
        height: auto;
        padding-bottom: 1;
    }

    .meta-row {
        height: auto;
    }

    .meta-latency {
        color: $success;
    }

    .meta-request {
        color: $warning;
    }

    #payload-container {
        height: 1fr;
        overflow: auto;
        border: solid $primary-darken-2;
    }

    #payload {
        padding: 1;
    }

    #path-label {
        color: $text-muted;
        padding: 0 1;
        display: none;
    }

    #path-label.visible {
        display: block;
    }

    #bottom-bar {
        dock: bottom;
        height: auto;
    }

    #json-path-container {
        height: auto;
        display: none;
        padding: 1;
        background: $surface-darken-1;
    }

    #json-path-container.visible {
        display: block;
    }

    #json-path-input {
        width: 100%;
    }

    #hint {
        text-align: center;
        color: $text-muted;
        padding: 1 0;
    }
    """

    def __init__(self, stored: StoredMessage) -> None:
        super().__init__()
        self.stored = stored
        self.msg = stored.msg
        self._parsed_json: dict[str, object] | list[object] | None = None
        self._is_json = False
        self._current_path: str | None = None  # Track if showing a path query result
        self._current_result: object = None  # Extracted result from path query

    def compose(self) -> ComposeResult:
        type_str = self.msg.message_type.value

        with Container(id="dialog"):
            yield Label(
                f"[{type_str}] {self.msg.subject}",
                id="title",
            )

            with Vertical(id="metadata"):
                yield Label(
                    f"Time: {self.msg.timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}",
                    classes="meta-row",
                )
                if self.msg.reply_to:
                    yield Label(
                        f"Reply-To: {self.msg.reply_to}",
                        classes="meta-row meta-request",
                    )
                    if self.stored.related_index is not None:
                        yield Label(
                            "  → Press 'r' to view response",
                            classes="meta-row meta-latency",
                        )
                if self.msg.request_subject:
                    yield Label(
                        f"Request Subject: {self.msg.request_subject}",
                        classes="meta-row",
                    )
                    if self.stored.related_index is not None:
                        yield Label(
                            "  → Press 'r' to view original request",
                            classes="meta-row meta-latency",
                        )
                if self.msg.latency_ms is not None:
                    yield Label(
                        f"Response Latency: {self.msg.latency_ms:.2f}ms",
                        classes="meta-row meta-latency",
                    )
                if self.msg.headers:
                    for k, v in self.msg.headers.items():
                        yield Label(
                            f"{rich_escape(k)}: {rich_escape(str(v))}",
                            classes="meta-row",
                        )
                yield Label(
                    f"Payload Size: {len(self.msg.payload)} bytes", classes="meta-row"
                )

            yield Label("", id="path-label")
            with ScrollableContainer(id="payload-container"):
                yield Static(id="payload")

            with Vertical(id="bottom-bar"):
                with Vertical(id="json-path-container"):
                    yield Input(
                        placeholder="Path: .user.name or .items[0] (empty to reset)",
                        id="json-path-input",
                    )

                hint_parts = ["q: close", "y: copy", "/: query", "jk: scroll"]
                if self.stored.related_index is not None:
                    if self.msg.message_type == MessageType.REQUEST:
                        hint_parts.append("r: response")
                    elif self.msg.message_type == MessageType.RESPONSE:
                        hint_parts.append("r: request")
                yield Label(" | ".join(hint_parts), id="hint")

    def on_mount(self) -> None:
        """Format and display the payload with syntax highlighting."""
        payload_widget = self.query_one("#payload", Static)
        self._display_payload(payload_widget, self.msg.payload)

    def _display_payload(self, widget: Static, payload: str) -> None:
        """Display payload with JSON syntax highlighting if applicable."""
        try:
            self._parsed_json = json.loads(payload)
            self._is_json = True
            formatted = json.dumps(self._parsed_json, indent=2)
            syntax = Syntax(formatted, "json", theme=self.app.theme, line_numbers=False)
            widget.update(syntax)
        except json.JSONDecodeError:
            self._parsed_json = None
            self._is_json = False
            widget.update(payload)

    def action_scroll_down(self) -> None:
        """Scroll payload down."""
        container = self.query_one("#payload-container", ScrollableContainer)
        container.scroll_relative(y=3)

    def action_scroll_up(self) -> None:
        """Scroll payload up."""
        container = self.query_one("#payload-container", ScrollableContainer)
        container.scroll_relative(y=-3)

    def action_scroll_top(self) -> None:
        """Scroll to top."""
        container = self.query_one("#payload-container", ScrollableContainer)
        container.scroll_home()

    def action_scroll_bottom(self) -> None:
        """Scroll to bottom."""
        container = self.query_one("#payload-container", ScrollableContainer)
        container.scroll_end()

    def action_dismiss_none(self) -> None:
        """Dismiss without navigation."""
        self.dismiss(None)

    def action_dismiss_or_reset(self) -> None:
        """Escape: reset query if active, otherwise close."""
        container = self.query_one("#json-path-container")
        if self._current_path is not None:
            # Reset to full payload
            self._reset_to_full_payload()
            container.remove_class("visible")
        elif container.has_class("visible"):
            # Just hide the input
            container.remove_class("visible")
        else:
            # Close the screen
            self.dismiss(None)

    def action_focus_query_or_close(self) -> None:
        """Enter: focus query input if visible, otherwise close."""
        container = self.query_one("#json-path-container")
        if container.has_class("visible"):
            # Re-focus the input for editing
            self.query_one("#json-path-input", Input).focus()
        else:
            # Close the screen
            self.dismiss(None)

    def action_goto_related(self) -> None:
        """Navigate to the related request or response."""
        if self.stored.related_index is not None:
            self.dismiss(self.stored.related_index)
        else:
            if self.msg.message_type == MessageType.REQUEST:
                self.notify("Response not yet received", severity="warning")
            else:
                self.notify("No related message found", severity="warning")

    def action_copy_payload(self) -> None:
        """Copy payload to clipboard. Copies query result if path is active."""
        if self._current_path is not None and self._current_result is not None:
            # Copy the path query result
            if isinstance(self._current_result, (dict, list)):
                text = json.dumps(self._current_result, indent=2)
            else:
                text = str(self._current_result)
            self._copy_to_clipboard(text)
            self.notify(f"Copied: {self._current_path}")
        elif self._is_json and self._parsed_json is not None:
            text = json.dumps(self._parsed_json, indent=2)
            self._copy_to_clipboard(text)
            self.notify("Payload copied to clipboard")
        else:
            self._copy_to_clipboard(self.msg.payload)
            self.notify("Payload copied to clipboard")

    def action_copy_subject(self) -> None:
        """Copy subject to clipboard."""
        self._copy_to_clipboard(self.msg.subject)
        self.notify("Subject copied to clipboard")

    def action_extract_json_path(self) -> None:
        """Toggle JSON path input."""
        if not self._is_json:
            self.notify("Payload is not valid JSON", severity="warning")
            return

        container = self.query_one("#json-path-container")
        container.toggle_class("visible")

        if container.has_class("visible"):
            input_widget = self.query_one("#json-path-input", Input)
            # Pre-fill with current path so user can amend it
            input_widget.value = self._current_path or ""
            input_widget.focus()
            # Move cursor to end
            input_widget.cursor_position = len(input_widget.value)

    def _reset_to_full_payload(self) -> None:
        """Reset the display to show the full payload."""
        self._current_path = None
        self._current_result = None
        payload_widget = self.query_one("#payload", Static)
        self._display_payload(payload_widget, self.msg.payload)
        path_label = self.query_one("#path-label", Label)
        path_label.update("")
        path_label.remove_class("visible")
        self.notify("Showing full payload")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle JSON path query."""
        if event.input.id == "json-path-input":
            path = event.value.strip()
            if path:
                self._execute_json_path(path)
                # Keep input visible but unfocus so keybindings work
                # User can press Enter to re-focus and edit
                self.set_focus(None)
            else:
                self._reset_to_full_payload()
                # Hide input when cleared
                self.query_one("#json-path-container").remove_class("visible")
                self.set_focus(None)

    def on_input_changed(self, event: Input.Changed) -> None:
        """Handle escape in input to reset."""
        pass  # Placeholder for potential live preview

    def _execute_json_path(self, path: str) -> None:
        """Execute a JSON path query and show result in main payload panel."""
        payload_widget = self.query_one("#payload", Static)
        path_label = self.query_one("#path-label", Label)

        if self._parsed_json is None:
            self.notify("Payload is not valid JSON", severity="error")
            return

        try:
            result = self._get_json_path(self._parsed_json, path)
            self._current_path = path
            self._current_result = result

            # Update path label
            path_label.update(f"Query: {path}")
            path_label.add_class("visible")

            # Display result in main payload area
            if isinstance(result, (dict, list)):
                formatted = json.dumps(result, indent=2)
                syntax = Syntax(
                    formatted, "json", theme=self.app.theme, line_numbers=False
                )
                payload_widget.update(syntax)
            elif isinstance(result, str):
                # String value - show as-is
                payload_widget.update(Text(f'"{result}"', style="green"))
            else:
                # Primitive value
                payload_widget.update(Text(str(result), style="cyan"))

            self.notify(f"Showing: {path}")
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    def _get_json_path(self, data: object, path: str) -> object:
        """Extract value at JSON path. Supports .key, [index], and combinations."""
        # Normalize path - remove leading $ or .
        path = path.strip()
        if path.startswith("$"):
            path = path[1:]
        if path.startswith("."):
            path = path[1:]

        if not path:
            return data

        current: object = data

        # Tokenize the path - match either .key or [index]
        tokens = re.findall(r"\.?([^.\[\]]+)|\[(\d+)\]", path)

        for token in tokens:
            key, index = token
            if key:  # It's a key access
                if isinstance(current, dict):
                    if key not in current:
                        raise KeyError(f"Key '{key}' not found")
                    current = current[key]
                else:
                    raise TypeError(
                        f"Cannot access key '{key}' on {type(current).__name__}"
                    )
            elif index:  # It's an index access
                idx = int(index)
                if isinstance(current, list):
                    if idx >= len(current) or idx < -len(current):
                        raise IndexError(
                            f"Index {idx} out of range (length {len(current)})"
                        )
                    current = current[idx]
                else:
                    raise TypeError(
                        f"Cannot access index [{idx}] on {type(current).__name__}"
                    )

        return current

    def _copy_to_clipboard(self, text: str) -> None:
        """Copy text to system clipboard."""
        try:
            subprocess.run(["pbcopy"], input=text.encode(), check=True)
        except (subprocess.SubprocessError, FileNotFoundError):
            try:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=text.encode(),
                    check=True,
                )
            except (subprocess.SubprocessError, FileNotFoundError):
                pass


class DiffScreen(ModalScreen[None]):
    """Screen showing diff between two messages."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
    ]

    CSS = """
    DiffScreen {
        align: center middle;
    }

    #diff-dialog {
        width: 90%;
        height: 90%;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }

    #diff-title {
        text-style: bold;
        text-align: center;
        padding-bottom: 1;
    }

    #diff-container {
        height: 1fr;
    }

    .diff-pane {
        width: 1fr;
        height: 1fr;
        border: solid $primary-darken-2;
        overflow: auto;
    }

    .diff-header {
        background: $primary-darken-2;
        padding: 0 1;
        text-style: bold;
    }

    .diff-content {
        padding: 1;
    }

    .diff-added {
        background: $success 20%;
    }

    .diff-removed {
        background: $error 20%;
    }
    """

    def __init__(self, msg1: NatsMessage, msg2: NatsMessage) -> None:
        super().__init__()
        self.msg1 = msg1
        self.msg2 = msg2

    def compose(self) -> ComposeResult:
        with Container(id="diff-dialog"):
            yield Label("Message Diff", id="diff-title")

            with Horizontal(id="diff-container"):
                with Vertical(classes="diff-pane"):
                    yield Label(
                        f"[{self.msg1.message_type.value}] {self.msg1.subject}",
                        classes="diff-header",
                    )
                    yield Label(
                        f"Time: {self.msg1.timestamp.strftime('%H:%M:%S.%f')[:-3]}",
                        classes="diff-header",
                    )
                    yield Static(id="diff-left", classes="diff-content")

                with Vertical(classes="diff-pane"):
                    yield Label(
                        f"[{self.msg2.message_type.value}] {self.msg2.subject}",
                        classes="diff-header",
                    )
                    yield Label(
                        f"Time: {self.msg2.timestamp.strftime('%H:%M:%S.%f')[:-3]}",
                        classes="diff-header",
                    )
                    yield Static(id="diff-right", classes="diff-content")

    def on_mount(self) -> None:
        """Display payloads with syntax highlighting."""
        left = self.query_one("#diff-left", Static)
        right = self.query_one("#diff-right", Static)
        self._display_payload(left, self.msg1.payload)
        self._display_payload(right, self.msg2.payload)

    def _display_payload(self, widget: Static, payload: str) -> None:
        """Display payload with syntax highlighting if JSON."""
        try:
            parsed = json.loads(payload)
            formatted = json.dumps(parsed, indent=2)
            syntax = Syntax(formatted, "json", theme=self.app.theme, line_numbers=False)
            widget.update(syntax)
        except json.JSONDecodeError:
            widget.update(payload)


class PublishScreen(ModalScreen[None]):
    """Screen for publishing a message."""

    BINDINGS = [
        Binding("escape", "dismiss", "Cancel"),
    ]

    CSS = """
    PublishScreen {
        align: center middle;
    }

    #publish-dialog {
        width: 75%;
        height: auto;
        max-height: 80%;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }

    #publish-title {
        text-style: bold;
        padding-bottom: 1;
    }

    .field-label {
        padding-top: 1;
        color: $text-muted;
    }

    Input {
        margin-bottom: 1;
    }

    TextArea {
        height: 10;
        margin-bottom: 1;
    }

    #publish-buttons {
        height: auto;
        align: center middle;
    }

    Button {
        margin: 0 1;
    }
    """

    def __init__(
        self,
        subscriber: NatsSubscriber,
        default_subject: str = "",
        default_payload: str = "",
    ) -> None:
        super().__init__()
        self.subscriber = subscriber
        self.default_subject = default_subject
        self.default_payload = default_payload

    def compose(self) -> ComposeResult:
        with Container(id="publish-dialog"):
            yield Label("Publish Message", id="publish-title")

            yield Label("Subject:", classes="field-label")
            yield Input(
                placeholder="e.g., my.subject",
                value=self.default_subject,
                id="subject-input",
            )

            yield Label(
                "Reply-To (optional, for request-reply):", classes="field-label"
            )
            yield Input(
                placeholder="Leave empty for fire-and-forget",
                id="reply-input",
            )

            yield Label("Payload (JSON or text):", classes="field-label")
            yield TextArea(
                self.default_payload or "{\n  \n}",
                id="payload-input",
                language="json",
            )

            with Horizontal(id="publish-buttons"):
                yield Button("Publish", variant="primary", id="publish-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    async def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "publish-btn":
            await self._publish()
        elif event.button.id == "cancel-btn":
            self.dismiss()

    async def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle input submission."""
        if event.input.id == "subject-input":
            self.query_one("#reply-input", Input).focus()
        elif event.input.id == "reply-input":
            self.query_one("#payload-input", TextArea).focus()

    async def _publish(self) -> None:
        """Publish the message."""
        subject = self.query_one("#subject-input", Input).value.strip()
        reply_to = self.query_one("#reply-input", Input).value.strip() or None
        payload = self.query_one("#payload-input", TextArea).text

        if not subject:
            self.notify("Subject is required", severity="error")
            return

        try:
            await self.subscriber.publish(subject, payload.encode(), reply_to=reply_to)
            self.notify(f"Published to {subject}")
            self.dismiss()
        except Exception as e:
            self.notify(f"Publish failed: {e}", severity="error")


class ExportScreen(ModalScreen[None]):
    """Screen for exporting messages."""

    BINDINGS = [
        Binding("escape", "dismiss", "Cancel"),
    ]

    CSS = """
    ExportScreen {
        align: center middle;
    }

    #export-dialog {
        width: 60%;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }

    #export-title {
        text-style: bold;
        padding-bottom: 1;
    }

    .field-label {
        padding-top: 1;
        color: $text-muted;
    }

    #export-info {
        padding: 1 0;
        color: $text-muted;
    }

    #export-buttons {
        height: auto;
        align: center middle;
        padding-top: 1;
    }

    Button {
        margin: 0 1;
    }
    """

    def __init__(
        self,
        messages: list["StoredMessage"],
        filtered_only: bool = False,
        default_path: str | None = None,
    ) -> None:
        super().__init__()
        self.messages = messages
        self.filtered_only = filtered_only
        self.default_path = default_path

    def compose(self) -> ComposeResult:
        count = len(self.messages)
        label = "filtered messages" if self.filtered_only else "all messages"

        # Use configured default or generate timestamped filename
        if self.default_path:
            initial_path = self.default_path
        else:
            initial_path = (
                f"~/nnav-export-{datetime.now().strftime('%Y%m%d-%H%M%S')}.json"
            )

        with Container(id="export-dialog"):
            yield Label("Export Messages", id="export-title")
            yield Label(f"Exporting {count} {label}", id="export-info")

            yield Label("File path:", classes="field-label")
            yield Input(
                placeholder="~/nnav-export.json",
                value=initial_path,
                id="path-input",
            )

            with Horizontal(id="export-buttons"):
                yield Button("Export JSON", variant="primary", id="json-btn")
                yield Button("Export NDJSON", variant="default", id="ndjson-btn")
                yield Button("Cancel", variant="default", id="cancel-btn")

    def on_button_pressed(self, event: Button.Pressed) -> None:
        """Handle button presses."""
        if event.button.id == "cancel-btn":
            self.dismiss()
            return

        path_str = self.query_one("#path-input", Input).value.strip()
        path = Path(path_str).expanduser()

        try:
            messages_data = [
                {
                    "timestamp": stored.msg.timestamp.isoformat(),
                    "type": stored.msg.message_type.value,
                    "subject": stored.msg.subject,
                    "payload": stored.msg.payload,
                    "reply_to": stored.msg.reply_to,
                    "headers": stored.msg.headers,
                    "latency_ms": stored.msg.latency_ms,
                    "request_subject": stored.msg.request_subject,
                    "bookmarked": stored.bookmarked,
                }
                for stored in self.messages
            ]

            if event.button.id == "json-btn":
                with path.open("w") as f:
                    json.dump(messages_data, f, indent=2)
            elif event.button.id == "ndjson-btn":
                with path.open("w") as f:
                    for msg in messages_data:
                        f.write(json.dumps(msg) + "\n")

            self.notify(f"Exported {len(messages_data)} messages to {path}")
            self.dismiss()

        except Exception as e:
            self.notify(f"Export failed: {e}", severity="error")


class ConnectionInfoScreen(ModalScreen[None]):
    """Screen showing connection information."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
    ]

    CSS = """
    ConnectionInfoScreen {
        align: center middle;
    }

    #info-dialog {
        width: 60;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }

    #info-title {
        text-style: bold;
        text-align: center;
        padding-bottom: 1;
    }

    .info-row {
        padding: 0 1;
    }

    .info-label {
        color: $text-muted;
    }

    .info-value {
        color: $text;
    }

    .info-connected {
        color: $success;
    }

    .info-disconnected {
        color: $error;
    }
    """

    def __init__(
        self, subscriber: NatsSubscriber, subject: str, message_count: int
    ) -> None:
        super().__init__()
        self.subscriber = subscriber
        self.subject = subject
        self.message_count = message_count

    def compose(self) -> ComposeResult:
        is_connected = self.subscriber.is_connected
        status = "Connected" if is_connected else "Disconnected"
        status_class = "info-connected" if is_connected else "info-disconnected"

        with Container(id="info-dialog"):
            yield Label("Connection Information", id="info-title")

            yield Label(f"Server: {self.subscriber.server_url}", classes="info-row")
            yield Label(f"Status: {status}", classes=f"info-row {status_class}")
            yield Label(f"Subject Filter: {self.subject}", classes="info-row")
            yield Label(f"Messages Received: {self.message_count}", classes="info-row")
            yield Label(
                f"Pending RPC: {self.subscriber.rpc_tracker.pending_count}",
                classes="info-row",
            )

            if self.subscriber.user:
                yield Label(f"User: {self.subscriber.user}", classes="info-row")


@dataclass
class SubjectNode:
    """Node in the subject tree."""

    name: str
    full_subject: str
    count: int
    children: dict[str, "SubjectNode"]


class SubjectTreeScreen(ModalScreen[str | None]):
    """Screen showing hierarchical subject tree."""

    BINDINGS = [
        Binding("escape", "dismiss_none", "Close"),
        Binding("q", "dismiss_none", "Close"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
    ]

    CSS = """
    SubjectTreeScreen {
        align: center middle;
    }

    #tree-dialog {
        width: 70%;
        height: 80%;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }

    #tree-title {
        text-style: bold;
        text-align: center;
        padding-bottom: 1;
    }

    #subject-tree {
        height: 1fr;
        border: solid $primary-darken-2;
    }

    #tree-hint {
        text-align: center;
        color: $text-muted;
        padding-top: 1;
    }
    """

    def __init__(self, root: SubjectNode) -> None:
        super().__init__()
        self.root = root

    def compose(self) -> ComposeResult:
        with Container(id="tree-dialog"):
            yield Label("Subject Tree", id="tree-title")
            yield Tree("Subjects", id="subject-tree")
            yield Label("Enter: filter to subject | q: close", id="tree-hint")

    def on_mount(self) -> None:
        """Build the tree from subject nodes."""
        tree = self.query_one("#subject-tree", Tree)
        tree.root.expand()

        # Add nodes recursively
        self._populate_tree(tree.root, self.root)

        # Expand first level
        for child in tree.root.children:
            child.expand()

    def _populate_tree(
        self, tree_node: TreeNode[str], subject_node: SubjectNode
    ) -> None:
        """Recursively add children to the tree."""
        # Sort by name
        for name in sorted(subject_node.children.keys()):
            child = subject_node.children[name]
            # Create label with count
            if child.count > 0:
                label = f"{name} ({child.count})"
            else:
                label = name

            # Add node with full subject as data
            if child.children:
                # Has children - add as expandable
                new_node = tree_node.add(label, data=child.full_subject)
                self._populate_tree(new_node, child)
            else:
                # Leaf node
                tree_node.add_leaf(label, data=child.full_subject)

    def on_tree_node_selected(self, event: Tree.NodeSelected[str]) -> None:
        """Handle node selection - set filter to that subject."""
        if event.node.data:
            # Check if has children - if so, use wildcard
            if event.node.children:
                self.dismiss(f"{event.node.data}.>")
            else:
                self.dismiss(event.node.data)

    def action_dismiss_none(self) -> None:
        """Dismiss without setting filter."""
        self.dismiss(None)

    def action_cursor_down(self) -> None:
        """Move cursor down."""
        tree = self.query_one("#subject-tree", Tree)
        tree.action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up."""
        tree = self.query_one("#subject-tree", Tree)
        tree.action_cursor_up()


class FilterInput(Input):
    """Input widget for filtering messages."""

    CSS = """
    FilterInput {
        dock: top;
        display: none;
    }

    FilterInput.visible {
        display: block;
    }
    """


class NatsVisApp(App[None]):
    """A TUI application for visualizing NATS messages."""

    TITLE = "NATS Message Visualizer"

    CSS = """
    #main-container {
        height: 1fr;
    }

    DataTable {
        height: 1fr;
    }

    DataTable > .datatable--cursor {
        background: $primary 40%;
    }

    #status-bar {
        dock: bottom;
        height: 1;
        background: $primary-darken-2;
        color: $text;
        padding: 0 1;
    }

    .paused {
        background: $warning;
        color: $background;
    }

    .bookmarked {
        color: $warning;
    }
    """

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("?", "help", "Help"),
        Binding("c", "clear", "Clear"),
        Binding("p", "toggle_pause", "Pause"),
        Binding("slash", "start_filter", "Filter"),
        Binding("escape", "clear_filter", "Clear Filter", show=False),
        Binding("t", "filter_type", "Type Filter"),
        Binding("i", "connection_info", "Info"),
        Binding("r", "republish", "Republish", show=False),
        Binding("e", "export", "Export"),
        Binding("E", "export_filtered", "Export Filtered", show=False),
        Binding("m", "toggle_bookmark", "Bookmark", show=False),
        Binding("n", "next_bookmark", "Next Bookmark", show=False),
        Binding("N", "prev_bookmark", "Prev Bookmark", show=False),
        Binding("d", "diff_bookmarks", "Diff", show=False),
        Binding("y", "copy_payload", "Copy", show=False),
        Binding("Y", "copy_subject", "Copy Subject", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("g", "cursor_top", "Top", show=False),
        Binding("G", "cursor_bottom", "Bottom", show=False),
        Binding("T", "subject_tree", "Subject Tree"),
    ]

    def __init__(
        self,
        server_url: str | None = None,
        user: str | None = None,
        password: str | None = None,
        subject: str = ">",
        import_file: Path | None = None,
        theme: str = "monokai",
        hide: HideConfig | None = None,
        columns: ColumnsConfig | None = None,
        export_path: str | None = None,
        jetstream_config: JetStreamConfig | None = None,
    ) -> None:
        super().__init__()
        self.theme = theme
        self.hide = hide or HideConfig()
        self.columns = columns or ColumnsConfig()
        self.export_path = export_path
        self.import_file = import_file
        self.viewer_mode = import_file is not None
        self.server_url = server_url or ""
        self.subject = subject
        self.jetstream_config = jetstream_config
        self.subscriber: NatsSubscriber | None = None
        if not self.viewer_mode and server_url:
            self.subscriber = NatsSubscriber(
                server_url, user=user, password=password, subject=subject
            )
        self.paused = False
        self.filter_text = ""
        self.filter_type: MessageType | None = None
        self.filter_regex: re.Pattern[str] | None = None
        self.messages: list[StoredMessage] = []
        self.filtered_indices: list[int] = []
        self.bookmark_indices: list[int] = []
        # Map reply_to subject -> request message index for RPC tracking
        self._pending_requests: dict[str, int] = {}
        # Double-press confirmation for clear
        self._last_clear_press: float | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        yield FilterInput(placeholder="Filter (text or /regex/)...", id="filter")
        with Container(id="main-container"):
            yield DataTable()
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        # Build columns based on config
        cols = []
        if self.columns.marker:
            cols.append("★")
        if self.columns.time:
            cols.append("Time")
        if self.columns.type:
            cols.append("Type")
        if self.columns.subject:
            cols.append("Subject")
        if self.columns.latency:
            cols.append("Latency")
        if self.columns.payload:
            cols.append("Payload")
        table.add_columns(*cols)
        table.cursor_type = "row"

        if self.viewer_mode and self.import_file:
            # Load imported messages
            self.sub_title = "Viewer Mode"
            self._load_import_file(self.import_file)
        else:
            # Connect to NATS
            self.run_worker(self._subscribe_messages(), exclusive=True)

        self._update_status()

    def _update_status(self) -> None:
        """Update the status bar."""
        status = self.query_one("#status-bar", Static)

        if self.viewer_mode:
            filename = self.import_file.name if self.import_file else "unknown"
            parts = [f"Viewing: {filename}"]
        else:
            parts = [f"Sub: {self.subject}"]

            if self.paused:
                parts.append("[PAUSED]")
                status.add_class("paused")
            else:
                status.remove_class("paused")

        if self.filter_text:
            parts.append(f"Filter: {self.filter_text}")

        if self.filter_type:
            parts.append(f"Type: {self.filter_type.value}")

        if not self.viewer_mode and self.subscriber:
            pending = self.subscriber.rpc_tracker.pending_count
            if pending > 0:
                parts.append(f"Pending: {pending}")

        bookmarks = len(self.bookmark_indices)
        if bookmarks > 0:
            parts.append(f"Bookmarks: {bookmarks}")

        parts.append(f"Msgs: {len(self.messages)}")

        status.update(" | ".join(parts))

    async def _subscribe_messages(self) -> None:
        """Background worker to subscribe to NATS messages."""
        if not self.subscriber:
            return

        try:
            await self.subscriber.connect()

            if self.jetstream_config:
                # JetStream mode
                stream = self.jetstream_config.stream
                policy = self.jetstream_config.deliver_policy.value
                self.sub_title = f"JetStream: {stream} ({policy})"

                async for msg in self.subscriber.subscribe_jetstream(
                    self.jetstream_config
                ):
                    if not self.paused:
                        self._add_message(msg)
                    self._update_status()
            else:
                # Normal NATS subscription
                self.sub_title = f"Connected to {self.server_url}"

                async for msg in self.subscriber.subscribe_all():
                    if not self.paused:
                        self._add_message(msg)
                    self._update_status()

        except Exception as e:
            self.sub_title = f"Error: {e}"

    def _load_import_file(self, path: Path) -> None:
        """Load messages from an import file (JSON or NATS CLI format)."""
        try:
            content = path.read_text()

            # Try JSON format first
            try:
                data = json.loads(content)
                if isinstance(data, list):
                    self._import_json_format(data)
                    self.notify(f"Imported {len(data)} messages")
                    return
            except json.JSONDecodeError:
                pass

            # Try NATS CLI format
            messages = self._parse_nats_cli_format(content)
            if messages:
                for msg in messages:
                    self._add_message(msg, imported=True)
                self.notify(f"Imported {len(messages)} messages")
            else:
                self.notify("No messages found in file", severity="warning")

        except Exception as e:
            self.notify(f"Import failed: {e}", severity="error")

    def _import_json_format(self, data: list[dict[str, object]]) -> None:
        """Import messages from our JSON export format."""
        type_map = {
            "PUB": MessageType.PUBLISH,
            "REQ": MessageType.REQUEST,
            "RES": MessageType.RESPONSE,
        }

        for item in data:
            try:
                # Parse timestamp
                timestamp_str = str(item.get("timestamp", ""))
                try:
                    timestamp = datetime.fromisoformat(timestamp_str)
                except ValueError:
                    timestamp = datetime.now()

                # Parse message type
                type_str = str(item.get("type", "PUB"))
                msg_type = type_map.get(type_str, MessageType.PUBLISH)

                # Parse headers
                headers_raw = item.get("headers", {})
                headers = (
                    {str(k): str(v) for k, v in headers_raw.items()}
                    if isinstance(headers_raw, dict)
                    else {}
                )

                # Parse latency
                latency_raw = item.get("latency_ms")
                latency_ms: float | None = None
                if latency_raw is not None:
                    try:
                        latency_ms = float(str(latency_raw))
                    except ValueError:
                        pass

                msg = NatsMessage(
                    subject=str(item.get("subject", "")),
                    payload=str(item.get("payload", "")),
                    timestamp=timestamp,
                    reply_to=str(item.get("reply_to"))
                    if item.get("reply_to")
                    else None,
                    headers=headers,
                    message_type=msg_type,
                    latency_ms=latency_ms,
                    request_subject=str(item.get("request_subject"))
                    if item.get("request_subject")
                    else None,
                )
                self._add_message(msg, imported=True)
            except Exception:
                continue  # Skip malformed entries

    def _parse_nats_cli_format(self, content: str) -> list[NatsMessage]:
        """Parse NATS CLI output format into messages."""
        messages: list[NatsMessage] = []
        lines = content.split("\n")

        i = 0
        while i < len(lines):
            line = lines[i].strip()

            # Look for message start: [#N] Received ...
            if not line.startswith("[#") or "] Received" not in line:
                i += 1
                continue

            subject = ""
            reply_to: str | None = None
            headers: dict[str, str] = {}
            payload_lines: list[str] = []

            # Parse the "Received" line
            if "Received on " in line:
                # Format: [#N] Received on "subject" with reply "reply-to"
                match = re.search(r'Received on "([^"]+)"', line)
                if match:
                    subject = match.group(1)
                reply_match = re.search(r'with reply "([^"]+)"', line)
                if reply_match:
                    reply_to = reply_match.group(1)
            elif "Received JetStream message:" in line:
                # Format: [#N] Received JetStream message: ... / subject: X / ...
                match = re.search(r"subject: ([^\s/]+)", line)
                if match:
                    subject = match.group(1)

            i += 1

            # Parse headers (Key: Value format) until empty line
            while i < len(lines) and lines[i].strip():
                header_line = lines[i].strip()
                if ": " in header_line and not header_line.startswith("{"):
                    key, _, value = header_line.partition(": ")
                    headers[key] = value
                else:
                    # This might be the start of payload
                    break
                i += 1

            # Skip empty line
            if i < len(lines) and not lines[i].strip():
                i += 1

            # Collect payload until next message or end
            while i < len(lines):
                next_line = lines[i]
                if next_line.strip().startswith("[#") and "] Received" in next_line:
                    break
                payload_lines.append(next_line)
                i += 1

            # Build payload
            payload = "\n".join(payload_lines).strip()
            if payload == "nil body":
                payload = ""

            # Determine message type
            if reply_to:
                msg_type = MessageType.REQUEST
            elif subject.startswith("_INBOX."):
                msg_type = MessageType.RESPONSE
            elif subject.startswith("$JS.ACK."):
                msg_type = MessageType.PUBLISH
            else:
                msg_type = MessageType.PUBLISH

            if subject:
                messages.append(
                    NatsMessage(
                        subject=subject,
                        payload=payload,
                        timestamp=datetime.now(),
                        reply_to=reply_to,
                        headers=headers,
                        message_type=msg_type,
                    )
                )

        return messages

    def _add_message(self, msg: NatsMessage, imported: bool = False) -> None:
        """Add a message to the table."""
        table = self.query_one(DataTable)

        time_str = msg.timestamp.strftime("%H:%M:%S.%f")[:-3]
        type_str = msg.message_type.value
        latency_str = f"{msg.latency_ms:.1f}ms" if msg.latency_ms else ""

        # Truncate payload for display
        payload_display = msg.payload.replace("\n", " ")[:80]
        if len(msg.payload) > 80:
            payload_display += "..."

        stored = StoredMessage(msg=msg, row_key=None, imported=imported)
        msg_index = len(self.messages)
        self.messages.append(stored)

        # Track request/response relationships
        if msg.reply_to:
            # This is a request - track it for later matching
            self._pending_requests[msg.reply_to] = msg_index

        if (
            msg.subject.startswith("_INBOX.")
            or msg.message_type == MessageType.RESPONSE
        ):
            # This might be a response - check if we have the matching request
            if msg.subject in self._pending_requests:
                request_index = self._pending_requests.pop(msg.subject)
                # Link both messages together
                stored.related_index = request_index
                self.messages[request_index].related_index = msg_index

        # Check if internal message should be hidden (but RPC tracking above still happens)
        if self.hide.inbox and msg.subject.startswith("_INBOX."):
            return
        if self.hide.jetstream and msg.subject.startswith("$JS."):
            return

        # Check filters
        if not self._matches_filter(msg):
            return

        # Build row data based on enabled columns
        marker = Text("I", style=Style(color="bright_black")) if imported else ""
        row_data: list[str | Text] = []
        if self.columns.marker:
            row_data.append(marker)
        if self.columns.time:
            row_data.append(time_str)
        if self.columns.type:
            row_data.append(type_str)
        if self.columns.subject:
            row_data.append(msg.subject)
        if self.columns.latency:
            row_data.append(latency_str)
        if self.columns.payload:
            row_data.append(payload_display)

        row_key = table.add_row(*row_data)
        stored.row_key = row_key
        self.filtered_indices.append(msg_index)

        if not self.paused:
            table.scroll_end()

    def _matches_filter(self, msg: NatsMessage) -> bool:
        """Check if message matches current filters."""
        # Type filter
        if self.filter_type and msg.message_type != self.filter_type:
            return False

        # Text/regex filter
        if self.filter_text:
            if self.filter_regex:
                if not (
                    self.filter_regex.search(msg.subject)
                    or self.filter_regex.search(msg.payload)
                ):
                    return False
            elif ">" in self.filter_text or "*" in self.filter_text:
                # NATS subject wildcard pattern
                if not self._matches_subject_pattern(msg.subject, self.filter_text):
                    return False
            else:
                filter_lower = self.filter_text.lower()
                if (
                    filter_lower not in msg.subject.lower()
                    and filter_lower not in msg.payload.lower()
                ):
                    return False

        return True

    def _matches_subject_pattern(self, subject: str, pattern: str) -> bool:
        """Check if subject matches NATS wildcard pattern."""
        # Convert NATS wildcards to regex
        # * matches a single token (no dots)
        # > matches one or more tokens (greedy, only at end)
        regex_pattern = (
            pattern.replace(".", r"\.").replace("*", r"[^.]+").replace(">", r".+")
        )
        try:
            return bool(re.match(f"^{regex_pattern}$", subject))
        except re.error:
            return False

    def _get_selected_index(self) -> int | None:
        """Get the index into self.messages for the selected row."""
        table = self.query_one(DataTable)
        if table.cursor_row is None or table.cursor_row < 0:
            return None
        if 0 <= table.cursor_row < len(self.filtered_indices):
            return self.filtered_indices[table.cursor_row]
        return None

    def _get_selected_message(self) -> NatsMessage | None:
        """Get the currently selected message."""
        idx = self._get_selected_index()
        if idx is not None and 0 <= idx < len(self.messages):
            return self.messages[idx].msg
        return None

    def _get_selected_stored(self) -> StoredMessage | None:
        """Get the currently selected stored message."""
        idx = self._get_selected_index()
        if idx is not None and 0 <= idx < len(self.messages):
            return self.messages[idx]
        return None

    async def on_unmount(self) -> None:
        if self.subscriber:
            await self.subscriber.disconnect()

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle Enter key on a selected row."""
        stored = self._get_selected_stored()
        if stored:
            self._show_message_detail(stored)

    def _show_message_detail(self, stored: StoredMessage) -> None:
        """Show the message detail screen and handle navigation."""

        def handle_result(result: int | None) -> None:
            if result is not None and 0 <= result < len(self.messages):
                # Navigate to the related message
                related_stored = self.messages[result]
                self._show_message_detail(related_stored)

        self.push_screen(MessageDetailScreen(stored), handle_result)

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle filter input submission."""
        if event.input.id == "filter":
            self.filter_text = event.value

            # Check if regex pattern (surrounded by /)
            if (
                event.value.startswith("/")
                and event.value.endswith("/")
                and len(event.value) > 2
            ):
                try:
                    self.filter_regex = re.compile(event.value[1:-1], re.IGNORECASE)
                except re.error:
                    self.filter_regex = None
                    self.notify("Invalid regex pattern", severity="error")
            else:
                self.filter_regex = None

            self._apply_filter()
            event.input.remove_class("visible")
            self.query_one(DataTable).focus()

    def _apply_filter(self) -> None:
        """Apply the current filter to messages."""
        table = self.query_one(DataTable)
        table.clear()
        self.filtered_indices.clear()

        for i, stored in enumerate(self.messages):
            msg = stored.msg

            # Skip internal messages if hidden
            if self.hide.inbox and msg.subject.startswith("_INBOX."):
                stored.row_key = None
                continue
            if self.hide.jetstream and msg.subject.startswith("$JS."):
                stored.row_key = None
                continue

            if self._matches_filter(msg):
                time_str = msg.timestamp.strftime("%H:%M:%S.%f")[:-3]
                type_str = msg.message_type.value
                latency_str = f"{msg.latency_ms:.1f}ms" if msg.latency_ms else ""
                payload_display = msg.payload.replace("\n", " ")[:80]
                if len(msg.payload) > 80:
                    payload_display += "..."

                # First column: bookmark takes precedence, then imported marker
                if stored.bookmarked:
                    marker = Text("★", style=Style(color="yellow", bold=True))
                elif stored.imported:
                    marker = Text("I", style=Style(color="bright_black"))
                else:
                    marker = Text("")

                # Build row data based on enabled columns
                row_data: list[str | Text] = []
                if self.columns.marker:
                    row_data.append(marker)
                if self.columns.time:
                    row_data.append(time_str)
                if self.columns.type:
                    row_data.append(type_str)
                if self.columns.subject:
                    row_data.append(msg.subject)
                if self.columns.latency:
                    row_data.append(latency_str)
                if self.columns.payload:
                    row_data.append(payload_display)

                row_key = table.add_row(*row_data)
                stored.row_key = row_key
                self.filtered_indices.append(i)

        self._update_status()

    def _update_bookmark_display(self, stored: StoredMessage) -> None:
        """Update the bookmark marker for a row."""
        # Only update if marker column is enabled
        if not self.columns.marker:
            return

        table = self.query_one(DataTable)
        if stored.row_key is not None:
            # Bookmark takes precedence, then imported marker
            if stored.bookmarked:
                marker = Text("★", style=Style(color="yellow", bold=True))
            elif stored.imported:
                marker = Text("I", style=Style(color="bright_black"))
            else:
                marker = Text("")
            # Get column key for first column (marker column)
            columns = list(table.columns.keys())
            if columns:
                table.update_cell(stored.row_key, columns[0], marker)
                table.refresh()

    def action_help(self) -> None:
        """Show help screen."""
        self.push_screen(HelpScreen())

    def action_clear(self) -> None:
        """Clear all messages (requires double-press)."""
        now = time.monotonic()
        if self._last_clear_press is not None and (now - self._last_clear_press) < 1.5:
            # Second press within 1.5 seconds - clear messages
            table = self.query_one(DataTable)
            table.clear()
            self.messages.clear()
            self.filtered_indices.clear()
            self.bookmark_indices.clear()
            self._last_clear_press = None
            self._update_status()
            self.notify("Messages cleared")
        else:
            # First press - show confirmation
            self._last_clear_press = now
            self.notify("Press c again to clear all messages")

    def action_toggle_pause(self) -> None:
        """Toggle pause state."""
        if self.viewer_mode:
            self.notify("Not available in viewer mode", severity="warning")
            return
        self.paused = not self.paused
        self._update_status()
        if self.paused:
            self.notify("Paused - press p to resume")
        else:
            self.notify("Resumed")

    def action_start_filter(self) -> None:
        """Start filtering."""
        filter_input = self.query_one("#filter", FilterInput)
        filter_input.add_class("visible")
        filter_input.value = self.filter_text
        filter_input.focus()

    def action_clear_filter(self) -> None:
        """Clear the filter."""
        filter_input = self.query_one("#filter", FilterInput)
        if filter_input.has_class("visible"):
            filter_input.remove_class("visible")
            filter_input.value = ""
            self.query_one(DataTable).focus()
            return

        if self.filter_text or self.filter_type:
            self.filter_text = ""
            self.filter_regex = None
            self.filter_type = None
            self._apply_filter()
            self.notify("Filters cleared")

    def action_filter_type(self) -> None:
        """Cycle through message type filters."""
        types = [None, MessageType.REQUEST, MessageType.RESPONSE, MessageType.PUBLISH]
        current_idx = types.index(self.filter_type) if self.filter_type in types else 0
        self.filter_type = types[(current_idx + 1) % len(types)]
        self._apply_filter()

        type_name = self.filter_type.value if self.filter_type else "All"
        self.notify(f"Type filter: {type_name}")

    def action_connection_info(self) -> None:
        """Show connection info screen."""
        if self.viewer_mode:
            self.notify(
                f"Viewing: {self.import_file.name if self.import_file else 'unknown'} | {len(self.messages)} messages"
            )
            return
        if self.subscriber:
            self.push_screen(
                ConnectionInfoScreen(self.subscriber, self.subject, len(self.messages))
            )

    def action_republish(self) -> None:
        """Republish the selected message."""
        if self.viewer_mode or not self.subscriber:
            self.notify("Not available in viewer mode", severity="warning")
            return
        msg = self._get_selected_message()
        if msg:
            self.push_screen(
                PublishScreen(
                    self.subscriber,
                    default_subject=msg.subject,
                    default_payload=msg.payload,
                )
            )

    def action_export(self) -> None:
        """Export all messages."""
        self.push_screen(ExportScreen(self.messages, default_path=self.export_path))

    def action_export_filtered(self) -> None:
        """Export filtered messages only."""
        filtered = [self.messages[i] for i in self.filtered_indices]
        self.push_screen(
            ExportScreen(filtered, filtered_only=True, default_path=self.export_path)
        )

    def action_toggle_bookmark(self) -> None:
        """Toggle bookmark on current message."""
        stored = self._get_selected_stored()
        idx = self._get_selected_index()

        if stored and idx is not None:
            stored.bookmarked = not stored.bookmarked

            if stored.bookmarked:
                if idx not in self.bookmark_indices:
                    self.bookmark_indices.append(idx)
                    self.bookmark_indices.sort()
                self.notify("Bookmarked")
            else:
                if idx in self.bookmark_indices:
                    self.bookmark_indices.remove(idx)
                self.notify("Bookmark removed")

            self._update_bookmark_display(stored)
            self._update_status()
        else:
            self.notify("No message selected", severity="warning")

    def action_next_bookmark(self) -> None:
        """Go to next bookmarked message."""
        if not self.bookmark_indices:
            self.notify("No bookmarks")
            return

        current = self._get_selected_index()
        if current is None:
            current = -1

        # Find next bookmark after current
        for idx in self.bookmark_indices:
            if idx > current:
                # Find row in filtered indices
                if idx in self.filtered_indices:
                    row = self.filtered_indices.index(idx)
                    self.query_one(DataTable).move_cursor(row=row)
                    return

        # Wrap around to first
        idx = self.bookmark_indices[0]
        if idx in self.filtered_indices:
            row = self.filtered_indices.index(idx)
            self.query_one(DataTable).move_cursor(row=row)

    def action_prev_bookmark(self) -> None:
        """Go to previous bookmarked message."""
        if not self.bookmark_indices:
            self.notify("No bookmarks")
            return

        current = self._get_selected_index()
        if current is None:
            current = len(self.messages)

        # Find previous bookmark before current
        for idx in reversed(self.bookmark_indices):
            if idx < current:
                if idx in self.filtered_indices:
                    row = self.filtered_indices.index(idx)
                    self.query_one(DataTable).move_cursor(row=row)
                    return

        # Wrap around to last
        idx = self.bookmark_indices[-1]
        if idx in self.filtered_indices:
            row = self.filtered_indices.index(idx)
            self.query_one(DataTable).move_cursor(row=row)

    def action_diff_bookmarks(self) -> None:
        """Diff two bookmarked messages."""
        bookmarked = [
            self.messages[i] for i in self.bookmark_indices if i < len(self.messages)
        ]

        if len(bookmarked) < 2:
            self.notify(
                "Need at least 2 bookmarked messages to diff", severity="warning"
            )
            return

        # Use first two bookmarks
        self.push_screen(DiffScreen(bookmarked[0].msg, bookmarked[1].msg))

    def action_copy_payload(self) -> None:
        """Copy selected message payload to clipboard."""
        msg = self._get_selected_message()
        if msg:
            try:
                parsed = json.loads(msg.payload)
                text = json.dumps(parsed, indent=2)
            except json.JSONDecodeError:
                text = msg.payload
            self._copy_to_clipboard(text)
            self.notify("Payload copied")

    def action_copy_subject(self) -> None:
        """Copy selected message subject to clipboard."""
        msg = self._get_selected_message()
        if msg:
            self._copy_to_clipboard(msg.subject)
            self.notify("Subject copied")

    def _copy_to_clipboard(self, text: str) -> None:
        """Copy text to system clipboard."""
        try:
            subprocess.run(["pbcopy"], input=text.encode(), check=True)
        except (subprocess.SubprocessError, FileNotFoundError):
            try:
                subprocess.run(
                    ["xclip", "-selection", "clipboard"],
                    input=text.encode(),
                    check=True,
                )
            except (subprocess.SubprocessError, FileNotFoundError):
                self.notify("Clipboard not available", severity="warning")

    def action_cursor_down(self) -> None:
        """Move cursor down (vim j)."""
        self.query_one(DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up (vim k)."""
        self.query_one(DataTable).action_cursor_up()

    def action_cursor_top(self) -> None:
        """Move cursor to top (vim g)."""
        self.query_one(DataTable).move_cursor(row=0)

    def action_cursor_bottom(self) -> None:
        """Move cursor to bottom (vim G)."""
        table = self.query_one(DataTable)
        table.move_cursor(row=table.row_count - 1)

    def _build_subject_tree(self) -> SubjectNode:
        """Build a tree from all message subjects."""
        root = SubjectNode(name="", full_subject="", count=0, children={})

        for stored in self.messages:
            subject = stored.msg.subject

            # Skip hidden subjects
            if self.hide.inbox and subject.startswith("_INBOX."):
                continue
            if self.hide.jetstream and subject.startswith("$JS."):
                continue

            parts = subject.split(".")
            current = root

            for i, part in enumerate(parts):
                if part not in current.children:
                    full_subject = ".".join(parts[: i + 1])
                    current.children[part] = SubjectNode(
                        name=part, full_subject=full_subject, count=0, children={}
                    )
                current = current.children[part]

            # Increment count at leaf
            current.count += 1

        return root

    def action_subject_tree(self) -> None:
        """Show subject tree view."""
        if not self.messages:
            self.notify("No messages to show", severity="warning")
            return

        root = self._build_subject_tree()

        def handle_result(subject_pattern: str | None) -> None:
            if subject_pattern:
                # Set as filter
                self.filter_text = subject_pattern
                self.filter_regex = None
                self._apply_filter()
                self.notify(f"Filtering: {subject_pattern}")

        self.push_screen(SubjectTreeScreen(root), handle_result)
