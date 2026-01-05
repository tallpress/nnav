"""Headless mode for nnav - filter and export without TUI."""

from pathlib import Path

from nnav.messages import export_messages, filter_messages, load_messages


def run_headless(
    import_file: Path,
    export_file: Path,
    filter_text: str | None,
    filter_type: str | None,
    subject_pattern: str | None,
    export_format: str,
) -> None:
    """Run nnav in headless mode - import, filter, export."""
    # Load messages
    messages = load_messages(import_file)
    print(f"Loaded {len(messages)} messages from {import_file}")

    # Apply filters
    filtered = filter_messages(
        messages,
        filter_text=filter_text,
        filter_type=filter_type,
        subject_pattern=subject_pattern,
    )
    print(f"After filtering: {len(filtered)} messages")

    # Export
    export_messages(filtered, export_file, export_format)
    print(f"Exported to {export_file}")
