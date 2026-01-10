"""JetStream browser screens for nnav."""

from __future__ import annotations

from nats.js.api import ConsumerInfo, StreamInfo
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Container, Vertical
from textual.screen import ModalScreen
from textual.widgets import DataTable, Input, Label, OptionList, Static
from textual.widgets.option_list import Option

from nnav.nats_client import JetStreamConfig, JetStreamDeliverPolicy, NatsSubscriber
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
        width: 90%;
        height: 80%;
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
        height: 1fr;
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


class JetStreamBrowserScreen(ModalScreen[JetStreamConfig | None]):
    """Modal screen for browsing JetStream streams."""

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        Binding("q", "cancel", "Cancel"),
        Binding("r", "refresh", "Refresh"),
        Binding("c", "view_consumers", "Consumers"),
        Binding("slash", "start_filter", "Filter"),
        Binding("j", "cursor_down", "Down", show=False),
        Binding("k", "cursor_up", "Up", show=False),
        Binding("g", "cursor_top", "Top", show=False),
        Binding("G", "cursor_bottom", "Bottom", show=False),
    ]

    CSS = """
    JetStreamBrowserScreen {
        align: center middle;
    }

    #browser-dialog {
        width: 90%;
        height: 80%;
        border: solid $primary;
        background: $surface;
        padding: 1 2;
    }

    #browser-title {
        text-style: bold;
        text-align: center;
        padding-bottom: 1;
    }

    #streams-table {
        height: 1fr;
    }

    #filter-container {
        height: auto;
        display: none;
        padding: 1 0 0 0;
    }

    #filter-container.visible {
        display: block;
    }

    #browser-status {
        height: 1;
        padding-top: 1;
        color: $text-muted;
    }

    #browser-hint {
        text-align: center;
        color: $text-muted;
        padding-top: 1;
    }
    """

    def __init__(self, subscriber: NatsSubscriber) -> None:
        super().__init__()
        self.subscriber = subscriber
        self.streams: list[StreamInfo] = []
        self.filtered_streams: list[StreamInfo] = []
        self.filter_text: str = ""

    def compose(self) -> ComposeResult:
        with Container(id="browser-dialog"):
            yield Label("JetStream Streams", id="browser-title")
            yield DataTable(id="streams-table")
            with Container(id="filter-container"):
                yield Input(placeholder="Filter streams...", id="stream-filter")
            yield Static("Loading...", id="browser-status")
            yield Label("Enter: Watch | r: Refresh | c: Consumers | Esc: Cancel", id="browser-hint")

    def on_mount(self) -> None:
        table = self.query_one("#streams-table", DataTable)
        table.add_columns("Stream", "Messages", "Bytes", "Subjects", "Consumers")
        table.cursor_type = "row"
        table.focus()

        self.run_worker(self._load_streams())

    async def _load_streams(self) -> None:
        """Load all streams from JetStream."""
        js = self.subscriber.js
        if not js:
            self._update_status("Not connected to JetStream")
            return

        self.streams = []

        try:
            streams = await js.streams_info()
            self.streams = list(streams)
            self._apply_filter()
            self._update_status(f"Streams: {len(self.streams)}")
        except Exception as e:
            self._update_status(f"Error: {e}")

    def _update_status(self, text: str) -> None:
        """Update status bar."""
        self.query_one("#browser-status", Static).update(text)

    def _get_selected_stream(self) -> StreamInfo | None:
        """Get the currently selected stream."""
        table = self.query_one("#streams-table", DataTable)
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
        event.stop()  # Prevent bubbling to NatsVisApp
        stream = self._get_selected_stream()
        if stream:
            self.app.push_screen(StartPositionScreen(stream), self._on_start_position_selected)

    def _on_start_position_selected(self, config: JetStreamConfig | None) -> None:
        """Handle start position selection."""
        if config:
            self.dismiss(config)

    def action_view_consumers(self) -> None:
        """View consumers for selected stream."""
        stream = self._get_selected_stream()
        if stream:
            self.run_worker(self._load_and_show_consumers(stream))

    async def _load_and_show_consumers(self, stream: StreamInfo) -> None:
        """Load consumers and show modal."""
        js = self.subscriber.js
        if not js:
            return

        stream_name = stream.config.name
        if not stream_name:
            return

        try:
            consumers = await js.consumers_info(stream_name)
            consumer_list = list(consumers)
            self.app.push_screen(ConsumerListScreen(stream_name, consumer_list))
        except Exception as e:
            self.notify(f"Failed to load consumers: {e}", severity="error")

    def action_start_filter(self) -> None:
        """Show filter input."""
        container = self.query_one("#filter-container")
        container.add_class("visible")
        self.query_one("#stream-filter", Input).focus()

    def on_input_submitted(self, event: Input.Submitted) -> None:
        """Handle filter input submission."""
        if event.input.id == "stream-filter":
            self.filter_text = event.value.strip()
            self._apply_filter()
            if not event.value.strip():
                self.query_one("#filter-container").remove_class("visible")
            self.query_one("#streams-table", DataTable).focus()

    def _apply_filter(self) -> None:
        """Apply filter to the streams table."""
        table = self.query_one("#streams-table", DataTable)
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

    def action_cancel(self) -> None:
        """Cancel and close the browser."""
        self.dismiss(None)

    def action_cursor_down(self) -> None:
        self.query_one("#streams-table", DataTable).action_cursor_down()

    def action_cursor_up(self) -> None:
        self.query_one("#streams-table", DataTable).action_cursor_up()

    def action_cursor_top(self) -> None:
        table = self.query_one("#streams-table", DataTable)
        table.move_cursor(row=0)

    def action_cursor_bottom(self) -> None:
        table = self.query_one("#streams-table", DataTable)
        if self.filtered_streams:
            table.move_cursor(row=len(self.filtered_streams) - 1)
