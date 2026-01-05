"""JetStream browser TUI for browsing streams and consumers."""

from __future__ import annotations

import nats
from nats.aio.client import Client
from nats.js import JetStreamContext
from nats.js.api import ConsumerInfo, StreamInfo
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import (
    DataTable,
    Footer,
    Header,
    Input,
    Label,
    OptionList,
    Static,
)
from textual.widgets.option_list import Option

from nnav.config import ColumnsConfig, HideConfig
from nnav.nats_client import JetStreamConfig, JetStreamDeliverPolicy
from nnav.themes import CUSTOM_THEMES
from nnav.ui import FilterInput, FullscreenMixin
from nnav.utils.formatting import format_bytes


class StartPositionScreen(ModalScreen[JetStreamConfig | None]):
    """Modal to select starting position for stream subscription."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("q", "cancel", "Cancel"),
        Binding("j", "cursor_down", "Down", show=False, priority=True),
        Binding("k", "cursor_up", "Up", show=False, priority=True),
    ]

    CSS = """
    StartPositionScreen {
        align: center middle;
    }

    #dialog {
        width: 60;
        height: auto;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }

    #title {
        text-style: bold;
        text-align: center;
        padding-bottom: 1;
    }

    #stream-info {
        color: $text-muted;
        padding-bottom: 1;
    }

    OptionList {
        height: auto;
        max-height: 10;
        margin-bottom: 1;
    }

    #seq-container {
        height: auto;
        display: none;
        padding: 1 0;
    }

    #seq-container.visible {
        display: block;
    }

    #hint {
        text-align: center;
        color: $text-muted;
        padding-top: 1;
    }
    """

    def __init__(self, stream_info: StreamInfo) -> None:
        super().__init__()
        self.stream_info = stream_info
        self.stream_name = stream_info.config.name or "unknown"
        self.selected_policy: JetStreamDeliverPolicy = JetStreamDeliverPolicy.NEW

    def compose(self) -> ComposeResult:
        msgs = self.stream_info.state.messages
        first_seq = self.stream_info.state.first_seq
        last_seq = self.stream_info.state.last_seq

        with Container(id="dialog"):
            yield Label(f"Stream: {self.stream_name}", id="title")
            yield Label(
                f"Messages: {msgs:,} | Seq: {first_seq} - {last_seq}",
                id="stream-info",
            )

            yield OptionList(
                Option("Latest (new messages only)", id="new"),
                Option("All (from beginning)", id="all"),
                Option("From sequence number...", id="seq"),
                id="options",
            )

            with Vertical(id="seq-container"):
                yield Label("Sequence number:")
                yield Input(placeholder="Enter sequence number", id="seq-input")

            yield Label("Enter: Select | Esc: Cancel", id="hint")

    def on_mount(self) -> None:
        self.query_one(OptionList).focus()

    def on_option_list_option_selected(self, event: OptionList.OptionSelected) -> None:
        option_id = event.option.id

        if option_id == "new":
            self.dismiss(
                JetStreamConfig(
                    stream=self.stream_name,
                    deliver_policy=JetStreamDeliverPolicy.NEW,
                )
            )
        elif option_id == "all":
            self.dismiss(
                JetStreamConfig(
                    stream=self.stream_name,
                    deliver_policy=JetStreamDeliverPolicy.ALL,
                )
            )
        elif option_id == "seq":
            # Show sequence input
            self.query_one("#seq-container").add_class("visible")
            self.query_one("#seq-input", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        if event.input.id == "seq-input":
            try:
                seq = int(event.value.strip())
                self.dismiss(
                    JetStreamConfig(
                        stream=self.stream_name,
                        deliver_policy=JetStreamDeliverPolicy.BY_START_SEQ,
                        start_sequence=seq,
                    )
                )
            except ValueError:
                self.notify("Invalid sequence number", severity="error")

    def action_cancel(self) -> None:
        self.dismiss(None)

    def action_cursor_down(self) -> None:
        self.query_one(OptionList).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one(OptionList).action_cursor_up()


class ConsumerListScreen(ModalScreen[None]):
    """Modal showing consumers for a stream."""

    BINDINGS = [
        Binding("escape", "dismiss", "Close"),
        Binding("q", "dismiss", "Close"),
        Binding("j", "cursor_down", "Down", show=False, priority=True),
        Binding("k", "cursor_up", "Up", show=False, priority=True),
    ]

    CSS = """
    ConsumerListScreen {
        align: center middle;
    }

    #dialog {
        width: 80;
        height: auto;
        max-height: 80%;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }

    #title {
        text-style: bold;
        text-align: center;
        padding-bottom: 1;
    }

    DataTable {
        height: auto;
        max-height: 20;
    }

    #hint {
        text-align: center;
        color: $text-muted;
        padding-top: 1;
    }
    """

    def __init__(self, stream_name: str, consumers: list[ConsumerInfo]) -> None:
        super().__init__()
        self.stream_name = stream_name
        self.consumers = consumers

    def compose(self) -> ComposeResult:
        with Container(id="dialog"):
            yield Label(f"Consumers: {self.stream_name}", id="title")
            yield DataTable()
            yield Label("Esc: Close | jk: Navigate", id="hint")

    def on_mount(self) -> None:
        table = self.query_one(DataTable)
        table.add_columns("Name", "Pending", "Ack Pending", "Redelivered", "Waiting")
        table.cursor_type = "row"

        for consumer in self.consumers:
            name = consumer.name or "?"
            pending = consumer.num_pending or 0
            ack_pending = consumer.num_ack_pending or 0
            redelivered = consumer.num_redelivered or 0
            waiting = consumer.num_waiting or 0
            table.add_row(name, str(pending), str(ack_pending), str(redelivered), str(waiting))

        table.focus()

    def action_cursor_down(self) -> None:
        self.query_one(DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one(DataTable).action_cursor_up()


class JetStreamApp(FullscreenMixin, App[JetStreamConfig | None]):
    """JetStream browser for viewing streams and consumers."""

    TITLE = "JetStream Browser"

    CSS = """
    #main-container {
        height: 1fr;
    }

    DataTable {
        height: 1fr;
    }

    #status-bar {
        dock: bottom;
        height: 1;
        padding: 0 1;
        background: $primary-background;
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
        Binding("r", "refresh", "Refresh"),
        Binding("c", "view_consumers", "Consumers"),
        Binding("slash", "start_filter", "Filter"),
        Binding("escape", "clear_filter", "Clear Filter", show=False),
        Binding("F", "toggle_fullscreen", "Fullscreen"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("g", "cursor_top", "Top", show=False),
        Binding("G", "cursor_bottom", "Bottom", show=False),
    ]

    def __init__(
        self,
        server_url: str,
        user: str | None = None,
        password: str | None = None,
        preview_theme: str = "monokai",
        textual_theme: str = "textual-dark",
        fullscreen: bool = False,
        hide: HideConfig | None = None,
        columns: ColumnsConfig | None = None,
        export_path: str | None = None,
    ) -> None:
        super().__init__()
        # Register custom themes before setting theme
        for custom_theme in CUSTOM_THEMES:
            self.register_theme(custom_theme)
        self.server_url = server_url
        self.user = user
        self.password = password
        self.theme = textual_theme
        self.preview_theme = preview_theme
        self._fullscreen = fullscreen
        self.hide = hide or HideConfig()
        self.columns = columns or ColumnsConfig()
        self.export_path = export_path
        self.nc: Client | None = None
        self.js: JetStreamContext | None = None
        self.streams: list[StreamInfo] = []
        self.filtered_streams: list[StreamInfo] = []
        self.filter_text: str = ""

    def compose(self) -> ComposeResult:
        yield Header()
        yield FilterInput(placeholder="Filter streams...", id="filter")
        with Container(id="main-container"):
            yield DataTable()
        yield Static("", id="status-bar")
        yield Footer()

    def on_mount(self) -> None:
        self.sub_title = f"Connecting to {self.server_url}..."

        table = self.query_one(DataTable)
        table.add_columns("Stream", "Messages", "Bytes", "Subjects", "Consumers")
        table.cursor_type = "row"

        # Focus table after refresh to ensure CSS is applied
        self.call_after_refresh(table.focus)

        # Apply fullscreen mode if configured
        if self._fullscreen:
            self.add_class("fullscreen")

        self.run_worker(self._connect_and_load())

    async def _connect_and_load(self) -> None:
        """Connect to NATS and load streams."""
        try:
            self.nc = await nats.connect(
                self.server_url,
                user=self.user,
                password=self.password,
            )
            self.js = self.nc.jetstream()
            self.sub_title = f"Connected to {self.server_url}"
            await self._load_streams()
        except Exception as e:
            self.sub_title = f"Error: {e}"

    async def _load_streams(self) -> None:
        """Load all streams from JetStream."""
        if not self.js:
            return

        self.streams = []

        try:
            streams = await self.js.streams_info()
            self.streams = list(streams)
            self._apply_filter()
        except Exception as e:
            self.notify(f"Failed to load streams: {e}", severity="error")

    def _update_status(self) -> None:
        """Update status bar."""
        status = self.query_one("#status-bar", Static)
        status.update(f"Streams: {len(self.streams)} | r: Refresh | Enter: Watch | c: Consumers")

    def _get_selected_stream(self) -> StreamInfo | None:
        """Get the currently selected stream."""
        table = self.query_one(DataTable)
        if table.cursor_row is None or table.cursor_row < 0:
            return None
        if 0 <= table.cursor_row < len(self.filtered_streams):
            return self.filtered_streams[table.cursor_row]
        return None

    def action_refresh(self) -> None:
        """Refresh stream list."""
        self.run_worker(self._load_streams())
        self.notify("Refreshing...")

    def on_data_table_row_selected(self, event: DataTable.RowSelected) -> None:
        """Handle Enter on a stream row."""
        stream = self._get_selected_stream()
        if stream:
            self.push_screen(StartPositionScreen(stream), self._on_start_position_selected)

    def _on_start_position_selected(self, config: JetStreamConfig | None) -> None:
        """Handle start position selection."""
        if config:
            # Exit and return the config - __main__.py will launch NatsVisApp
            self.exit(config)

    def action_view_consumers(self) -> None:
        """View consumers for selected stream."""
        stream = self._get_selected_stream()
        if stream:
            self.run_worker(self._load_and_show_consumers(stream))

    async def _load_and_show_consumers(self, stream: StreamInfo) -> None:
        """Load consumers and show modal."""
        if not self.js:
            return

        stream_name = stream.config.name
        if not stream_name:
            return

        try:
            consumers = await self.js.consumers_info(stream_name)
            consumer_list = list(consumers)
            self.push_screen(ConsumerListScreen(stream_name, consumer_list))
        except Exception as e:
            self.notify(f"Failed to load consumers: {e}", severity="error")

    def action_cursor_down(self) -> None:
        self.query_one(DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one(DataTable).action_cursor_up()

    def action_cursor_top(self) -> None:
        table = self.query_one(DataTable)
        table.move_cursor(row=0)

    def action_cursor_bottom(self) -> None:
        table = self.query_one(DataTable)
        if self.filtered_streams:
            table.move_cursor(row=len(self.filtered_streams) - 1)

    def action_start_filter(self) -> None:
        """Show the filter input."""
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

        if self.filter_text:
            self.filter_text = ""
            self._apply_filter()
            self.notify("Filter cleared")

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle filter input submission."""
        if event.input.id == "filter":
            self.filter_text = event.value.strip()
            self._apply_filter()
            event.input.remove_class("visible")
            self.query_one(DataTable).focus()

    def _apply_filter(self) -> None:
        """Apply filter to the streams table."""
        table = self.query_one(DataTable)
        table.clear()
        self.filtered_streams = []

        filter_lower = self.filter_text.lower()
        for stream in self.streams:
            name = stream.config.name or "?"
            if filter_lower and filter_lower not in name.lower():
                continue

            self.filtered_streams.append(stream)
            msgs = stream.state.messages
            bytes_size = format_bytes(stream.state.bytes)
            subjects = len(stream.config.subjects or [])
            consumers = stream.state.consumer_count

            table.add_row(
                name,
                f"{msgs:,}",
                bytes_size,
                str(subjects),
                str(consumers),
            )

        self._update_status()

    async def on_unmount(self) -> None:
        """Disconnect on exit."""
        if self.nc:
            await self.nc.drain()
