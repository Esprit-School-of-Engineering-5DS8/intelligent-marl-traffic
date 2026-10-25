# Live map modes — Optimize · Predict · Roam

The Events tab is the existing operations screen. This layer adds the three
mode views around it without touching the Events markup: the same map, the same
top bar, the same timeline and the same four dock cards, re-composed per mode.

Implemented in the app's own stack (vanilla ES modules + Vite + Mapbox GL) rather
than a React/TypeScript port, because the dashboard is a static Vite app and the
map, timeline and gauges already live outside React. `modes/index.js` is the
single store and controller — the same role a Zustand store would play.

```
modes/
  data.js    deterministic mock provider (recommendations, signal timing,
             forecast, roam stats, congestion geometry) behind one adapter
  index.js   store, map layers, panels, dock/timeline overrides, keyboard,
             presets, collapse, persistence
```

Swap `modeData` for a fetch-based provider and the UI keeps working.

## What each mode is for

**Optimize — "what should I change now?"**
The operator has a congested corridor and a handful of levers. The panel ranks
recommendations by delay saved, so the list is ordered by impact, not by road.
Each row carries the mechanism (signal phase, reroute, ramp meter, transit
priority), the projected gain and a confidence figure. *Preview* is the
low-risk path: it ghosts the change on the map (animated dashed reroute,
red→green congestion line), shows the before/after delta chips, and animates
both gauges to projected values with a faint ghost arc at the live value.
*Apply* is optimistic: the row becomes Applied immediately; *Dismiss* is
undoable through the toast. The scrubber gains a two-line comparison band and
Control Actions is replaced by a signal-timing editor, because in this mode the
operator is editing phases, not issuing corridor actions.

**Predict — "what will happen if…?"**
The operator is planning, not reacting. The panel leads with peak time, expected
delay and confidence; the sparkline draws the forecast against a dashed typical
day, with a dashed rule at the current scrub time. What-if chips (rain, concert,
roadworks) re-run the scenario and move the numbers; "Compare with typical day"
toggles the baseline. The scrubber grows a hatched future zone from *now* to the
end of the day whose confidence band widens as uncertainty grows, plus a
draggable forecast handle. Gauges show predicted values and keep the live value
as a ghost outline.

**Roam — "let me look at the network."**
Map-first. Panels collapse, the dock hides, the camera is free, and only a stats
strip, a compact legend and four pills remain (Follow vehicle, Fly-through,
Segments, Recenter). The Segments pill opens
an inspector listing every segment with speed and state; segments open the same
inspector focused on that road. The timeline adopts a dark glass treatment so it
reads as map furniture instead of a panel.

## Panel anatomy

Both mode panels use the same chrome as Zone Monitoring: a hairline-bordered
cream glass card, a small uppercase system chip in the top-left with the clock
on the right, a 17px title, and a highlighted summary block carrying the single
most important number. Everything below the header is composed of 10px
sub-cards with micro-label headers, tabular numerals and green accents.

- **Optimize** — summary = top impact (`−7.4 min`, confidence, applied count).
  Each recommendation is a card: rank, title/detail, kind chip, four stat pills
  (delay, flow, efficiency, confidence), an impact bar scaled against the
  strongest recommendation, then Apply / Preview / Dismiss. Previewing pins a
  green footer with three labelled deltas.
- **Predict** — summary = expected delay. A three-column readout (peak time,
  peak volume, confidence) sits above a predicted-volume card with a grid, a
  dashed typical-day baseline, a peak marker and a labelled key. "Hours at
  risk" ranks the next three peaks with green severity bars, then scenario
  chips and a switch for the typical-day comparison.

## Layout

- Left rail (400px, matching the Zone Monitoring width token): recommendations
  or forecast. The zone/queue panels fade out in these modes — the mode panel is
  the rail. The panel is content-sized like Zone Monitoring, capped at the rail
  height so long lists scroll inside the card.
- Bottom right: the timeline (unchanged geometry) sits above the dock row.
- Dock: Control Actions (signal editor in Optimize), Traffic Load, Efficiency,
  Event Log. Roam hides the row and centres the timeline.
