# nnav - NATS Navigator

The lnav equivalent for NATS. A terminal UI for visualizing and debugging NATS messages in real-time.

## Project Overview

- **Purpose**: Real-time NATS message visualization, debugging, and analysis
- **Stack**: Python 3.12+, Textual (TUI), nats-py (NATS client), Click (CLI)
- **Modes**: Live streaming, viewer (import sessions), headless (scripting)

## Project Structure

```
src/nnav/
├── __main__.py      # CLI entry point (Click) - mode routing
├── app.py           # Main TUI application (Textual)
├── config.py        # Configuration loading from ~/.config/nnav/config.toml
├── nats_client.py   # NATS connection, RPC tracking, message types
├── headless.py      # Headless mode for batch processing
├── constants.py     # Shared constants
├── core/
│   └── filter.py    # Message filtering logic (FilterState, MessageFilter)
├── ui/
│   ├── screens.py   # Modal screens (HelpScreen, MessageDetailScreen, etc.)
│   ├── jetstream_screens.py  # JetStream browser screens
│   ├── mixins.py    # Shared UI mixins (FilterMixin, FullscreenMixin)
│   └── widgets.py   # Custom widgets (FilterInput)
└── utils/
    ├── clipboard.py # Clipboard operations
    ├── formatting.py # Display formatting
    └── patterns.py  # NATS pattern matching
tests/               # pytest tests (currently empty)
```

## Key Commands

```bash
make run            # Run the app (uv run nnav)
make config-check   # Type check with mypy
make test           # Run pytest
make clean          # Remove caches and venv
```

## Architecture

### Layers
1. **CLI** (`__main__.py`): Parses args, routes to TUI/viewer/headless mode
2. **NATS Client** (`nats_client.py`): Connection, subscription, RPC correlation
3. **TUI** (`app.py`): Textual app with modal screens, filtering, navigation
4. **Headless** (`headless.py`): Scriptable filtering and export

### Key Classes
- `NatsMessage`: Dataclass for message data with correlation info
- `RpcTracker`: Matches request/response pairs, calculates latency
- `NatsSubscriber`: AsyncIO NATS connection manager
- `NatsVisApp`: Main Textual application
- `StoredMessage`: UI wrapper with bookmarks, import status
- `MessageFilter`: Filtering logic with text, regex, type, and tree prefix support
- `JetStreamBrowserScreen`: Modal screen for browsing JetStream streams

## Features

- Real-time streaming with wildcard subscriptions (`*`, `>`)
- Request/response RPC matching with latency tracking
- Filtering: text, regex (`/pattern/`), exclude (`!pattern`), message type (REQ/RES/PUB), subject wildcards
- Subject tree browser (hierarchical view with counts)
- JSON syntax highlighting and path queries (`.user.name`)
- Message diff between bookmarked messages
- Import/export (JSON, NDJSON, NATS CLI format)
- Vim keybindings (j/k navigation)

## Key Bindings

| Key | Action | Key | Action |
|-----|--------|-----|--------|
| j/k | Navigate | p | Pause/Resume |
| Enter | View details | m | Bookmark |
| / | Filter (use ! to exclude) | n/N | Next/Prev bookmark |
| t | Type filter | d | Diff bookmarks |
| T | Subject tree | y/Y | Copy payload/subject |
| e/E | Export all/filtered | J | JetStream browser |
| ? | Help | q | Quit |

## Configuration

Config file at `~/.config/nnav/config.toml`:
- `theme` - Pygments theme for JSON highlighting
- `export_path` - Default export file path
- `[connection]` - Default server URL, user, password
- `[hide]` - Hide internal subjects: `inbox` (_INBOX.*), `jetstream` ($JS.*)
- `[columns]` - Toggle columns: marker, time, type, subject, latency, payload

## Development Notes

- Uses async/await for non-blocking NATS operations
- Type hints throughout with strict mypy mode
- Textual's ModalScreen pattern for overlays
- RPC tracking uses NATS inbox patterns (_INBOX.*)

## Running

```bash
# Live mode - connect and stream
nnav -s nats://localhost:4222 -S "orders.>"

# Viewer mode - load saved session
nnav -i session.json

# JetStream mode - browse streams, select to watch
nnav -J

# Headless mode - filter and export
nnav -i input.json -f "error" -t REQ -e errors.json
```
