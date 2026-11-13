# TurbineIQ visual direction lock

## Taste draw and rationale

The required `design-taste-frontend` draw ran for `analytics` with the `achromatic-ledger` style, light theme, and the full TurbineIQ brief. Its recorded output is [`.taste-skill/direction.json`](../../.taste-skill/direction.json) (seed `1218131853`, drawn 2026-11-03).

```sh
node <taste-skill>/scripts/draw.mjs --app --kind analytics --brief "TurbineIQ: engineering workspace comparing a synthetic gas turbine reference model against generated observations, with 3D component inspector and cited evidence assistant" --theme light --style achromatic-ledger --keep type --out .taste-skill
```

Achromatic Ledger suits this engineering workspace because the chrome stays neutral, measurements align like a ledger, and a single blue marks the main data element. Apply `#1d5fbf` only to the synthetic observation series; reference remains ink and comparisons remain grey. The product's own face is the blue-grey meter ground `#f2f4f7`, not the default `#f8f8f8`.

The exact draw selected a 55px icon rail and an analytics report-card-with-legend-table pattern. The earlier plan chose an Open plane with a 240px labelled sidebar. The draw is the visual authority per this task, so sections 3 and 5 of the plan now lock the icon rail; phone navigation uses a bottom bar with short labels. The report-card-with-legend-table pattern is mapped to the existing Component ledger beside the Stage; the timeline keeps direct labels and its table fallback instead of a redundant two-series legend, as section 8 requires. The engineering-specific Stage, station ledger, and screen content remain governed by plan section 6. The Phase 2 shell now implements the rail, mobile bar, page header, and boundary sheet; current verification is recorded below.

## Final design tokens

The shell starts with the System theme preference; users can choose System, Light, or Dark. The light tokens are the fallback, and OS dark preference selects the dark tokens. `--control` is reserved for dividers; `--control-strong` is used for field, select, and segmented-control boundaries and measures at least 3:1 on both surface and ground in both themes.

| Token group | Light | Dark |
|---|---|---|
| Ground / surface / raised | `#f2f4f7` / `#ffffff` / `#eceff3` | `#0e0f11` / `#141518` / `#1c1d21` |
| Border / rule / divider control / strong control | `#e2e6eb` / `#eef1f4` / `#cfd5dc` / `#858a94` | `#26282c` / `#1d1f23` / `#3a3d42` / `#686e77` |
| Text / muted / accent | `#0a0a0a` / `#6b6b6b` / `#141414` | `#f2f3f4` / `#9a9ea5` / `#f2f3f4` |
| Chart 1 / chart 2 / chart 3 | `#141414` / `#8a8a8a` / `#1d5fbf` | `#f2f3f4` / `#7d828a` / `#6ea2f0` |
| Positive / negative / warning | `#2e7d32` / `#c4242a` / `#92400e` | `#5fc39c` / `#ef6b7a` / `#d9a441` |
| Positive pill background / ink | `#dcfae5` / `#04250e` | `#1b2828` / `#5fc39c` |
| Negative pill background / ink | `#ffedea` / `#831c1e` | `#2c1a20` / `#ef6b7a` |
| Warning pill background / ink | `#fffbeb` / `#92400e` | `#2a2416` / `#d9a441` |
| Neutral pill background / ink | `#eeeeee` / `#3d3d3d` | `#212226` / `#c9ccd1` |
| Stage background / part / edge / selected | `surface` / `#d9dde3` / `#8a8f98` / `chart-3` | `surface` / `#626872` / `#686e77` / `chart-3` |

Shape and type values stay as specified in plan section 4: card radius 8px, control radius 6px, pill radius 999px, row 44px, control 36px, filter 28px, 55px desktop icon rail, 12px gap, 24px card padding, 32px page gutter; 24px title, 16px section title, 30px KPI, 14px body, 12px small text. Motion is 120-240ms with opacity/transform only. Keep chart and residual meaning independent of hue.

### Contrast measurements

Ran `python docs/redesign/contrast_check.py`. Text and pill ink require 4.5:1; UI and chart marks require 3:1. Status text is measured on both surface and ground, the stage edge against the stage background, and the strong control edge against surface and ground. All 40 measured pairs pass.

