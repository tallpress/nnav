# nnav - Project Context

## Overview

A terminal UI for visualizing and debugging NATS messages in real-time. Built with Python 3.12+, Textual, and nats-py.

## Project Structure

```
/Users/tom/tallpress/nats-vis/
├── src/nnav/
│   ├── __init__.py
│   ├── __main__.py      # CLI entry point (Click)
│   ├── app.py           # Main TUI application (Textual)
│   ├── headless.py      # Headless mode for scripting
│   └── nats_client.py   # NATS connection and message handling
├── tests/
│   └── __init__.py      # Empty - no tests yet
├── .gitignore
├── .python-version      # 3.12
├── FEATURES.md          # Detailed feature list
├── LICENSE              # MIT
├── Makefile             # install, run, config-check, test, clean
├── README.md            # Installation and usage docs
├── pyproject.toml       # Project config (hatchling build)
└── uv.lock
```

## Key Features

- Real-time NATS message streaming with wildcard subscriptions
- Request/Response RPC matching with latency tracking
- Filtering: text, regex (`/pattern/`), message type (REQ/RES/PUB), subject wildcards
- Subject tree browser (`T`) - hierarchical view with counts
- JSON tools: syntax highlighting, path queries (`.user.name`), message diff
- Import/Export sessions (JSON, NDJSON, NATS CLI output format)
- Headless mode for scripting: `nnav -i input.json -f "error" -e output.json`
- Vim keybindings (j/k navigation)
- Viewer mode - load sessions without NATS connection

## Key Bindings

| Key | Action |
|-----|--------|
| j/k | Navigate |
| Enter | View details |
| / | Filter |
| t | Type filter |
| T | Subject tree |
| Space | Pause/Resume |
| m | Bookmark |
| n/N | Next/Prev bookmark |
| d | Diff bookmarks |
| y/Y | Copy payload/subject |
| e/E | Export all/filtered |
| p | Publish |
| ? | Help |
| q | Quit |

## Installation

```bash
# For users (from GitHub)
uv tool install git+https://github.com/tallpress/nnav.git

# For development
git clone https://github.com/tallpress/nnav.git
cd nnav
uv sync
uv run nnav
```

## Commands

```bash
make run            # uv run nnav
make config-check   # uv run mypy src/nnav
make test           # uv run pytest tests/
make clean          # Remove caches and venv
```

## Dependencies

- nats-py>=2.9.0
- textual>=0.89.0
- click>=8.1.0

Dev:
- mypy>=1.13.0
- pytest>=8.3.0

## Work Done This Session

1. **Renamed project** from `nats-vis` to `nnav`
   - Renamed `src/nats_vis/` → `src/nnav/`
   - Updated pyproject.toml, imports, Makefile, FEATURES.md

2. **Added headless mode** (`src/nnav/headless.py`)
   - `--import` + `--export` triggers headless mode
   - Supports `--filter`, `--type`, `--subject`, `--format`

3. **Added subject tree browser**
   - Press `T` to open hierarchical subject view
   - Shows message counts per subject
   - Select to filter by that subject pattern

4. **Added NATS wildcard filtering**
   - `*` matches single token, `>` matches rest of subject

5. **Prepared for open source**
   - Added LICENSE (MIT)
   - Added README.md with install/usage docs
   - Updated .gitignore
   - Verified no secrets/credentials in codebase

## Still Missing

- Tests (tests/ is empty)
- GitHub Actions CI
- CONTRIBUTING.md
- Screenshots/GIF for README

## Notes

- Project directory is `/Users/tom/tallpress/nats-vis/` but GitHub repo will be `tallpress/nnav`
- Test data files (`a.json`, `a.txt`) exist locally but are not git-tracked
- Double-press `c` to clear messages (confirmation pattern)
- Imported messages show "I" marker, bookmarked show "★"
