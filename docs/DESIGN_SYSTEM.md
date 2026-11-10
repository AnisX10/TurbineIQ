# TurbineIQ design system

This guide describes the shared visual and interaction rules for the React workspace. The canonical CSS values live in `frontend/src/index.css`; route components should consume semantic tokens instead of introducing screen-specific palettes.

## Principles

- Keep surfaces quiet and information dense. Prefer clear headings, compact ledgers, direct chart labels, and small factual notes over decorative cards, gradients, shadows, or ornamental icons.
- Keep the visual language neutral. Use the chart blue for data emphasis and semantic colors for positive, negative, and warning signals. The inspected interface keeps non-neutral accent coverage below one percent.
- Keep numbers aligned. Geist Mono is justified for tabular engineering values, signed residuals, seeds, timestamps, and tool arguments/results. Use it selectively rather than for body copy.
- Mark synthetic values and provenance close to the data. Missing values use an em dash and retain their unit. A status is never encoded by color alone.
- Keep interaction reversible and local by default. Motion is opt-in where practical and respects reduced-motion preferences.

## Typography and spacing

Use the local Geist files for interface text and Geist Mono for aligned values. Available text weights are 400, 500, 600, and 700; Mono uses 400 and 500. Do not rely on thin space, narrow no-break space, triangle glyphs, or down-caret glyphs that these bundled fonts do not provide. Put a unit in its own span with `margin-inline-start: 0.25em`, or use a normal non-breaking space where a separate span is not appropriate. Use Lucide or inline SVG for directional markers.

The Stage and form-control hit areas are at least 44 by 44 CSS pixels. Small labels and chart axes remain at least 11 px. Use the global `--dur-slow` value for camera motion, and disable interpolation when reduced motion is requested.

## Semantic tokens

| Token | Light | Dark | Use |
| --- | --- | --- | --- |
| `--ground` | `#f2f4f7` | `#0e0f11` | Application canvas and rail background |
| `--surface` | `#ffffff` | `#141518` | Main panels and dialogs |
| `--raised` | `#eceff3` | `#1c1d21` | Neutral selected/raised state |
| `--border` | `#e2e6eb` | `#26282c` | Panel edges |
| `--rule` | `#eef1f4` | `#1d1f23` | Fine dividers |
| `--control` | `#cfd5dc` | `#3a3d42` | Low-emphasis dividers |
| `--control-strong` | `#858a94` | `#686e77` | Fields, selects, segmented-control boundaries |
| `--text` | `#0a0a0a` | `#f2f3f4` | Primary ink and leader lines |
| `--muted` | `#6b6b6b` | `#9a9ea5` | Secondary labels |
| `--chart-1` | `#141414` | `#f2f3f4` | Reference series |
| `--chart-2` | `#8a8a8a` | `#7d828a` | Secondary neutral series |
| `--chart-3` | `#1d5fbf` | `#6ea2f0` | Observation series and selected-part outline |
| `--positive` | `#2e7d32` | `#5fc39c` | Positive text/status |
| `--negative` | `#c4242a` | `#ef6b7a` | Negative text/status |
| `--warning` | `#92400e` | `#d9a441` | Warning text/status |
| `--stage-bg` | `var(--surface)` | `var(--surface)` | Stage canvas |
| `--stage-part` | `#d9dde3` | `#626872` | Schematic/model neutral part color |
| `--stage-edge` | `#8a8f98` | `#686e77` | Stage frame and schematic outlines |
| `--stage-selected` | `var(--chart-3)` | `var(--chart-3)` | Selected mesh outline |

`--control` is reserved for low-emphasis dividers. Use `--control-strong` for interactive boundaries; the contrast checker verifies required token pairs in both themes. System, Light, and Dark modes share the same token names.

## Shared components

- **Shell:** `IconRail`, `MobileBottomBar`, `PageHeader`, theme menu, engine status, and Boundary sheet.
- **Overview:** `FilterRow`, `KpiRow`, `StageCard`, `StationLedger`, `ComponentLedger`, `ComponentMetrics`, `TimelineChart`, and `ReplayTimeline`.
- **Component detail:** breadcrumb, keyboard-operable Metrics / Over time / Evidence tabs, metric ledger, charts, and published-reference block.
- **Evidence:** compound local search, ranked result rows, citation chip, and plain-text reader.
- **Assistant:** Local / Cloud segmented mode, context chips, answer and trace ledger, consent Sheet, and keyboard-operable composer.
- **Shared UI:** native-dialog `Sheet` and `EngineOfflineBanner` in `frontend/src/components/ui/`.
- **Viewer:** local GLB, schematic fallback, stage toolbar, mesh picker, selected-part outline and callout.

## Accessibility rules

- Keep the skip link and one main landmark. Give each route a clear page heading and each section a heading.
- Icon-only controls need an accessible name and state. Rail links retain `aria-label` and `aria-current`; visible tooltips supplement, never replace, the accessible name.
- Keep touch targets at least 44 px where the interaction is compact. Keep a visible 2 px keyboard-focus outline with separation from the control edge.
- Preserve keyboard navigation for menus, segmented controls, tabs, chart tables, playback, part selection, and dialogs. Escape closes sheets; opening/closing a sheet manages focus entry, trap, and return.
- Respect reduced motion. Do not auto-rotate the model; rotor motion is opt-in and disabled under reduced motion.
- Never make status depend only on color. Retain labels, signs, icons, or shape markers beside semantic color.
- Render retrieved excerpts as text, not HTML. Keep citations and provenance visible with the passage or metric they qualify.
- Keep chart text at least 11 px, expose a table alternative for the timeline, and provide readable value text for the replay scrubber.

For the recorded visual direction, measured contrast, and phase evidence, see the [redesign index](redesign/README.md) and [DIRECTION.md](redesign/DIRECTION.md).
