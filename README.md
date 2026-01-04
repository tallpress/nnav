# nnav - NATS Navigator

A terminal UI for visualizing and debugging NATS messages in real-time.

## Features

- **Real-time message stream** - Subscribe to subjects with wildcard support (`*`, `>`)
- **Request/Response matching** - Automatically correlate RPC pairs with latency tracking
- **Filtering** - By text, regex (`/pattern/`), message type, or subject pattern
- **Subject tree browser** - Hierarchical view of subjects with message counts
- **JSON tools** - Syntax highlighting, path queries (`.user.name`), message diff
- **Import/Export** - Save sessions, share with colleagues, import NATS CLI output
- **Headless mode** - Filter and export without TUI for scripting

## Installation

Requires Python 3.12+ and [uv](https://docs.astral.sh/uv/).

```bash
# Install uv if you don't have it
curl -LsSf https://astral.sh/uv/install.sh | sh

# Install nnav as a CLI tool
uv tool install git+https://github.com/tallpress/nnav.git

# Verify it's installed
nnav --help
```

This adds `nnav` to your PATH. To upgrade later:

```bash
uv tool upgrade nnav
```

To uninstall:

```bash
uv tool uninstall nnav
```

## Usage

```bash
# Connect to local NATS
nnav

# Connect to specific server
nnav -s nats://myserver:4222

# Subscribe to specific subjects, this is not reccomended as RPC message matching will not work
nnav -s nats://localhost:4222 -S "orders.>"

# Use a NATS context file
nnav -c ~/.config/nats/context/prod.json

# View a saved session (no NATS connection needed)
nnav --import session.json

# Headless: filter and export
nnav -i input.json -f "error" -e errors.json
nnav -i input.json -t REQ -e requests.json
```

## Keyboard Shortcuts

| Key | Action |
|-----|--------|
| `j/k` | Navigate up/down |
| `Enter` | View message details |
| `/` | Filter messages |
| `t` | Filter by type (REQ/RES/PUB) |
| `T` | Subject tree browser |
| `Space` | Pause/Resume stream |
| `m` | Bookmark message |
| `n/N` | Next/Previous bookmark |
| `d` | Diff two bookmarked messages |
| `y` | Copy payload |
| `e` | Export messages |
| `p` | Publish message |
| `?` | Help |
| `q` | Quit |

### In Detail View

| Key | Action |
|-----|--------|
| `j/k` | Scroll |
| `/` | JSON path query (e.g., `.user.name`) |
| `r` | Jump to related request/response |

## Context File Format

```json
{
  "url": "nats://myserver:4222",
  "user": "myuser",
  "password": "mypassword"
}
```

## Headless Mode

Filter and export without the TUI - useful for scripts and CI:

```bash
# Filter by text
nnav -i session.json -f "error" -e errors.json

# Filter by regex
nnav -i session.json -f "/order-[0-9]+/" -e orders.json

# Filter by message type
nnav -i session.json -t REQ -e requests.json

# Filter by subject pattern
nnav -i session.json -S "orders.>" -e orders.json

# Export as newline-delimited JSON
nnav -i session.json -e output.ndjson --format ndjson
```

## Importing NATS CLI Output

You can import output from `nats sub`:

```bash
# Capture with nats CLI
nats sub ">" --count 100 > capture.txt

# View in nnav
nnav -i capture.txt
```

## Development

```bash
git clone https://github.com/tallpress/nnav.git
cd nnav
uv sync
uv run nnav              # Run
make config-check        # Type check
make test                # Run tests
```

## License

MIT
