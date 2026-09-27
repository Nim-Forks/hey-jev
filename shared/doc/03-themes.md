# Theme system for the web remote

Status: **proposal — waiting for approval. No code has been changed.**

## Concept

The PTT page gets a CSS custom-property theme system. Each theme is a
block of CSS variable overrides scoped by `body[data-theme="…"]`. The
theme is stored per device in `localStorage` (`heyjev.theme`) and selected
in Settings.

## What's themed

| Variable | Controls |
| --- | --- |
| `--bg` | page background |
| `--accent` | state dot, active elements, links |
| `--text` | main text |
| `--sub` | secondary text |
| `--tile-bg` | tile background |
| `--ptt-border` | PTT button border |
| `--ptt-bg-start/end` | PTT radial gradient |
| `--ptt-glow` | box-shadow glow on hold |
| `--ptt-glow-color` | glow colour (RGB triplet for alpha compositing) |
| `--ptt-font` | PTT label font |
| `--ptt-letter-spacing` | label tracking |
| `--held-border` / `--held-color` | hold state |
| `--font` | global font family |

## Proposed themes

### 1. Default (current)
Clean dark, Segoe UI, green accents, subtle grey border. Already shipped.

### 2. HAL-9000
- Background: pure black `#000`
- PTT: deep red radial gradient (`#1a0000` → `#000`), thick dark bezel
  border, red `#ff2020` label
- Hold state: red glow `rgba(255,32,32,0.4)`, slow pulse animation
  (`animation: hal-pulse 2s ease-in-out infinite`)
- Accent: red `#ff2020`; state dot cycles orange→red instead of green
- Font: monospace, wide letter-spacing (like the HAL display)
- Tiles: dark panels with thin red borders

### 3. LOTR Ring
- Background: dark charcoal `#1a1612`
- PTT: golden radial gradient (`#3d2f00` → `#1a1612`), warm gold border
  `#c4a000`, elvish-style font (Cormorant Garamond via Google Fonts, with
  system-serif fallback), letter-spacing wide
- Hold state: golden glow `rgba(196,160,0,0.3)` with slow shimmer animation
- Accent: warm gold `#c4a000`; dot colours shifted to warm palette
- Tiles: dark parchment-tone panels, gold hairline borders
- Detail text in italic serif

### 4. Steampunk
- Background: sepia `#2a1f14`
- PTT: brass radial gradient (`#5a3a10` → `#2a1f14`), copper border
  `#b87333` with double-ring effect, serif font (Playfair Display),
  letter-spacing tight
- Hold state: copper glow `rgba(184,115,51,0.35)`, tick-tock pulse (fast
  in-out)
- Accent: copper `#b87333`; dot colours in amber/brass range
- Tiles: aged brass panels with rivet-dot borders (dotted)
- Texture: optional subtle noise overlay via CSS `repeating-conic-gradient`

### 5. Ouroboros
- Background: deep teal-black `#0a1a1a`
- PTT: teal-to-dark radial gradient, thin luminous border `#2dd4a0`,
  geometric sans font (Space Grotesk)
- Hold state: teal glow `rgba(45,212,160,0.4)` with a slow rotating
  conic-gradient ring (CSS `@property` animation) suggesting the serpent
  turning
- Accent: teal `#2dd4a0`
- Tiles: dark teal panels, thin teal borders

### 6. Matrix (bonus)
- Background: pure black
- PTT: dark green gradient, phosphor green `#00ff41`, monospace
- Hold state: bright green glow, text-scramble feel
- Accent: `#00ff41`; dot in green
- Subtle scanline overlay

## Implementation (shared/web/)

1. **CSS variables** in `index.html` `<style>`: define the current values
   as `:root { … }` (default theme)
2. **Theme blocks**: `[data-theme="hal"] { … }`, `[data-theme="ring"] { … }`,
   etc. — each overrides the variables
3. **JS**: `applyTheme(name)` sets `document.body.dataset.theme = name`
   and `localStorage.setItem("heyjev.theme", name)`; called on page load
   and from the Settings theme selector
4. **Settings**: a theme dropdown (or radio group) in the Settings page,
   stored per device
5. **Fonts**: Google Fonts `<link>` tags for Cormorant Garamond, Playfair
   Display, Space Grotesk — loaded once, only used when the theme is active
   (no network cost for the default theme)

## What's NOT themed

- The WebSocket protocol, JS logic, audio pipeline — unchanged
- The Settings page keeps its own consistent dark theme (form fields should
  stay readable regardless of the PTT aesthetic)
- Timer list, history list — inherit `--accent` / `--tile-bg` but their
  layout doesn't change

## Files touched

| File | Change |
| --- | --- |
| `shared/web/index.html` | CSS variables + theme blocks + `<link>` for fonts |
| `shared/web/app.js` | `applyTheme()`, load/save from localStorage |
| `shared/web/settings.html` | theme selector dropdown |
| `shared/remote_server.py` | serve font files (if self-hosted) or rely on Google Fonts CDN |

## Effort

~1 session: CSS variables + 5 theme blocks + settings dropdown + fonts.
Each theme is ~30-40 lines of CSS overrides; no JS logic changes.
