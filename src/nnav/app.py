import json
import re
import time
from datetime import datetime
from pathlib import Path

from rich.style import Style
from rich.text import Text
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container
from textual.widgets import DataTable, Footer, Header, Input, Static
from textual.widgets.data_table import RowKey

from nnav.config import ColumnsConfig, HideConfig, ThemeConfig
from nnav.messages import load_messages
from nnav.nats_client import JetStreamConfig, MessageType, NatsMessage, NatsSubscriber
from nnav.themes import build_themes
from nnav.ui import (
    CURSOR_BINDINGS,
    FULLSCREEN_BINDING,
    FULLSCREEN_CSS,
    ConnectionInfoScreen,
    DiffScreen,
    ExportScreen,
    FilterInput,
    FilterMixin,
    FullscreenMixin,
    HelpScreen,
    MessageDetailScreen,
    PublishScreen,
    StoredMessage,
    SubjectNode,
    SubjectTreeScreen,
)
from nnav.utils.clipboard import copy_to_clipboard


class NatsVisApp(FilterMixin, FullscreenMixin, App[None]):
    TITLE = "nnav"

    CSS = """
    #main-container {
        height: 1fr;
        background: $background;
    }

    DataTable {
        height: 1fr;
        background: $background;
    }

    DataTable:focus {
        background: $background;
    }

    DataTable:focus-within {
        background: $background;
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

    BINDINGS = [
        Binding("q", "quit", "Quit"),
        Binding("?", "help", "Help"),
        Binding("c", "clear", "Clear"),
        Binding("p", "toggle_pause", "Pause"),
        Binding("f", "toggle_tail", "Tail"),
        Binding("slash", "start_filter", "Filter"),
        Binding("escape", "clear_filter", "Clear Filter", show=False),
        Binding("t", "filter_type", "Type Filter"),
        Binding("F", "toggle_fullscreen", "Fullscreen"),
        Binding("i", "connection_info", "Info"),
        Binding("r", "republish", "Republish", show=False),
        Binding("e", "export", "Export"),
        Binding("E", "export_filtered", "Export Filtered", show=False),
        Binding("m", "toggle_bookmark", "Mark"),
        Binding("n", "next_bookmark", "Next Mark"),
        Binding("N", "prev_bookmark", "Prev Mark", show=False),
        Binding("d", "diff_bookmarks", "Diff", show=False),
        Binding("y", "copy_payload", "Copy", show=False),
        Binding("Y", "copy_message", "Copy Message", show=False),
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
        preview_theme: str = "monokai",
        textual_theme: str = "textual-dark",
        fullscreen: bool = False,
        hide: HideConfig | None = None,
        columns: ColumnsConfig | None = None,
        export_path: str | None = None,
        jetstream_config: JetStreamConfig | None = None,
        theme_configs: list[ThemeConfig] | None = None,
    ) -> None:
        super().__init__()
        # Register custom themes from config before setting theme
        for custom_theme in build_themes(theme_configs or []):
            self.register_theme(custom_theme)
        self.theme = textual_theme
        self.preview_theme = preview_theme
        self._fullscreen = fullscreen
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
        self.tail_mode = True  # Auto-scroll to new messages
        self.filter_text = ""
        self.filter_type: MessageType | None = None
        self.include_terms: list[str] = []
        self.exclude_terms: list[str] = []
        self.include_regexes: list[re.Pattern[str] | None] = []
        self.exclude_regexes: list[re.Pattern[str] | None] = []
        self.messages: list[StoredMessage] = []
        self.filtered_indices: list[int] = []
        self.bookmark_indices: list[int] = []
        # Map reply_to subject -> request message index for RPC tracking
        self._pending_requests: dict[str, int] = {}
        # Double-press confirmation for clear
        self._last_clear_press: float | None = None

    def compose(self) -> ComposeResult:
        yield Header()
        with Container(id="main-container"):
            yield DataTable()
        yield FilterInput(placeholder="Filter (text or /regex/)...", id="filter")
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

        # Focus table after refresh to ensure CSS is applied
        self.call_after_refresh(table.focus)

        # Apply fullscreen mode if configured
        if self._fullscreen:
            self.add_class("fullscreen")

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

            if self.tail_mode:
                parts.append("[TAIL]")

        if self.include_terms:
            parts.append(f"Filter: {' '.join(self.include_terms)}")

        if self.exclude_terms:
            parts.append(f"Exclude: {' '.join(self.exclude_terms)}")

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
            messages = load_messages(path)
            if messages:
                for msg in messages:
                    self._add_message(msg, imported=True)
                self.notify(f"Imported {len(messages)} messages")
            else:
                self.notify("No messages found in file", severity="warning")
        except Exception as e:
            self.notify(f"Import failed: {e}", severity="error")

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

        # Auto-scroll only if tail mode is on
        if self.tail_mode:
            table.scroll_end()

    def _matches_filter(self, msg: NatsMessage) -> bool:
        """Check if message matches current filters."""
        # Type filter
        if self.filter_type and msg.message_type != self.filter_type:
            return False

        # Include terms - message must match ALL include terms
        for i, term in enumerate(self.include_terms):
            regex = self.include_regexes[i] if i < len(self.include_regexes) else None
            if not self._term_matches(term, msg, regex):
                return False

        # Exclude terms - message must NOT match ANY exclude term
        for i, term in enumerate(self.exclude_terms):
            regex = self.exclude_regexes[i] if i < len(self.exclude_regexes) else None
            if self._term_matches(term, msg, regex):
                return False

        return True

    def _term_matches(
        self, term: str, msg: NatsMessage, regex: re.Pattern[str] | None
    ) -> bool:
        """Check if a single term matches the message."""
        if regex:
            return bool(regex.search(msg.subject) or regex.search(msg.payload))
        elif ">" in term or "*" in term:
            return self._matches_subject_pattern(msg.subject, term)
        else:
            term_lower = term.lower()
            return term_lower in msg.subject.lower() or term_lower in msg.payload.lower()

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

        self.push_screen(
            MessageDetailScreen(
                stored, self.preview_theme, fullscreen=self._fullscreen
            ),
            handle_result,
        )

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle filter input submission."""
        if event.input.id == "filter":
            self.filter_text = event.value
            self._parse_filter_terms(event.value)
            self._apply_filter()
            if not event.value:  # Only hide if filter is empty
                event.input.remove_class("visible")
            self._focus_table()

    def _parse_filter_terms(self, filter_text: str) -> None:
        """Parse filter text into include and exclude terms with their regexes."""
        self.include_terms = []
        self.exclude_terms = []
        self.include_regexes = []
        self.exclude_regexes = []

        if not filter_text.strip():
            return

        # Split on spaces, but respect /regex/ boundaries
        terms = self._split_filter_terms(filter_text)

        for term in terms:
            if term.startswith("!"):
                pattern = term[1:]  # Remove ! prefix
                if pattern:  # Ignore lone !
                    self.exclude_terms.append(pattern)
                    self.exclude_regexes.append(self._compile_regex_term(pattern))
            else:
                if term:
                    self.include_terms.append(term)
                    self.include_regexes.append(self._compile_regex_term(term))

    def _split_filter_terms(self, filter_text: str) -> list[str]:
        """Split filter text on spaces, respecting /regex/ boundaries."""
        terms: list[str] = []
        current = ""
        in_regex = False

        for char in filter_text:
            if char == "/" and not in_regex:
                in_regex = True
                current += char
            elif char == "/" and in_regex:
                in_regex = False
                current += char
            elif char == " " and not in_regex:
                if current:
                    terms.append(current)
                    current = ""
            else:
                current += char

        if current:
            terms.append(current)

        return terms

    def _compile_regex_term(self, term: str) -> re.Pattern[str] | None:
        """Compile a term as regex if it's in /pattern/ format."""
        if term.startswith("/") and term.endswith("/") and len(term) > 2:
            try:
                return re.compile(term[1:-1], re.IGNORECASE)
            except re.error:
                self.notify(f"Invalid regex: {term}", severity="error")
                return None
        return None

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
            row_key = stored.row_key
            if columns and isinstance(row_key, RowKey):
                table.update_cell(row_key, columns[0], marker)
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

    def action_toggle_tail(self) -> None:
        """Toggle tail mode (auto-scroll to new messages)."""
        self.tail_mode = not self.tail_mode
        self._update_status()
        if self.tail_mode:
            self.notify("Tail mode on - following new messages")
            self.query_one(DataTable).scroll_end()
        else:
            self.notify("Tail mode off - scroll freely")

    def action_clear_filter(self) -> None:
        """Clear the filter and hide input."""
        self._hide_filter_input()

        # Clear filter state
        if self.filter_text or self.filter_type or self.include_terms or self.exclude_terms:
            self.filter_text = ""
            self.include_terms = []
            self.exclude_terms = []
            self.include_regexes = []
            self.exclude_regexes = []
            self.filter_type = None
            self._apply_filter()
            self.notify("Filters cleared")

        self._focus_table()

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
        self.push_screen(
            DiffScreen(bookmarked[0].msg, bookmarked[1].msg, self.preview_theme)
        )

    def action_copy_payload(self) -> None:
        """Copy selected message payload to clipboard."""
        msg = self._get_selected_message()
        if msg:
            try:
                parsed = json.loads(msg.payload)
                text = json.dumps(parsed, indent=2)
            except json.JSONDecodeError:
                text = msg.payload
            if copy_to_clipboard(text):
                self.notify("Payload copied")
            else:
                self.notify("Clipboard not available", severity="warning")

    def _message_to_dict(self, msg: NatsMessage) -> dict[str, object]:
        """Convert a message to a dictionary for JSON serialization."""
        try:
            payload = json.loads(msg.payload)
        except json.JSONDecodeError:
            payload = msg.payload

        data: dict[str, object] = {"subject": msg.subject}
        if msg.reply_to:
            data["reply_to"] = msg.reply_to
        if msg.headers:
            data["headers"] = msg.headers
        data["payload"] = payload
        return data

    def action_copy_message(self) -> None:
        """Copy full message as JSON to clipboard."""
        stored = self._get_selected_stored()
        if stored:
            data = self._message_to_dict(stored.msg)

            # Include related request/response if available
            if stored.related_index is not None and 0 <= stored.related_index < len(self.messages):
                related = self.messages[stored.related_index].msg
                key = "response" if stored.msg.message_type == MessageType.REQUEST else "request"
                data[key] = self._message_to_dict(related)

            if copy_to_clipboard(json.dumps(data, indent=2)):
                self.notify("Message copied")
            else:
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