| Theme | Pair | Ratio | Minimum |
|---|---|---:|---:|
| Light | `--text` on `--surface` | 19.80:1 | 4.5:1 |
| Light | `--text` on `--ground` | 17.97:1 | 4.5:1 |
| Light | `--muted` on `--surface` | 5.33:1 | 4.5:1 |
| Light | `--muted` on `--ground` | 4.84:1 | 4.5:1 |
| Light | `--control-strong` on `--surface` | 3.47:1 | 3.0:1 |
| Light | `--control-strong` on `--ground` | 3.14:1 | 3.0:1 |
| Light | `--chart-2` on `--surface` | 3.45:1 | 3.0:1 |
| Light | `--chart-3` on `--surface` | 6.10:1 | 3.0:1 |
| Light | `--accent` on `--surface` | 18.42:1 | 3.0:1 |
| Light | `--stage-edge` on `--stage-bg` | 3.25:1 | 3.0:1 |
| Light | `--stage-part` on `--stage-bg` | 1.36:1 | 1.0:1 |
| Light | `--positive` text on `--surface` | 5.13:1 | 4.5:1 |
| Light | `--positive` text on `--ground` | 4.65:1 | 4.5:1 |
| Light | `--negative` text on `--surface` | 5.78:1 | 4.5:1 |
| Light | `--negative` text on `--ground` | 5.25:1 | 4.5:1 |
| Light | `--warning` text on `--surface` | 7.09:1 | 4.5:1 |
| Light | `--warning` text on `--ground` | 6.43:1 | 4.5:1 |
| Light | Positive pill ink on background | 14.77:1 | 4.5:1 |
| Light | Negative pill ink on background | 8.63:1 | 4.5:1 |
| Light | Warning pill ink on background | 6.84:1 | 4.5:1 |
| Light | Neutral pill ink on background | 9.36:1 | 4.5:1 |
| Dark | `--text` on `--surface` | 16.43:1 | 4.5:1 |
| Dark | `--text` on `--ground` | 17.26:1 | 4.5:1 |
| Dark | `--muted` on `--surface` | 6.79:1 | 4.5:1 |
| Dark | `--muted` on `--ground` | 7.13:1 | 4.5:1 |
| Dark | `--control-strong` on `--surface` | 3.55:1 | 3.0:1 |
| Dark | `--control-strong` on `--ground` | 3.73:1 | 3.0:1 |
| Dark | `--chart-2` on `--surface` | 4.72:1 | 3.0:1 |
| Dark | `--chart-3` on `--surface` | 7.03:1 | 3.0:1 |
| Dark | `--accent` on `--surface` | 16.43:1 | 3.0:1 |
| Dark | `--stage-edge` on `--stage-bg` | 3.55:1 | 3.0:1 |
| Dark | `--stage-part` on `--stage-bg` | 3.25:1 | 1.0:1 |
| Dark | `--positive` text on `--surface` | 8.50:1 | 4.5:1 |
| Dark | `--positive` text on `--ground` | 8.92:1 | 4.5:1 |
| Dark | `--negative` text on `--surface` | 6.13:1 | 4.5:1 |
| Dark | `--negative` text on `--ground` | 6.44:1 | 4.5:1 |
| Dark | `--warning` text on `--surface` | 8.12:1 | 4.5:1 |
| Dark | `--warning` text on `--ground` | 8.53:1 | 4.5:1 |
| Dark | Positive pill ink on background | 7.08:1 | 4.5:1 |
| Dark | Negative pill ink on background | 5.53:1 | 4.5:1 |
| Dark | Warning pill ink on background | 6.85:1 | 4.5:1 |
| Dark | Neutral pill ink on background | 9.87:1 | 4.5:1 |

## Typography

Lock Geist (Geist Sans) for text and Geist Mono for every engineering figure. Use tabular numerals so columns align; the mono flag is justified because engineering readouts are a ledger of aligned figures. Weights are Geist 400, 500, 600, 700 and Geist Mono 400, 500.

