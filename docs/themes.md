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
