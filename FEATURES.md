# nnav - NATS Navigator

## Implemented Features

### Core Functionality
- [x] Connect to NATS server with URL or context file
- [x] Subscribe to subjects with wildcard support (`*`, `>`)
- [x] Real-time message display (timestamp, type, subject, latency, payload)
- [x] User/password authentication from context files
- [x] **Viewer Mode** - Load saved sessions without NATS connection (`--import`)
- [x] **Import Formats** - JSON export or NATS CLI output format

### Request/Response Debugging
- [x] **RPC Request/Response Matching** - Automatically correlate request-reply pairs using reply-to subjects and inbox patterns
- [x] **Latency Tracking** - Measure and display response times for matched request/reply pairs
- [x] **Pending RPC Counter** - Track requests awaiting responses
- [x] **Message Type Detection** - Automatically classify messages as PUB/REQ/RES
- [x] **Jump to Related Message** - From a request, press `r` to view its response (and vice versa)

### Navigation & Viewing
- [x] Vim-style navigation (`j`, `k`, `g`, `G`)
- [x] Message detail popup with syntax-highlighted JSON (`Enter`)
- [x] Scrollable payload view in detail screen
- [x] Connection info screen (`i`)
- [x] Help overlay with all shortcuts (`?`)

### Filtering & Search
- [x] **Live Filter** - Filter messages by subject or payload (`/`)
- [x] **Regex Filter** - Use `/pattern/` syntax for regex matching
- [x] **Subject Wildcards** - Filter using NATS wildcard patterns (`*`, `>`)
- [x] **Type Filter** - Cycle through REQ/RES/PUB filters (`t`)
- [x] **Subject Tree Browser** - Hierarchical view of subjects with message counts (`T`)
- [x] **Clear Filters** - Reset all filters (`Escape`)

### Message Analysis
- [x] **JSON Path Query** - Extract specific fields from JSON payloads (`/` in detail view, pre-fills previous query)
- [x] **Message Diff** - Side-by-side comparison of two bookmarked messages (`d`)
- [x] **Payload Size Display** - Show byte size in detail view
- [x] **Headers Display** - View message headers in detail view

### Status Bar
- [x] **Status Bar** - Shows subject, pause state, filter, pending RPC, bookmark count, message count
- [x] **Viewer Mode Status** - Shows filename and message count when viewing imported sessions

### Productivity
- [x] **Pause/Resume** - Freeze display to inspect messages (`Space`)
- [x] **Bookmarks** - Mark important messages (`m`)
- [x] **Navigate Bookmarks** - Jump between bookmarked messages (`n`/`N`)
- [x] **Copy Payload** - Copy to clipboard with formatting (`y`)
- [x] **Copy Subject** - Copy subject to clipboard (`Y`)
- [x] **Clear Messages** - Clear all messages (`c` twice to confirm)

### Publishing
- [x] **Publish Message** - Send new messages from TUI (`p`)
- [x] **Republish** - Resend selected message with edits (`r`)
- [x] **Reply-To Support** - Set reply-to for request-reply patterns
- [x] **JSON Editor** - TextArea with JSON syntax for payload

### Export
- [x] **Export All** - Save all messages to JSON (`e`)
- [x] **Export Filtered** - Save only filtered messages (`E`)
- [x] **NDJSON Support** - Export as newline-delimited JSON
- [x] **Custom Path** - Choose export file location
- [x] **Metadata Included** - Export includes timestamps, types, latency, bookmarks

## Keyboard Shortcuts

### Navigation
| Key | Action |
|-----|--------|
| `j` / `↓` | Move down |
| `k` / `↑` | Move up |
| `g` | Go to first message |
| `G` | Go to last message |
| `Enter` | View message details |
| `n` | Next bookmarked message |
| `N` | Previous bookmarked message |

### Filtering & Search
| Key | Action |
|-----|--------|
| `/` | Filter messages (text or `/regex/`) |
| `Escape` | Clear filter |
| `t` | Cycle message type filter |

### Actions
| Key | Action |
|-----|--------|
| `Space` | Pause/Resume stream |
| `c` | Clear all messages |
| `m` | Toggle bookmark |
| `y` | Copy payload to clipboard |
| `Y` | Copy subject to clipboard |
| `r` | Republish selected message |
| `d` | Diff two bookmarked messages |

### Publishing & Export
| Key | Action |
|-----|--------|
| `p` | Publish new message |
| `e` | Export all messages to JSON |
| `E` | Export filtered messages |

### Views & Panels
| Key | Action |
|-----|--------|
| `T` | Subject tree browser |
| `i` | Show connection info |
| `?` | Show help |
| `q` | Quit |

### In Detail View
| Key | Action |
|-----|--------|
| `j` / `k` | Scroll down / up |
| `g` / `G` | Scroll to top / bottom |
| `/` | JSON path query (pre-fills previous query for editing) |
| `r` | Jump to related request/response |
| `y` | Copy payload |
| `Y` | Copy subject |
| `Escape` | Reset query / Close |
| `Enter` | Re-focus query input / Close |
| `q` | Close |

## Planned Features

### JetStream Support
- [ ] Stream Browser - List and inspect JetStream streams
- [ ] Consumer Status - View consumer lag and pending messages
- [ ] Message Replay - Replay messages from a stream by sequence or time
- [ ] Ack Tracking - Monitor acknowledgment flow

### Advanced Analysis
- [ ] Request Chain Visualization - Track multi-hop request flows
- [ ] Binary Payload Support - Hex view, protobuf decoding
- [ ] Payload Validation - JSON schema validation
- [ ] Subject Tree View - Hierarchical subject browser

### Tracing & Correlation
- [ ] Trace Header Support - Parse `Nats-Trace-*` headers
- [ ] Correlation ID Tracking - Group by correlation ID
- [ ] OpenTelemetry Context - Extract trace/span IDs

### UI/UX
- [ ] Color Coding - Messages by subject pattern
- [ ] Column Customization - Show/hide, resize
- [ ] Multiple Panes - Split view for filters
- [ ] Dark/Light Theme Toggle

### Configuration
- [ ] Config File - Save preferences
- [ ] Subject Aliases - Name complex patterns
- [ ] Profiles - Quick switch environments
- [ ] History Limit - Memory management

### Headless Mode
- [x] **Headless Export** - Filter and export without TUI (`--import` + `--export`)
- [x] **Text/Regex Filter** - Filter by text or `/regex/` in headless mode (`--filter`)
- [x] **Type Filter** - Filter by message type (`--type REQ|RES|PUB`)
- [x] **Subject Pattern** - Filter by NATS subject pattern (`--subject`)
- [x] **Export Formats** - JSON or NDJSON output (`--format`)

## Usage

```bash
# Run with default server
uv run nnav

# With specific server
uv run nnav -s nats://localhost:4222

# With context file
uv run nnav -c ~/.config/nats/context/mycontext.json

# With subject filter
uv run nnav -c ~/.config/nats/context/mycontext.json -S "orders.>"

# View saved session (viewer mode)
uv run nnav --import session.json

# Import NATS CLI output
uv run nnav -i nats-output.txt

# Headless mode: filter and export (no TUI)
uv run nnav -i input.json -f "error" -e output.json
uv run nnav -i input.json -t REQ -e requests.json
uv run nnav -i input.json -S "orders.>" -e orders.ndjson --format ndjson
```
