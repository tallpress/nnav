"""Modal screens for nnav TUI."""

from __future__ import annotations

import asyncio
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

from rich.markup import escape as rich_escape
from rich.syntax import Syntax
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, ScrollableContainer, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    Button,
    DataTable,
    Input,
    Label,
    Static,
    TextArea,
    Tree,
)
from textual.widgets.tree import TreeNode

from nnav.nats_client import MessageType, NatsMessage
from nnav.utils.clipboard import copy_to_clipboard

if TYPE_CHECKING:
    from nnav.nats_client import NatsSubscriber


@dataclass
class StoredMessage:
    """Message stored with row key for retrieval."""

    msg: NatsMessage
    row_key: object | None
    bookmarked: bool = False
    related_index: int | None = None  # Index of matching request/response
    imported: bool = False  # True for messages loaded from file


@dataclass
class SubjectNode:
    """Node in the subject tree."""

    name: str
    full_subject: str
    count: int
    children: dict[str, SubjectNode]


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
            yield Label("nnav - Keyboard Shortcuts", id="help-title")

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
                "  /          Filter messages (text, /regex/, !exclude)", classes="help-row"
            )
            yield Label("             !pattern excludes matching messages", classes="help-row")
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
            yield Label("  F          Toggle fullscreen", classes="help-row")
            yield Label("  i          Show connection info", classes="help-row")
            yield Label("  ?          Show this help", classes="help-row")
            yield Label("  q          Quit", classes="help-row")

            yield Label("In Message Detail View", classes="help-section")
            yield Label("  j / k      Scroll down / up", classes="help-row")
            yield Label("  g / G      Scroll to top / bottom", classes="help-row")
            yield Label("  /          JSON path query", classes="help-row")
            yield Label("  :          Pipe to shell command", classes="help-row")
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
        Binding("colon", "pipe_command", "Pipe"),
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

    #pipe-command-container {
        height: auto;
        display: none;
        padding: 1;
        background: $surface-darken-1;
    }

    #pipe-command-container.visible {
        display: block;
    }

    #pipe-command-input {
        width: 100%;
    }

    #transform-label {
        color: $warning;
        padding: 0 1;
        display: none;
    }

    #transform-label.visible {
        display: block;
    }

    #hint {
        text-align: center;
        color: $text-muted;
        padding: 1 0;
    }
    """

    def __init__(
        self,
        stored: StoredMessage,
        preview_theme: str = "monokai",
        fullscreen: bool = False,
    ) -> None:
        super().__init__()
        self.stored = stored
        self.msg = stored.msg
        self.preview_theme = preview_theme
        self.fullscreen = fullscreen
        self._parsed_json: dict[str, object] | list[object] | None = None
        self._is_json = False
        self._current_path: str | None = None
        self._current_result: object = None
        # Pipe command state
        self._pipe_output: str | None = None
        self._pipe_command: str | None = None
        self._showing_transformed: bool = False

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
                    if self.stored.related_index is not None and not self.fullscreen:
                        yield Label(
                            "  → Press 'r' to view response",
                            classes="meta-row meta-latency",
                        )
                if self.msg.request_subject:
                    yield Label(
                        f"Request Subject: {self.msg.request_subject}",
                        classes="meta-row",
                    )
                    if self.stored.related_index is not None and not self.fullscreen:
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
            yield Label("", id="transform-label")
            with ScrollableContainer(id="payload-container"):
                yield Static(id="payload")

            with Vertical(id="bottom-bar"):
                with Vertical(id="json-path-container"):
                    yield Input(
                        placeholder="Path: .user.name or .items[0] (empty to reset)",
                        id="json-path-input",
                    )
                with Vertical(id="pipe-command-container"):
                    yield Input(
                        placeholder="Shell command (payload piped to stdin)",
                        id="pipe-command-input",
                    )

                if not self.fullscreen:
                    hint_parts = ["q: close", "y: copy", "/: query", ":: pipe"]
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
            syntax = Syntax(
                formatted, "json", theme=self.preview_theme, line_numbers=False
            )
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
        """Escape: reset transform/query or close."""
        pipe_container = self.query_one("#pipe-command-container")
        json_container = self.query_one("#json-path-container")

        # Priority 1: Hide pipe command input if visible
        if pipe_container.has_class("visible"):
            pipe_container.remove_class("visible")
        # Priority 2: Reset transform if showing piped output
        elif self._showing_transformed:
            self._reset_from_transform()
        # Priority 3: Reset JSON path if active
        elif self._current_path is not None:
            self._reset_to_full_payload()
            json_container.remove_class("visible")
        # Priority 4: Hide JSON path input if visible
        elif json_container.has_class("visible"):
            json_container.remove_class("visible")
        # Priority 5: Dismiss screen
        else:
            self.dismiss(None)

    def action_focus_query_or_close(self) -> None:
        """Enter: focus query input if visible, otherwise close."""
        container = self.query_one("#json-path-container")
        if container.has_class("visible"):
            self.query_one("#json-path-input", Input).focus()
        else:
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
        """Copy payload to clipboard. Copies transform/query result if active."""
        if self._showing_transformed and self._pipe_output is not None:
            copy_to_clipboard(self._pipe_output)
            self.notify("Copied piped output")
        elif self._current_path is not None and self._current_result is not None:
            if isinstance(self._current_result, (dict, list)):
                text = json.dumps(self._current_result, indent=2)
            else:
                text = str(self._current_result)
            copy_to_clipboard(text)
            self.notify(f"Copied: {self._current_path}")
        elif self._is_json and self._parsed_json is not None:
            text = json.dumps(self._parsed_json, indent=2)
            copy_to_clipboard(text)
            self.notify("Payload copied to clipboard")
        else:
            copy_to_clipboard(self.msg.payload)
            self.notify("Payload copied to clipboard")

    def action_copy_subject(self) -> None:
        """Copy subject to clipboard."""
        copy_to_clipboard(self.msg.subject)
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
            input_widget.value = self._current_path or ""
            input_widget.focus()
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
        """Handle JSON path query or pipe command."""
        if event.input.id == "json-path-input":
            path = event.value.strip()
            if path:
                self._execute_json_path(path)
                self.set_focus(None)
            else:
                self._reset_to_full_payload()
                self.query_one("#json-path-container").remove_class("visible")
                self.set_focus(None)
        elif event.input.id == "pipe-command-input":
            command = event.value.strip()
            if command:
                self.run_worker(self._execute_pipe_command(command))
                self.query_one("#pipe-command-container").remove_class("visible")
                self.set_focus(None)
            else:
                self.query_one("#pipe-command-container").remove_class("visible")

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

            path_label.update(f"Query: {path}")
            path_label.add_class("visible")

            if isinstance(result, (dict, list)):
                formatted = json.dumps(result, indent=2)
                syntax = Syntax(
                    formatted, "json", theme=self.preview_theme, line_numbers=False
                )
                payload_widget.update(syntax)
            elif isinstance(result, str):
                payload_widget.update(Text(f'"{result}"', style="green"))
            else:
                payload_widget.update(Text(str(result), style="cyan"))

            self.notify(f"Showing: {path}")
        except Exception as e:
            self.notify(f"Error: {e}", severity="error")

    def _get_json_path(self, data: object, path: str) -> object:
        """Extract value at JSON path. Supports .key, [index], and combinations."""
        path = path.strip()
        if path.startswith("$"):
            path = path[1:]
        if path.startswith("."):
            path = path[1:]

        if not path:
            return data

        current: object = data
        tokens = re.findall(r"\.?([^.\[\]]+)|\[(\d+)\]", path)

        for token in tokens:
            key, index = token
            if key:
                if isinstance(current, dict):
                    if key not in current:
                        raise KeyError(f"Key '{key}' not found")
                    current = current[key]
                else:
                    raise TypeError(
                        f"Cannot access key '{key}' on {type(current).__name__}"
                    )
            elif index:
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

    def action_pipe_command(self) -> None:
        """Toggle pipe command input."""
        container = self.query_one("#pipe-command-container")
        container.toggle_class("visible")

        if container.has_class("visible"):
            input_widget = self.query_one("#pipe-command-input", Input)
            input_widget.value = ""
            input_widget.focus()

    def _get_pipeable_content(self) -> str:
        """Get content to pipe - query result if active, otherwise full payload."""
        if self._current_path is not None and self._current_result is not None:
            if isinstance(self._current_result, (dict, list)):
                return json.dumps(self._current_result, indent=2)
            return str(self._current_result)
        elif self._is_json and self._parsed_json is not None:
            return json.dumps(self._parsed_json, indent=2)
        return self.msg.payload

    async def _execute_pipe_command(self, command: str) -> None:
        """Execute shell command with payload as stdin."""
        content = self._get_pipeable_content()

        try:
            process = await asyncio.create_subprocess_shell(
                command,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout, stderr = await process.communicate(content.encode())

            self._pipe_command = command
            self._pipe_output = stdout.decode("utf-8", errors="replace")

            if stderr:
                stderr_text = stderr.decode("utf-8", errors="replace").strip()
                if stderr_text:
                    self.notify(f"stderr: {stderr_text[:100]}", severity="warning")

            self._display_pipe_result()

        except Exception as e:
            self.notify(f"Command failed: {e}", severity="error")

    def _display_pipe_result(self) -> None:
        """Display the piped command output."""
        payload_widget = self.query_one("#payload", Static)
        transform_label = self.query_one("#transform-label", Label)

        self._showing_transformed = True
        transform_label.update(f"Pipe: {self._pipe_command}")
        transform_label.add_class("visible")

        output = self._pipe_output or ""

        # Try to detect if output is JSON for syntax highlighting
        try:
            parsed = json.loads(output)
            formatted = json.dumps(parsed, indent=2)
            syntax = Syntax(
                formatted, "json", theme=self.preview_theme, line_numbers=False
            )
            payload_widget.update(syntax)
        except (json.JSONDecodeError, TypeError):
            # Not JSON - display as plain text
            payload_widget.update(output)

    def _reset_from_transform(self) -> None:
        """Reset from transformed view back to original."""
        self._pipe_output = None
        self._pipe_command = None
        self._showing_transformed = False

        transform_label = self.query_one("#transform-label", Label)
        transform_label.update("")
        transform_label.remove_class("visible")

        # Restore original display (respect JSON path if still active)
        payload_widget = self.query_one("#payload", Static)
        if self._current_path is not None:
            self._execute_json_path(self._current_path)
        else:
            self._display_payload(payload_widget, self.msg.payload)

        self.notify("Showing original payload")


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

    def __init__(
        self, msg1: NatsMessage, msg2: NatsMessage, preview_theme: str = "monokai"
    ) -> None:
        super().__init__()
        self.msg1 = msg1
        self.msg2 = msg2
        self.preview_theme = preview_theme

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
            syntax = Syntax(
                formatted, "json", theme=self.preview_theme, line_numbers=False
            )
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
        messages: list[StoredMessage],
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


class SubjectTreeScreen(ModalScreen[str | None]):
    """Screen showing hierarchical subject tree."""

    BINDINGS = [
        Binding("escape", "dismiss_none", "Close"),
        Binding("q", "dismiss_none", "Close"),
        Binding("h", "toggle_histogram", "Histogram"),
        Binding("s", "toggle_sort", "Sort", show=False),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("down", "cursor_down", "Down", show=False),
        Binding("up", "cursor_up", "Up", show=False),
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

    #subject-tree.hidden {
        display: none;
    }

    #histogram-table {
        height: 1fr;
        border: solid $primary-darken-2;
        display: none;
    }

    #histogram-table.visible {
        display: block;
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
        self.histogram_mode = False
        self.sort_by_count = True
        self._flat_subjects: list[tuple[str, int]] = []

    def compose(self) -> ComposeResult:
        with Container(id="tree-dialog"):
            yield Label("Subject Tree", id="tree-title")
            yield Tree("Subjects", id="subject-tree")
            yield DataTable(id="histogram-table")
            yield Label("Enter: filter | h: histogram | q: close", id="tree-hint")

    def on_mount(self) -> None:
        """Build the tree from subject nodes."""
        tree = self.query_one("#subject-tree", Tree)
        tree.root.expand()

        self._populate_tree(tree.root, self.root)

        for child in tree.root.children:
            child.expand()

        self._flat_subjects = self._build_flat_subjects()

        table = self.query_one("#histogram-table", DataTable)
        table.add_columns("Subject", "Distribution", "Count")
        table.cursor_type = "row"

    def _populate_tree(
        self, tree_node: TreeNode[str], subject_node: SubjectNode
    ) -> None:
        """Recursively add children to the tree."""
        for name in sorted(subject_node.children.keys()):
            child = subject_node.children[name]
            if child.count > 0:
                label = f"{name} ({child.count})"
            else:
                label = name

            if child.children:
                new_node = tree_node.add(label, data=child.full_subject)
                self._populate_tree(new_node, child)
            else:
                tree_node.add_leaf(label, data=child.full_subject)

    def on_tree_node_selected(self, event: Tree.NodeSelected[str]) -> None:
        """Handle node selection - set filter to that subject."""
        if event.node.data:
            if event.node.children:
                self.dismiss(f"{event.node.data}.>")
            else:
                self.dismiss(event.node.data)

    def action_dismiss_none(self) -> None:
        """Dismiss without setting filter."""
        self.dismiss(None)

    def action_cursor_down(self) -> None:
        """Move cursor down."""
        if self.histogram_mode:
            self.query_one("#histogram-table", DataTable).action_cursor_down()
        else:
            self.query_one("#subject-tree", Tree).action_cursor_down()

    def action_cursor_up(self) -> None:
        """Move cursor up."""
        if self.histogram_mode:
            self.query_one("#histogram-table", DataTable).action_cursor_up()
        else:
            self.query_one("#subject-tree", Tree).action_cursor_up()

    def _build_flat_subjects(self) -> list[tuple[str, int]]:
        """Flatten tree to list of (subject, count) tuples."""
        results: list[tuple[str, int]] = []

        def walk(node: SubjectNode) -> None:
            if node.count > 0:
                results.append((node.full_subject, node.count))
            for child in node.children.values():
                walk(child)

        walk(self.root)
        return results

    def _populate_histogram(self) -> None:
        """Populate the histogram table."""
        table = self.query_one("#histogram-table", DataTable)
        table.clear()

        subjects = self._flat_subjects
        if self.sort_by_count:
            subjects = sorted(subjects, key=lambda x: -x[1])
        else:
            subjects = sorted(subjects, key=lambda x: x[0])

        if not subjects:
            return

        max_count = max(c for _, c in subjects)
        bar_width = 25

        for subject, count in subjects:
            bar_len = int((count / max_count) * bar_width) if max_count > 0 else 0
            bar = "█" * bar_len + "░" * (bar_width - bar_len)
            table.add_row(subject, bar, str(count), key=subject)

    def action_toggle_histogram(self) -> None:
        """Toggle between tree and histogram view."""
        self.histogram_mode = not self.histogram_mode
        tree = self.query_one("#subject-tree", Tree)
        table = self.query_one("#histogram-table", DataTable)
        title = self.query_one("#tree-title", Label)
        hint = self.query_one("#tree-hint", Label)

        if self.histogram_mode:
            tree.add_class("hidden")
            table.add_class("visible")
            self._populate_histogram()
            table.focus()
            title.update("Subject Histogram")
            hint.update("Enter: filter | h: tree view | s: sort | q: close")
        else:
            tree.remove_class("hidden")
            table.remove_class("visible")
            tree.focus()
            title.update("Subject Tree")
            hint.update("Enter: filter | h: histogram | q: close")

    def action_toggle_sort(self) -> None:
        """Toggle sort order in histogram mode."""
        if self.histogram_mode:
            self.sort_by_count = not self.sort_by_count
            self._populate_histogram()
            sort_type = "count" if self.sort_by_count else "name"
            self.notify(f"Sorted by {sort_type}")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle histogram row selection."""
        if event.row_key and event.row_key.value:
            self.dismiss(str(event.row_key.value))
