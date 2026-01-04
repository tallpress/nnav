"""CLI entry point for nnav - NATS Navigator."""

import json
from pathlib import Path

import click

from nnav.app import NatsVisApp


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
def main(
    server: str | None,
    context: str | None,
    subject: str,
    import_file: Path | None,
    filter_text: str | None,
    filter_type: str | None,
    export_file: Path | None,
    export_format: str,
) -> None:
    """nnav - NATS Navigator.

    Subscribes to NATS subjects and displays messages in real-time.
    Use --import to view a saved session without connecting to NATS.

    Headless mode (no TUI):
      nnav -i input.json -f "error" -e output.json
      nnav -i input.json -t REQ -e requests.json
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

    # TUI mode
    if import_file:
        # Viewer mode - no NATS connection needed
        app = NatsVisApp(import_file=import_file)
    elif context:
        config = load_context(context)
        app = NatsVisApp(
            server_url=config["server_url"],
            user=config["user"],
            password=config["password"],
            subject=subject,
        )
    else:
        app = NatsVisApp(
            server_url=server or "nats://localhost:4222",
            user=None,
            password=None,
            subject=subject,
        )
    app.run()


if __name__ == "__main__":
    main()
