# nnav

A terminal UI for exploring NATS messages with filtering, request/response matching, and JSON tools inspired by lnav (https://lnav.org/)

## Contents

- [Features](#features)
- [Limitations](#limitations)
- [Installation](#installation)
- [Modes](#modes)
  - [Watch Mode (Default)](#watch-mode-default)
  - [JetStream Mode](#jetstream-mode)
  - [Headless Mode](#headless-mode)
- [Configuration](#configuration)
  - [Custom Themes](#custom-themes)
- [File Formats](#file-formats)
- [Development](#development)

## Features

- **Real-time message stream** - Subscribe to subjects with wildcard support (`*`, `>`)
- **Request/Response matching** - Automatically correlate RPC pairs with latency tracking
- **Filtering** - By text, regex (`/pattern/`), message type, or subject pattern
- **Subject tree browser** - Hierarchical view of subjects with message counts
- **JSON tools** - Syntax highlighting, path queries (`.user.name`), message diff
- **Import/Export** - Save sessions, share with friends, import NATS CLI output
- **Headless mode** - Filter and export without TUI for scripting
- **JetStream mode** - Browse streams/consumers, watch streams from any position


## Limitations
- assumes message payloads are JSON
- hasn't been tested with very high message rates

## Installation

You can run this in a few different ways. The recommended way is via the `uv` tool manager.

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

## Modes

### Watch Mode (Default)

Subscribe to NATS subjects and watch messages in real-time with a TUI.

```bash
# Connect to local NATS
nnav

# Connect to specific server
nnav -s nats://myserver:4222

# Subscribe to specific subjects (not recommended - RPC matching won't work)
nnav -s nats://localhost:4222 -S "orders.>"

# Use a NATS context file
nnav -c ~/.config/nats/context/prod.json

# View a saved session (no NATS connection needed)
nnav --import session.json
```

### JetStream Mode

Browse JetStream streams and consumers, then watch messages from any starting position.

```bash
# Open JetStream browser
nnav -J

# Connect to specific server
nnav -J -s nats://myserver:4222

# Use a context file
nnav -J -c ~/.config/nats/context/prod.json
```

#### Start Positions

When selecting a stream, you can choose:
- **Latest** - Only new messages (default)
- **All** - From the beginning of the stream
- **Sequence** - From a specific sequence number

After selecting, nnav switches to watch mode with all the usual features (filtering, bookmarks, export).

### Headless Mode

Filter and export without the TUI - useful for scripts and CI.

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

## Configuration

nnav can be configured at `~/.config/nnav/config.toml`:

```toml
# Default export file path
export_path = "~/nats-exports/session.json"

# Appearance settings
[appearance]
theme = "textual-dark"         # Textual app theme
preview_theme = "monokai"      # Pygments theme for JSON syntax highlighting
fullscreen = false             # Start in fullscreen mode (hide header/footer)

# Default connection (used when no --server or --context provided)
[connection]
url = "nats://localhost:4222"
user = "myuser"
password = "mypassword"

# Hide internal subjects from display (RPC correlation still works)
[hide]
inbox = true       # Hide _INBOX.* subjects
jetstream = true   # Hide $JS.* subjects

# Configure which columns to display
[columns]
marker = true      # Bookmark/import marker (★, I)
time = true        # Timestamp
type = true        # Message type (REQ/RES/PUB)
subject = true     # NATS subject
latency = true     # Response latency
payload = true     # Message payload preview
```

All settings are optional - defaults are used for missing values.

### theme

See [Textual themes](https://textual.textualize.io/guide/design/#themes) for all available options.

Common: `textual-dark`, `textual-light`, `nord`, `dracula`, `gruvbox`, `tokyo-night`, `monokai`, `catppuccin-mocha`

### preview_theme

See [Pygments styles](https://pygments.org/styles/) for all available options.

Dark: `monokai`, `dracula`, `one-dark`, `nord`, `gruvbox-dark`, `material`, `native`, `vim`

Light: `github-light`, `gruvbox-light`, `solarized-light`, `vs`, `friendly`

### Custom Themes

You can define custom Textual themes in your config file. These are registered before the app starts, so you can reference them in the `theme` setting.

```toml
[appearance]
theme = "my-custom-theme"

[[themes]]
name = "my-custom-theme"
primary = "#fabd2f"
secondary = "#83a598"
accent = "#fe8019"
foreground = "#ebdbb2"
background = "#1d2021"
success = "#b8bb26"
warning = "#d79921"
error = "#fb4934"
surface = "#282828"
panel = "#3c3836"
dark = true

[themes.variables]
border = "#504945"
footer-background = "#282828"
footer-key-foreground = "#fabd2f"
```

#### Theme Properties

| Property | Description |
|----------|-------------|
| `name` | Theme identifier (required) |
| `primary` | Primary accent color |
| `secondary` | Secondary accent color |
| `accent` | Tertiary accent color |
| `foreground` | Default text color |
| `background` | App background color |
| `success` | Success state color |
| `warning` | Warning state color |
| `error` | Error state color |
| `surface` | Surface/container color |
| `panel` | Panel/sidebar color |
| `dark` | `true` for dark themes, `false` for light |

#### Theme Variables

The `[themes.variables]` section allows fine-grained control over UI elements. Common variables:

| Variable | Description |
|----------|-------------|
| `border` | Border color |
| `border-blurred` | Border color when unfocused |
| `scrollbar` | Scrollbar track color |
| `scrollbar-hover` | Scrollbar hover color |
| `footer-background` | Footer bar background |
| `footer-key-foreground` | Footer keybinding color |
| `footer-description-foreground` | Footer description color |
| `input-cursor-background` | Text input cursor color |
| `input-selection-background` | Text selection color |
| `block-cursor-background` | Block cursor background |
| `block-cursor-foreground` | Block cursor text color |

See [Textual design variables](https://textual.textualize.io/guide/design/#design-variables) for all available variables.

You can define multiple themes by adding more `[[themes]]` blocks.

## File Formats

### Context Files

Supports the standard NATS CLI context file format:

```json
{
  "url": "nats://myserver:4222",
  "user": "myuser",
  "password": "mypassword"
  ...
}
```

### Importing NATS CLI Output

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
```

## License

MIT
