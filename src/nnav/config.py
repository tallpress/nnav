"""Configuration loading from ~/.config/nnav/config.toml."""

import tomllib
from dataclasses import dataclass, field
from pathlib import Path


@dataclass
class ConnectionConfig:
    """Default NATS connection settings."""

    url: str | None = None
    user: str | None = None
    password: str | None = None


@dataclass
class ColumnsConfig:
    """Configure which columns to display in the message table."""

    marker: bool = True
    time: bool = True
    type: bool = True
    subject: bool = True
    latency: bool = True
    payload: bool = True


@dataclass
class HideConfig:
    """Configure which internal subjects to hide from display."""

    inbox: bool = False  # _INBOX.*
    jetstream: bool = False  # $JS.*


@dataclass
class AppearanceConfig:
    """Appearance settings."""

    theme: str = "textual-dark"  # Textual app theme
    preview_theme: str = "monokai"  # Pygments theme for JSON syntax highlighting
    fullscreen: bool = False  # Start in fullscreen mode (hide header/footer)


@dataclass
class Config:
    """Application configuration."""

    export_path: str | None = None  # Default export file path
    connection: ConnectionConfig = field(default_factory=ConnectionConfig)
    columns: ColumnsConfig = field(default_factory=ColumnsConfig)
    hide: HideConfig = field(default_factory=HideConfig)
    appearance: AppearanceConfig = field(default_factory=AppearanceConfig)


def load_config() -> Config:
    """Load configuration from ~/.config/nnav/config.toml.

    Returns defaults if file doesn't exist.
    """
    path = Path.home() / ".config" / "nnav" / "config.toml"
    if not path.exists():
        return Config()

    with path.open("rb") as f:
        data = tomllib.load(f)

    conn_data = data.get("connection", {})
    connection = ConnectionConfig(
        url=conn_data.get("url"),
        user=conn_data.get("user"),
        password=conn_data.get("password"),
    )

    col_data = data.get("columns", {})
    columns = ColumnsConfig(
        marker=col_data.get("marker", True),
        time=col_data.get("time", True),
        type=col_data.get("type", True),
        subject=col_data.get("subject", True),
        latency=col_data.get("latency", True),
        payload=col_data.get("payload", True),
    )

    hide_data = data.get("hide", {})
    hide = HideConfig(
        inbox=hide_data.get("inbox", False),
        jetstream=hide_data.get("jetstream", False),
    )

    appearance_data = data.get("appearance", {})
    appearance = AppearanceConfig(
        theme=appearance_data.get("theme", "textual-dark"),
        preview_theme=appearance_data.get("preview_theme", "monokai"),
        fullscreen=appearance_data.get("fullscreen", False),
    )

    return Config(
        export_path=data.get("export_path"),
        connection=connection,
        columns=columns,
        hide=hide,
        appearance=appearance,
    )