Six Latin WOFF2 files were copied at development time from Fontsource 5.3.0: [`Geist-400.woff2`](../../frontend/public/fonts/Geist-400.woff2), [`Geist-500.woff2`](../../frontend/public/fonts/Geist-500.woff2), [`Geist-600.woff2`](../../frontend/public/fonts/Geist-600.woff2), [`Geist-700.woff2`](../../frontend/public/fonts/Geist-700.woff2), [`GeistMono-400.woff2`](../../frontend/public/fonts/GeistMono-400.woff2), and [`GeistMono-500.woff2`](../../frontend/public/fonts/GeistMono-500.woff2). Their SIL Open Font License 1.1 texts are beside them as `OFL-Geist-Sans.txt` and `OFL-Geist-Mono.txt`. Source package versions: [`@fontsource/geist-sans@5.3.0`](https://www.npmjs.com/package/@fontsource/geist-sans) and [`@fontsource/geist-mono@5.3.0`](https://www.npmjs.com/package/@fontsource/geist-mono). These packages were packed only to extract the files; neither was added to package manifests or runtime dependencies. Phase 2 loads Geist and Geist Mono from these local files with `@font-face`; the unused Fira assets were removed.

## Cycle glyph

The final ink-only 24px glyph is [`cycle-glyph.svg`](glyph/cycle-glyph.svg), with a 1.75px closed four-station loop that uses more of the 24px grid; the isobar edges are gently curved. The preview is available as [SVG](glyph/cycle-glyph-preview.svg) and [WebP](glyph/cycle-glyph-preview.webp), showing 16px, 20px, 24px, and 48px sizes on light `#f2f4f7` and dark `#0e0f11` grounds. The 16px variant omits station dots.

Geist and Geist Mono do not include U+2009 or U+202F; Geist Mono does not include U+25B2, and neither face includes U+25BE. Units are rendered in a separate span with `margin-inline-start: 0.25em` or separated with U+00A0. Direction and flag markers use Lucide icons or SVG shapes. These four unsupported characters are excluded from product UI copy.

## Search findings and interaction refinements

The exact six requested searches, the two narrow retries, their relevant matches, and what changed are recorded in [UI_UX_FINDINGS.md](UI_UX_FINDINGS.md). They support direct chart labels and table fallback, keyboard focus and skip navigation, accessible icon names and states, reactive reduced motion, and narrow React state consumers. The chart palette and library suggestions were not adopted because Taste and the project plan specify the blue and hand-rolled SVG.

The UI/UX Pro Max canonical pre-delivery checklist and quick-reference sections 1-3 were reviewed. The plan requires accessible icon states, reactive reduced motion, and sample-update render isolation. At Phase 1 close, only token contrast and the glyph preview were verified; Phase 2 implementation and its checks are documented below.

## Phase 1 verification (historical)

- `npm run build`: passed; the existing lazy 3D chunk advisory remains. The build copies the font assets into `dist`, but `frontend/src` has no Geist references, so the UI does not request them.
- `npm run lint`: passed (exit 0).
- `python docs/redesign/contrast_check.py`: passed all 40 light/dark contrast pairs, including strong controls, chart 2, status text on both backgrounds, and the stage edge.
- Unsupported-glyph scan: no U+2009, U+202F, U+25B2, or U+25BE characters remain in docs or frontend source.
- Font integrity check: all six files have the WOFF2 signature; both complete SIL OFL 1.1 texts are present.
- Chrome headless rendered the preview at 720x360; the 16px, 20px, 24px, and 48px marks were visually inspected on both grounds. The 16px variant has no station dots.
- `git diff --check`: passed.

The Phase 0 Python gates (Ruff and 69 pytest cases) are recorded in [BASELINE.md](BASELINE.md). No Python or application source changed in Phase 1, so they were not rerun after the direction assets were added.

## Phase 1 assumptions, limits, and deviations (historical)

- Assumed the task's defaults: Geist plus Geist Mono; light first with dark as a later token swap.
- The direction remains synthetic-only, local-first, and simplified; this phase adds no OEM data, physical connectivity, or runtime network requests.
- The generated icon rail supersedes the earlier plan's Open plane/labelled sidebar. The plan now records this explicit visual direction change. The report-card-with-legend-table pattern remains in `direction.json`; its fit beside the engineering Stage has not been implemented or checked in a live redesigned UI.
- At Phase 1 close, fonts were committed but unused. No Python API, type definition, component ID, GLB contract, or GLB asset was changed.
- Phase 1 changed no application files. Phase 2 adds the shell and token integration described below.

## Phase 2 and Phase 3 implementation status

Phase 2 is complete. The 55px IconRail, accessible destination links, safe-area-aware MobileBottomBar, PageHeader, utilities menu, BoundarySheet, local fonts, first-paint theme initialization, hash router, reducer/context store, format utilities, and shared published-reference constant are implemented. Evidence, Assistant, and the basic component detail remain on their legacy/transition screens until Phase 4.

Phase 3 Overview is implemented as a live API-backed engineering screen: compound filters, four ledger-style KPIs, interactive turbine stage, station and component ledgers, sample timeline with residual strip, table alternative, playback controls, URL state, reduced-motion behavior, skeleton and request error states, and 320px reflow. The one-percent colour budget, type, controls, and stage colors are checked in the finished browser at all four planned widths.

- Phase 2 commands, accessibility and network results, screenshots, skill inspections, and limitations: [PHASE2.md](PHASE2.md).
- Phase 3 feature decisions, TurbineViewer change log, test outputs, contrast measurements, screenshots, bundle comparison, and Lighthouse results: [PHASE3.md](PHASE3.md).
- Overview colour share at 1440, 1024, 768, and 375px is 0.1%, 0.2%, 0.2%, and 0.2%. The blue chart series remains the sole broad data hue. The mono flag is justified once above because aligned engineering readouts are a ledger of figures.
- No light-stage lighting intensities changed after visual review; the metal model remained legible without looking washed out. GLB selection emission was reduced after the measured tablet colour budget exceeded 1%.
- The public API, Python behavior, frontend types, six component IDs, and GLB contract remain unchanged. No new runtime dependency, remote request, DCS/SCADA/PLC path, or industrial connectivity was added.
