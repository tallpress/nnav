"""Custom themes for nnav matching popular colorschemes."""

from textual.theme import Theme

# Gruvbox Dark theme - matches nvim gruvbox-custom
gruvbox_dark = Theme(
    name="gruvbox-dark",
    primary="#fabd2f",  # bright_yellow - main accent
    secondary="#83a598",  # bright_blue
    accent="#fe8019",  # bright_orange
    foreground="#ebdbb2",  # fg
    background="#1d2021",  # bg_hard (darker)
    success="#b8bb26",  # bright_green
    warning="#d79921",  # yellow
    error="#fb4934",  # bright_red
    surface="#282828",  # bg (normal)
    panel="#3c3836",  # bg1
    dark=True,
    variables={
        "block-cursor-background": "#ebdbb2",
        "block-cursor-foreground": "#1d2021",
        "block-cursor-text-style": "bold",
        "border": "#504945",  # bg2
        "border-blurred": "#3c3836",  # bg1
        "scrollbar": "#3c3836",  # bg1
        "scrollbar-hover": "#504945",  # bg2
        "scrollbar-active": "#665c54",  # bg3
        "link-background": "#1d2021",
        "link-background-hover": "#282828",
        "link-color": "#83a598",  # bright_blue
        "link-color-hover": "#83a598",
        "footer-background": "#282828",  # bg
        "footer-key-foreground": "#fabd2f",  # bright_yellow
        "footer-description-foreground": "#ebdbb2",
        "input-cursor-background": "#ebdbb2",
        "input-cursor-foreground": "#1d2021",
        "input-selection-background": "#504945",  # bg2
    },
)

# Gruvbox Light theme
gruvbox_light = Theme(
    name="gruvbox-light",
    primary="#b57614",  # yellow dark
    secondary="#076678",  # blue dark
    accent="#af3a03",  # orange dark
    foreground="#3c3836",  # fg
    background="#fbf1c7",  # bg
    success="#79740e",  # green dark
    warning="#b57614",  # yellow dark
    error="#9d0006",  # red dark
    surface="#ebdbb2",  # bg1
    panel="#d5c4a1",  # bg2
    dark=False,
    variables={
        "block-cursor-background": "#3c3836",
        "block-cursor-foreground": "#fbf1c7",
        "border": "#bdae93",  # bg3
        "border-blurred": "#d5c4a1",  # bg2
    },
)

# Aliases with underscores for convenience
gruvbox_dark_alias = Theme(
    name="gruvbox_dark",
    primary=gruvbox_dark.primary,
    secondary=gruvbox_dark.secondary,
    accent=gruvbox_dark.accent,
    foreground=gruvbox_dark.foreground,
    background=gruvbox_dark.background,
    success=gruvbox_dark.success,
    warning=gruvbox_dark.warning,
    error=gruvbox_dark.error,
    surface=gruvbox_dark.surface,
    panel=gruvbox_dark.panel,
    dark=gruvbox_dark.dark,
    variables=gruvbox_dark.variables,
)

gruvbox_light_alias = Theme(
    name="gruvbox_light",
    primary=gruvbox_light.primary,
    secondary=gruvbox_light.secondary,
    accent=gruvbox_light.accent,
    foreground=gruvbox_light.foreground,
    background=gruvbox_light.background,
    success=gruvbox_light.success,
    warning=gruvbox_light.warning,
    error=gruvbox_light.error,
    surface=gruvbox_light.surface,
    panel=gruvbox_light.panel,
    dark=gruvbox_light.dark,
    variables=gruvbox_light.variables,
)

# All custom themes (both hyphen and underscore variants)
CUSTOM_THEMES = [
    gruvbox_dark,
    gruvbox_light,
    gruvbox_dark_alias,
    gruvbox_light_alias,
]
