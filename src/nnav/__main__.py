"""CLI entry point for nnav - NATS Navigator."""

import json
from pathlib import Path

import click

from nnav.app import NatsVisApp
from nnav.config import load_config


def load_context(context_path: str) -> dict[str, str | None]:
    """Load NATS context from JSON file."""
    path = Path(context_path).expanduser()
    with path.open() as f:
        data = json.load(f)

    url = data.get("url", "")
    if url and not url.startswith("nats://"):
        url = f"nats://{url}"

    return {
        "server_url": url or "nats://localhost:4222",
        "user": data.get("user") or None,
        "password": data.get("password") or None,
    }


@click.command()
@click.option(
    "--server",
    "-s",
    default=None,
    help="NATS server URL",
)
@click.option(
    "--context",
    "-c",
    default=None,
    help="Path to NATS context JSON file",
)
@click.option(
    "--subject",
    "-S",
    default=">",
    help="Subject filter (supports wildcards: *, >)",
    show_default=True,
)
@click.option(
    "--import",
    "-i",
    "import_file",
    default=None,
    type=click.Path(exists=True, path_type=Path),
    help="Import session from file (JSON or NATS CLI format)",
)
@click.option(
    "--filter",
    "-f",
    "filter_text",
    default=None,
    help="Filter messages by text or /regex/ (headless mode)",
)
@click.option(
    "--type",
    "-t",
    "filter_type",
    type=click.Choice(["REQ", "RES", "PUB"], case_sensitive=False),
    default=None,
    help="Filter by message type (headless mode)",
)
@click.option(
    "--export",
    "-e",
    "export_file",
    default=None,
    type=click.Path(path_type=Path),
    help="Export to file (enables headless mode with --import)",
)
@click.option(
    "--format",
    "export_format",
    type=click.Choice(["json", "ndjson"], case_sensitive=False),
    default="json",
    help="Export format",
    show_default=True,
)
@click.option(
    "--jetstream",
    "-J",
    is_flag=True,
    help="JetStream browser mode (browse streams/consumers)",
)
def main(
    server: str | None,
    context: str | None,
    subject: str,
    import_file: Path | None,
    filter_text: str | None,
    filter_type: str | None,
    export_file: Path | None,
    export_format: str,
    jetstream: bool,
) -> None:
    """nnav - NATS Navigator.

    Subscribes to NATS subjects and displays messages in real-time.
    Use --import to view a saved session without connecting to NATS.

    Headless mode (no TUI):
      nnav -i input.json -f "error" -e output.json
      nnav -i input.json -t REQ -e requests.json

    JetStream mode:
      nnav -J                    # Browse streams, select to watch
      nnav -J -s nats://server   # Connect to specific server
    """
    # Headless mode: import + export
    if import_file and export_file:
        from nnav.headless import run_headless

        run_headless(
            import_file=import_file,
            export_file=export_file,
            filter_text=filter_text,
            filter_type=filter_type,
            subject_pattern=subject if subject != ">" else None,
            export_format=export_format,
        )
        return

    # Load config file
    config = load_config()

    # JetStream browser mode
    if jetstream:
        from nnav.jetstream_app import JetStreamApp

        # Determine server URL
        js_server: str
        js_user: str | None = None
        js_password: str | None = None

        if context:
            ctx = load_context(context)
            js_server = ctx["server_url"] or "nats://localhost:4222"
            js_user = ctx["user"]
            js_password = ctx["password"]
        elif server:
            js_server = server
        elif config.connection.url:
            js_server = config.connection.url
            js_user = config.connection.user
            js_password = config.connection.password
        else:
            js_server = "nats://localhost:4222"

        js_app = JetStreamApp(
            server_url=js_server,
            user=js_user,
            password=js_password,
            preview_theme=config.appearance.preview_theme,
            textual_theme=config.appearance.theme,
            fullscreen=config.appearance.fullscreen,
            hide=config.hide,
            columns=config.columns,
            export_path=config.export_path,
            theme_configs=config.themes,
        )
        js_config = js_app.run()

        # If a stream was selected, launch watch mode
        if js_config:
            watch_app = NatsVisApp(
                server_url=js_server,
                user=js_user,
                password=js_password,
                preview_theme=config.appearance.preview_theme,
                textual_theme=config.appearance.theme,
                fullscreen=config.appearance.fullscreen,
                hide=config.hide,
                columns=config.columns,
                export_path=config.export_path,
                jetstream_config=js_config,
                theme_configs=config.themes,
            )
            watch_app.run()
        return

    # TUI mode
    if import_file:
        # Viewer mode - no NATS connection needed
        app = NatsVisApp(
            import_file=import_file,
            preview_theme=config.appearance.preview_theme,
            textual_theme=config.appearance.theme,
            fullscreen=config.appearance.fullscreen,
            hide=config.hide,
            columns=config.columns,
            export_path=config.export_path,
            theme_configs=config.themes,
        )
    elif context:
        ctx = load_context(context)
        app = NatsVisApp(
            server_url=ctx["server_url"],
            user=ctx["user"],
            password=ctx["password"],
            subject=subject,
            preview_theme=config.appearance.preview_theme,
            textual_theme=config.appearance.theme,
            fullscreen=config.appearance.fullscreen,
            hide=config.hide,
            columns=config.columns,
            export_path=config.export_path,
            theme_configs=config.themes,
        )
    elif server:
        # CLI --server flag
        app = NatsVisApp(
            server_url=server,
            subject=subject,
            preview_theme=config.appearance.preview_theme,
            textual_theme=config.appearance.theme,
            fullscreen=config.appearance.fullscreen,
            hide=config.hide,
            columns=config.columns,
            export_path=config.export_path,
            theme_configs=config.themes,
        )
    elif config.connection.url:
        # Config file connection
        app = NatsVisApp(
            server_url=config.connection.url,
            user=config.connection.user,
            password=config.connection.password,
            subject=subject,
            preview_theme=config.appearance.preview_theme,
            textual_theme=config.appearance.theme,
            fullscreen=config.appearance.fullscreen,
            hide=config.hide,
            columns=config.columns,
            export_path=config.export_path,
            theme_configs=config.themes,
        )
    else:
        # Default localhost
        app = NatsVisApp(
            server_url="nats://localhost:4222",
            subject=subject,
            preview_theme=config.appearance.preview_theme,
            textual_theme=config.appearance.theme,
            fullscreen=config.appearance.fullscreen,
            hide=config.hide,
            columns=config.columns,
            export_path=config.export_path,
            theme_configs=config.themes,
        )
    app.run()


if __name__ == "__main__":
    main()
