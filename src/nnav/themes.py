"""Custom theme support for nnav."""

from textual.theme import Theme

from nnav.config import ThemeConfig


def build_theme(config: ThemeConfig) -> Theme:
    """Build a Textual Theme from a ThemeConfig."""
    return Theme(
        name=config.name,
        primary=config.primary,
        secondary=config.secondary,
        accent=config.accent,
        foreground=config.foreground,
        background=config.background,
        success=config.success,
        warning=config.warning,
        error=config.error,
        surface=config.surface,
        panel=config.panel,
        dark=config.dark,
        variables=config.variables,
    )


def build_themes(configs: list[ThemeConfig]) -> list[Theme]:
    """Build a list of Textual Themes from ThemeConfigs."""
    return [build_theme(c) for c in configs]