- Top bar: identical controls plus the Panels menu (presets + per-panel toggles).
- Under 520px the mode switcher wraps to its own row; the panel starts below it
  so the switcher is never covered.

## Motion tokens

Declared on `.live-map-view` and reused by every mode surface:

| Token | Value | Use |
| --- | --- | --- |
| `--motion-fast` | 120ms | hover, button press, chip fill |
| `--motion-base` | 220ms | row entrance, crossfade, panel pill |
| `--motion-slow` | 420ms | panel entrance, mode-tab indicator, number counts |
| `--ease-standard` | `cubic-bezier(0.2, 0, 0, 1)` | everything spatial |
| `--ease-emphasized` | `cubic-bezier(0.3, 0, 0, 1.2)` | pills and popovers (gentle overshoot) |

- Mode change: green tab pill slides (`left`/`width`, 420ms); panels re-enter
  with `modePanelIn` (14px + fade); rows stagger at 35ms.
- Numbers count with a cubic ease-out over 420ms (`setDockMetric`); gauge arcs
  and the marker transition over 520ms; the ghost arc follows on the slow token.
- Map layers are faded with a 420ms `line-opacity` tween rather than toggled, so
  congestion never pops. Reroute dashes only animate while a preview is open and
  the interval stops on mode exit.
- `prefers-reduced-motion`: all animations/transitions collapse to fades or are
  disabled; count-ups jump; map fades become instant.

## Panel states

| State | Trigger | Behaviour |
| --- | --- | --- |
| Expanded | default | full panel on the left rail |
| Collapsed | minus button in the panel header | panel is replaced by a glass pill keeping the headline (`4 recommendations · −7.4 min`, `Peak 18:00 · +19 m`); the pill restores on click or Enter |
| Hidden | Panels menu toggles, `H` | panel fades + slides 10px, pointer events off; `H` restores |
| Previewing | Preview button | row gets a green ring, map reroute animates, delta strip sticks to the panel bottom |
| Applied / dismissible | Apply / Dismiss | applied rows are marked; dismissals are removed and undoable via toast |
| Preset | Full / Focus / Map only / Ops | panel visibility set; preset buttons show the active choice |

Panels are not free-draggable; the rail, dock and timeline stay in their fixed
responsive slots so the map padding never has to chase a dragged panel.

## Interaction map

- One store: `{ mode, zone, minute, previewId, applied, dismissed, inputs,
  compareTypical, panelsPreset, panelCollapsed, followMode, forecastMinute }`.
  Scrubbing writes `minute` and re-renders the panel, gauges, compare/forecast
  bands and the clock from that single value.
- Keys: `1–4` modes, `Space` play/pause, `[` `]` speed, `←` `→` scrub (`Shift`
  = 15 min), `H` hide/restore panels. Ignored while typing in a field.
- Optimize apply/dismiss use optimistic UI with an undo action in the toast.
- Persistence: zone, applied/dismissed ids, what-if inputs, compare toggle and
  the layout preset live in `localStorage` (`sumo.liveModes.v1`).

## Edge cases handled

- **Feed offline** (no API on `:8000`): play reverts and a toast reports it;
  mode data is deterministic locally, so panels still render.
- **No recommendations**: the panel shows an explicit empty state instead of an
  empty list; the collapsed pill reads "Corridor clear".
- **Map not ready / style swapped**: layers are added on `load`, retried on a
  bounded poll, and re-added on `style.load`.
- **Reduced motion**: no staggered entrances, no dash animation, instant fades.
- **Small screens**: switcher wraps, panel scrolls, pill and inspector stay
  inside the viewport, panel clears the timeline.
- **Many items** (100+ incidents): lists scroll inside the panel; no row is
  unmounted and the panel keeps its own scrollbar.
- **Disconnected / stale preview**: preview state is cleared when switching away
  from Optimize; applied ids are keyed by recommendation id.

## Deliberately out of scope

- Free-form panel dragging/snap-to-edge and per-mode layout persistence beyond
  the presets.
- Shared-element expand of gauge cards into a detail view.
- Tablet bottom-sheet snap points (the rail simply scrolls).
- A React/TypeScript/Tailwind/Framer Motion port; the behaviour is specified
  above and contained in `modes/index.js` if that migration happens.
