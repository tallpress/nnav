"""Message parsing, filtering, and export utilities for nnav."""

import json
import re
from datetime import datetime
from pathlib import Path

from nnav.nats_client import MessageType, NatsMessage


def load_messages(path: Path) -> list[NatsMessage]:
    """Load messages from file (JSON or NATS CLI format).

    Args:
        path: Path to the message file

    Returns:
        List of parsed NatsMessage objects
    """
    content = path.read_text()

    # Try JSON format first
    try:
        data = json.loads(content)
        if isinstance(data, list):
            return parse_json_format(data)
    except json.JSONDecodeError:
        pass

    # Try NATS CLI format
    return parse_nats_cli_format(content)


def parse_json_format(data: list[dict[str, object]]) -> list[NatsMessage]:
    """Parse messages from JSON export format.

    Args:
        data: List of message dictionaries

    Returns:
        List of NatsMessage objects
    """
    type_map = {
        "PUB": MessageType.PUBLISH,
        "REQ": MessageType.REQUEST,
        "RES": MessageType.RESPONSE,
    }
    messages: list[NatsMessage] = []

    for item in data:
        try:
            # Parse timestamp
            timestamp_str = str(item.get("timestamp", ""))
            try:
                timestamp = datetime.fromisoformat(timestamp_str)
            except ValueError:
                timestamp = datetime.now()

            # Parse message type
            type_str = str(item.get("type", "PUB"))
            msg_type = type_map.get(type_str, MessageType.PUBLISH)

            # Parse headers
            headers_raw = item.get("headers", {})
            headers = (
                {str(k): str(v) for k, v in headers_raw.items()}
                if isinstance(headers_raw, dict)
                else {}
            )

            # Parse latency
            latency_raw = item.get("latency_ms")
            latency_ms: float | None = None
            if latency_raw is not None:
                try:
                    latency_ms = float(str(latency_raw))
                except ValueError:
                    pass

            messages.append(
                NatsMessage(
                    subject=str(item.get("subject", "")),
                    payload=str(item.get("payload", "")),
                    timestamp=timestamp,
                    reply_to=str(item.get("reply_to")) if item.get("reply_to") else None,
                    headers=headers,
                    message_type=msg_type,
                    latency_ms=latency_ms,
                    request_subject=(
                        str(item.get("request_subject"))
                        if item.get("request_subject")
                        else None
                    ),
                )
            )
        except Exception:
            continue

    return messages


def parse_nats_cli_format(content: str) -> list[NatsMessage]:
    """Parse NATS CLI output format into messages.

    Args:
        content: Raw NATS CLI output text

    Returns:
        List of NatsMessage objects
    """
    messages: list[NatsMessage] = []
    lines = content.split("\n")

    i = 0
    while i < len(lines):
        line = lines[i].strip()

        # Look for message start: [#N] Received ...
        if not line.startswith("[#") or "] Received" not in line:
            i += 1
            continue

        subject = ""
        reply_to: str | None = None
        headers: dict[str, str] = {}
        payload_lines: list[str] = []

        # Parse the "Received" line
        if "Received on " in line:
            match = re.search(r'Received on "([^"]+)"', line)
            if match:
                subject = match.group(1)
            reply_match = re.search(r'with reply "([^"]+)"', line)
            if reply_match:
                reply_to = reply_match.group(1)
        elif "Received JetStream message:" in line:
            match = re.search(r"subject: ([^\s/]+)", line)
            if match:
                subject = match.group(1)

        i += 1

        # Parse headers until empty line
        while i < len(lines) and lines[i].strip():
            header_line = lines[i].strip()
            if ": " in header_line and not header_line.startswith("{"):
                key, _, value = header_line.partition(": ")
                headers[key] = value
            else:
                break
            i += 1

        # Skip empty line
        if i < len(lines) and not lines[i].strip():
            i += 1

        # Collect payload until next message
        while i < len(lines):
            next_line = lines[i]
            if next_line.strip().startswith("[#") and "] Received" in next_line:
                break
            payload_lines.append(next_line)
            i += 1

        payload = "\n".join(payload_lines).strip()
        if payload == "nil body":
            payload = ""

        # Determine message type
        if reply_to:
            msg_type = MessageType.REQUEST
        elif subject.startswith("_INBOX."):
            msg_type = MessageType.RESPONSE
        else:
            msg_type = MessageType.PUBLISH

        if subject:
            messages.append(
                NatsMessage(
                    subject=subject,
                    payload=payload,
                    timestamp=datetime.now(),
                    reply_to=reply_to,
                    headers=headers,
                    message_type=msg_type,
                )
            )

    return messages


