# KEMETRA design tokens

Two token systems exist on purpose: the vanilla shell (`styles.css`) and the React island
(`src/shared/theme`). They must agree on colour, radius and typography.

## 1. Shell tokens — `frontend/styles.css` `:root`

| Token | Value | Use |
| --- | --- | --- |
| `--ink` | `#171717` | primary text |
| `--ink-soft` | `#333333` | secondary text |
| `--muted` | `#777777` | labels, captions |
| `--line` | `#e9e9e9` | hairlines, table rules |
| `--line-soft` | `#f1f1f1` | inner separators |
| `--soft` | `#f6f6f6` | recessed surfaces, chips |
| `--green` | `#7cbd40` | brand accent, active nav, meters |
| `--green-deep` | `#5f9c2b` | accent text on white, focus rings |
| `--orange` | `#e9a044` | congestion / density warnings |
| `--blue` | `#4b6f9e` | informational, emergency |
| `--red` | `#c74a4a` | incidents, failures |
| `--pink` | `#cb5487` | secondary categorical series |

Font stack: `"Outfit", "Inter", "SF Pro Text", -apple-system, …`. Page background `#ffffff`.

## 2. React tokens — `frontend/src/shared/theme/index.css`

| Token | Light value | Notes |
| --- | --- | --- |
| `--bg` | `#f4f6f8` | app background |
| `--surface` / `--surface-2` / `--surface-3` | `#ffffff` / `#f0f3f6` / `#e5eaef` | stepped surfaces |
| `--border` / `--border-strong` | `#d3dbe3` / `#b5c1cd` | hairlines |
| `--text` / `--text-2` / `--muted` | `#0e1621` / `#445566` / `#5e6d7c` | text ramp |
| `--accent` / `--focus` | `#5f9c2b` | green, matches `--green-deep` |
| `--accent-soft` | `#edf6e3` | accent wash |
| `--accent-ink` | `#ffffff` | text on accent |
| `--flow` / `--dense` / `--jam` / `--emergency` | `#126b3f` / `#8a5208` / `#a8262a` / `#1e4fae` | traffic states only, always with a label |
| `--radius-*` | `0px` | the whole radius scale is 0 |

Traffic colours are reserved for traffic states — never decoration — and always ship with
an icon or a label so colour is not the only signal.

## 3. Astryx mapping — `frontend/src/shared/theme/astryx-tokens.css`

`@astryxdesign/core` reads `--color-*` variables; the file maps them onto the KEMETRA ramp
(0 radius, glass cards):

| Astryx variable | KEMETRA source |
| --- | --- |
| `--color-background-body` | `--bg` |
| `--color-background-surface` | `--surface` |
| `--color-background-card` | `rgba(255,255,255,.85)` |
| `--color-text-primary` / `-secondary` / `-disabled` | `--text` / `--text-2` / `--muted` |
| `--color-accent` / `-muted` / `-on-accent` | `--accent` / `--accent-soft` / `--accent-ink` |
| `--radius-*` | `0px` |

Theme switching: `data-theme="light|dark"` on `<html>`; light is the default. The benchmark
mount additionally sets `data-theme="light"` + `data-astryx-theme="kemetra"` on its own
container, and the light block is declared for `[data-theme="light"]` too, so that subtree
stays light inside a dark page. The dark palette lives only under `[data-theme="dark"]`.

**One dark surface remains by design:** the live-map canvas. `LiveMapPage` paints its map box
`#0a0f14` and passes `theme="dark"` to `NetworkMap`, so roads and vehicle colours read on
navy; the cards, header and legend around it use the light tokens.

## 4. Chart tokens — `frontend/src/shared/charts/tokens.ts`

`readTokens()` reads the CSS variables at render time and falls back to the light theme:
text `#0e1621`, border `#d3dbe3`, surface `#ffffff`, accent `#5f9c2b`, flow `#126b3f`,
dense `#8a5208`, jam `#a8262a`, emergency `#1e4fae`. Charts therefore follow the theme
without a second palette.

Controller colours (`src/shared/domain/methods.ts`) must match the report figures
(`analysis/style.py`). The LLM controller is `#7cbd40` so it reads as part of the KEMETRA
family rather than an imported purple series.

## 5. Rules

1. New colour → add a token, never a literal in a component.
2. Radius stays 0; use `--radius-*` even when it is zero so a future change is one edit.
3. One accent: green. Purple `#5b4bd6` / `#9a8cff` is retired from `frontend/src`.
4. The map is the only dark surface; cards over it stay light.
5. Do not rename the `cotraffic-settings` localStorage key when adding fields.