def filter_messages(
    messages: list[NatsMessage],
    filter_text: str | None = None,
    filter_type: str | None = None,
    subject_pattern: str | None = None,
) -> list[NatsMessage]:
    """Filter messages by text, type, and subject pattern.

    Args:
        messages: List of messages to filter
        filter_text: Text or /regex/ to search for in subject and payload
        filter_type: Message type filter (REQ, RES, PUB)
        subject_pattern: NATS subject pattern with wildcards (*, >)

    Returns:
        Filtered list of messages
    """
    result = messages

    # Type filter
    if filter_type:
        type_map = {
            "REQ": MessageType.REQUEST,
            "RES": MessageType.RESPONSE,
            "PUB": MessageType.PUBLISH,
        }
        target_type = type_map.get(filter_type.upper())
        if target_type:
            result = [m for m in result if m.message_type == target_type]

    # Subject pattern filter
    if subject_pattern:
        result = [m for m in result if matches_subject_pattern(m.subject, subject_pattern)]

    # Text/regex filter
    if filter_text:
        result = [m for m in result if matches_filter(m, filter_text)]

    return result


def matches_subject_pattern(subject: str, pattern: str) -> bool:
    """Check if a subject matches a NATS pattern with wildcards.

    Args:
        subject: The NATS subject to check
        pattern: Pattern with * (single token) and > (multi-token) wildcards

    Returns:
        True if subject matches pattern
    """
    # Convert NATS wildcards to regex
    regex_pattern = pattern.replace(".", r"\.").replace("*", r"[^.]+").replace(">", r".+")
    regex = re.compile(f"^{regex_pattern}$")
    return bool(regex.match(subject))


def matches_filter(msg: NatsMessage, filter_text: str) -> bool:
    """Check if a message matches a text or regex filter.

    Args:
        msg: Message to check
        filter_text: Text or /regex/ pattern

    Returns:
        True if message matches filter
    """
    if filter_text.startswith("/") and filter_text.endswith("/") and len(filter_text) > 2:
        # Regex filter
        try:
            regex = re.compile(filter_text[1:-1], re.IGNORECASE)
            return bool(regex.search(msg.subject) or regex.search(msg.payload))
        except re.error:
            return False
    else:
        # Text filter
        filter_lower = filter_text.lower()
        return filter_lower in msg.subject.lower() or filter_lower in msg.payload.lower()


def export_messages(
    messages: list[NatsMessage],
    path: Path,
    format: str = "json",
) -> None:
    """Export messages to file.

    Args:
        messages: List of messages to export
        path: Output file path
        format: Export format ("json" or "ndjson")
    """
    data = [
        {
            "timestamp": m.timestamp.isoformat(),
            "type": m.message_type.value,
            "subject": m.subject,
            "payload": m.payload,
            "reply_to": m.reply_to,
            "headers": m.headers,
            "latency_ms": m.latency_ms,
            "request_subject": m.request_subject,
        }
        for m in messages
    ]

    with path.open("w") as f:
        if format == "ndjson":
            for item in data:
                f.write(json.dumps(item) + "\n")
        else:
            json.dump(data, f, indent=2)
