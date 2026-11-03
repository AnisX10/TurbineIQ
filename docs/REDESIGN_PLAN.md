# TurbineIQ — End-to-End Redesign Plan

Minimalist SaaS direction · written for Codex · 2026-11-03

This file is the single source of truth for the redesign. Put it at `docs/REDESIGN_PLAN.md` in the repo and tell Codex to read it first. Section 15 holds the copy-paste master prompt.

---

## 0. How to read this plan

**Goal.** Replace the current dark, teal, Fira-based interface with a quiet, light-first, minimalist SaaS interface that feels like a precision instrument and has its own identity.

**Non-goals.**
- No change to the Python API, the JSON shapes in `frontend/src/types.ts`, the component IDs, or the Blender/GLB contract in `docs/BLENDER_INTEGRATION.md`.
- No new product features (no auth, billing, teams, or live-plant connectivity). The product stays a local, synthetic-only prototype.
- No landing or marketing page. This is an app, so every screen is an app screen.

**Skill roles and precedence.** Three skills are supplied. They do different jobs, and they conflict if all three are allowed to set visual tokens.

| Skill | Role in this project | Authority |
|---|---|---|
| `taste-skill` (design-taste-frontend) | Art direction for the app screens, the house rules, the lint and inspect gates | **Wins on every visual decision** (colour, type, layout, chrome) |
| `ui-ux-pro-max-skill` | UX, accessibility, chart and interaction guidance; pre-delivery checklist; React and three.js stack tips | **Wins on accessibility and interaction.** Use `--domain ux`, `chart`, `icons`, `react`, `--stack react`, `--stack threejs` |
| `frontend-slides` | Builds the 16:9 HTML demo deck only (Phase 8) | **Not used for the app UI** |

Rules for conflicts:
1. If taste-skill and ui-ux-pro-max disagree on a visual token, taste-skill wins.
2. If they disagree on accessibility or interaction, the stricter rule wins.
3. Do **not** run `ui-ux-pro-max --design-system` and adopt its output. I ran it for this brief. It returned a marketing "Enterprise Gateway" landing pattern, a generic blue and amber palette, and Fira Code with Fira Sans. That is the wrong product shape, and it is almost exactly the current look. Use its domain searches instead.

---

## 1. Audit of the current UI

Read from the code in `frontend/src/`:

| Area | Today |
|---|---|
| Theme | Dark only. Teal `--accent: #69cbd3`. Fira Sans and Fira Code. |
| Shell | 58px icon-only rail, a top bar with breadcrumb and a "Synthetic data" badge, a footer line. |
| Navigation | Two pages switched with `useState`. No URLs, so nothing can be linked or reloaded to the same view. |
| Overview page | Title and scenario/seed controls, scenario description, four equal metric cards, 3D viewer beside a component inspector, a timeline card (SVG chart, play button, scrubber, event row), a trust strip. |
| Code shape | `App.tsx` 541 lines (page plus five components), `TurbineViewer.tsx` 759 lines, one 683-line CSS file, 5 media queries. The viewer hardcodes `SELECTED_TONE = '#56d0db'` instead of reading a token. The chart is a fixed 960×210 SVG viewBox. |
| Docs drift | `DEMO_GUIDE.md` says no GLB exists. The README says the GLB auto-loads. Fix both during Phase 7. |

**Design problems to solve**
1. **No identity.** Fira plus a dark teal accent is the default dashboard kit. taste-skill calls this "a well-applied kit, not a product".
2. **Flat hierarchy.** Four equal KPI cards, but the residual (observation minus reference) is the story.
3. **Chrome carries colour.** The accent sits on navigation and controls, not on data.
4. **Icon-only rail** hides labels people need, and the top bar repeats the breadcrumb.
5. **Provenance is scattered** across a badge, a trust strip, and the footer.
6. **Hardcoded values** in the viewer prevent a clean theme switch.
7. **State is not in the URL**, which is a poor fit for a product whose whole point is reproducible seeds.

**Must survive the redesign:** the synthetic-only boundary on every screen, server-recomputed assistant context, keyboard operation, local-first behaviour (no external requests), the lazy-loaded 3D chunk.

---

## 2. Design brief

**Product truth.** TurbineIQ compares a deterministic reference model of a simplified gas turbine against generated synthetic observations, shows where they depart, lets you inspect each component in 3D, and answers questions with cited local evidence.

**Users.** An engineer or reviewer in a meeting or a long working session. Technical, time-poor, sceptical of black boxes.

**One question per screen.**
- Overview: *Where does the observation depart from the reference, and which component is involved?*
- Component: *What is this component doing in this sample, against its reference?*
- Evidence: *What do the local notes say, and where exactly?*
- Assistant: *Can I get a bounded, cited answer with the tools it used shown?*

**Six principles**
1. **Instrument, not dashboard.** Sparse, exact, calm.
2. **Colour goes on data, never on chrome.**
3. **Provenance is a first-class element.** Quiet, but one click away from every figure.
4. **One question per screen.** Anything that does not serve it moves out.
5. **Reproducible by URL.** Scenario, seed, sample and component live in the address.
6. **Local-first, visibly.** Bundled fonts, no CDN, no external requests.

---

## 3. Direction (decided)

**Style: "Achromatic ledger"**, dealt by `taste-skill` for an app screen of kind `analytics`, light theme. **Shell: "Open plane."**

Why it fits: the chrome holds no colour at all, figures read as columns in a ledger, and exactly one hue marks the main data element. That is minimalist SaaS in the Linear, Stripe, and Vercel family, and it suits an engineering instrument.

**The three "face" choices** (taste-skill requires one or more, so the product does not read as a kit):
1. **Ground from the product's world:** blue-grey `#f2f4f7` (the sheet's "ledger or meter" ground) instead of `#f8f8f8`. Cards stay white.
2. **The one chart hue `#1d5fbf` on the synthetic observation series.** Everything else is ink or grey.
3. **Every figure in Geist Mono**, text in Geist. Tabular digits so columns of values stack. taste-skill's inspector flags mono, so state this reason in the report: *engineering readouts are a ledger of aligned figures.*

**Signature element only this product has: the Station ledger (amended after Phase 0 review).** A thin horizontal strip under the 3D stage shows four Brayton stations in axis order: 1 Compressor inlet → 2 Compressor discharge → 3 Turbine inlet → 4 Turbine exhaust. It shows temperature only: station 1 shows synthetic ambient temperature and ambient pressure from the scenario input (no reference values are supplied); stations 2–4 compare reference and synthetic temperatures where both values exist. The browser API has no per-station pressure values, so the UI must not show them and this redesign must not extend the backend. Selecting a component highlights its station pair, and hovering a station highlights the matching part in 3D.

**Brand mark: the cycle glyph.** A closed four-vertex loop drawn on a 24px grid, 1.5px stroke, ink only. The four vertices are the four stations of the cycle (a T–s diagram silhouette). Starter path (refine by eye):

```svg
<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linejoin="round" aria-hidden="true">
  <path d="M5 19 L7 9 Q13 6 19 4 L18 13 Q12 17 5 19 Z"/>
</svg>
```

Wordmark: `TurbineIQ`, Geist 600, 15px, ink. Never a coloured or black square tile with a letter.

**Rejected alternatives** (for the record): `framed-sheet` (L-shaped tinted frame fights a 3D stage), `accent-ladder` (tinted areas introduce brand colour in the chrome), and keeping the current dark `data-terminal` (it is the generator-default look). A dark theme still ships as a token swap in Phase 6.

---

## 4. Design tokens

Create `frontend/src/design/tokens.css`. Values for the light theme are taken from the dealt sheet except the ground (see §3). Dark values are a derived starting point: verify every pair with the contrast checks in §13.

```css
:root {
  /* ground and surfaces */
  --ground: #f2f4f7;
  --surface: #ffffff;
  --raised: #eceff3;
  --border: #e2e6eb;
  --rule: #eef1f4;
  --control: #cfd5dc;

  /* ink */
  --text: #0a0a0a;
  --muted: #6b6b6b;
  --accent: #141414;          /* the one primary action is near-black */

  /* data */
  --chart-1: #141414;         /* reference model */
  --chart-2: #8a8a8a;         /* comparison / synthetic truth */
  --chart-3: #1d5fbf;         /* synthetic observation: the one hue */
  --positive: #2e7d32;
  --negative: #c4242a;
  --warning: #92400e;
  --pill-positive-bg: #dcfae5; --pill-positive-ink: #04250e;
  --pill-negative-bg: #ffedea; --pill-negative-ink: #831c1e;
  --pill-warning-bg:  #fffbeb; --pill-warning-ink:  #92400e;
  --pill-neutral-bg:  #eeeeee; --pill-neutral-ink:  #3d3d3d;

  /* shape and rhythm */
  --radius-card: 8px;
  --radius-control: 6px;
  --radius-pill: 999px;
  --row-height: 44px;
  --control-height: 36px;
  --filter-height: 28px;
  --sidebar-width: 240px;
  --gap: 12px;
  --pad: 24px;
  --gutter: 32px;

  /* type */
  --font-sans: "Geist", system-ui, sans-serif;
  --font-mono: "Geist Mono", ui-monospace, Consolas, monospace;
  --fs-title: 24px;   /* 700 */
  --fs-section: 16px; /* 600 */
  --fs-kpi: 30px;     /* 500, mono */
  --fs-body: 14px;    /* 400 */
  --fs-small: 12px;   /* 400 */

  /* motion */
  --dur-fast: 120ms; --dur-base: 180ms; --dur-slow: 240ms;
  --ease: cubic-bezier(0.2, 0, 0, 1);

  /* 3D stage (read at runtime by the viewer; no hex literals in TSX) */
  --stage-bg: var(--surface);
  --stage-part: #d9dde3;
  --stage-edge: #8a8f98;
  --stage-selected: var(--chart-3);

  color-scheme: light dark;
}

[data-theme="dark"] {
  --ground: #0e0f11;  --surface: #141518;  --raised: #1c1d21;
  --border: #26282c;  --rule: #1d1f23;     --control: #3a3d42;
  --text: #f2f3f4;    --muted: #9a9ea5;    --accent: #f2f3f4;
  --chart-1: #f2f3f4; --chart-2: #7d828a;  --chart-3: #6ea2f0;
  --positive: #5fc39c; --negative: #ef6b7a; --warning: #d9a441;
  --pill-positive-bg: #1b2828; --pill-positive-ink: #5fc39c;
  --pill-negative-bg: #2c1a20; --pill-negative-ink: #ef6b7a;
  --pill-warning-bg:  #2a2416; --pill-warning-ink:  #d9a441;
  --pill-neutral-bg:  #212226; --pill-neutral-ink:  #c9ccd1;
  --stage-part: #2a2d33; --stage-edge: #5b6068;
}
```

**Rules that go with the tokens**
- **No shadow on anything at rest.** Separation is a 1px line or one tone step. The only shadow allowed is on floating layers (menus, tooltips, sheets): `0 4px 16px rgb(0 0 0 / 0.08)`.
- **One gap value** (12px) horizontally and vertically inside a card grid; 24px card padding; 32px page gutter.
- **Type:** Geist 400/500/600/700 and Geist Mono 400/500, self-hosted as `.woff2` in `frontend/public/fonts/` with the OFL licence text beside them (the project already does this for Fira). Remove the Fira files once the swap lands. Apply `font-variant-numeric: tabular-nums` to every figure. **Bold is for the page title and section titles, never for numbers.**
- **Colour budget:** under 1% coloured pixels on a screen in the light theme. Ink and grey everywhere; `--chart-3` only on the observation series, the selected sample marker, and the selected 3D part; red and green only as a small sign or short number where a figure changed.
- **Signs, not colour alone:** every residual shows a `+` or `−` and a small triangle. Colour never carries meaning by itself.
- **Radii:** 8px cards, 6px controls, full pills. No other values.
- **Icons:** `lucide-react`, 16px, 1.5px stroke, outline only. No icons in tinted squares. No emoji.
- **Forbidden:** gradients, glows, glass, sparklines on KPIs, rainbow charts, "Welcome back", invented vanity numbers, lorem ipsum.

---

## 5. Information architecture and shell

**Shell: Open plane.** A labelled 240px sidebar sits on the page ground with no top bar. Page header and cards start about 32px from the top. Cards are white on the blue-grey ground.

```
┌ Sidebar 240 ─────┐ ┌ Canvas (fluid, 32px gutter) ───────────────────────────┐
│ [glyph] TurbineIQ│ │ Page title (24/700)   [Synthetic · seed 42]   [actions] │
│ GE 6B.03 ref ▾   │ │ ─ tabs / filter row ─────────────────────────────────── │
│                  │ │                                                         │
│ Workspace        │ │   content cards on --surface, 8px radius, 1px --border  │
│  Overview        │ │                                                         │
│  Components      │ │                                                         │
│  Evidence        │ │                                                         │
│  Assistant       │ │                                                         │
│                  │ │                                                         │
│ ──────────────── │ │                                                         │
│ ● Local engine   │ │                                                         │
│   connected      │ │                                                         │
│ Theme  ◐         │ │                                                         │
│ Boundary ⓘ       │ │                                                         │
└──────────────────┘ └─────────────────────────────────────────────────────────┘
```

- **Asset switcher** at the top of the sidebar: reads `GE 6B.03 reference · Synthetic`. With one asset it is a static label with a chevron-less style; do not fake a menu.
- **Nav items:** 32px tall, 34px pitch, 16px outline icon plus a 14px label. Active item is a neutral grey pill (`--raised`, radius 6) inset 8px. No coloured bar.
- **Bottom of the sidebar:** engine status as **text** ("Local engine · connected / offline / checking"), theme toggle (System, Light, Dark), and a **Boundary** button.
- **The Boundary sheet** replaces the trust strip, the footer, and the badge. It is a right-side sheet listing: data provenance, model name, "simplified, not OEM-validated", "no physical connection or control", seed, scenario. The page header keeps one small chip, `Synthetic · seed 42`, that opens the same sheet. Keep the published 6B.03 reference block and its "synthetic replay is not calibrated" caveat visible on Component pages and reference it from the Boundary sheet (amended after Phase 0 review).
- **Routes (hash-based, no router dependency):**
  - `#/overview`
  - `#/components/<component_id>` (inlet, compressor, combustor, turbine, shaft, generator)
  - `#/evidence`
  - `#/assistant`
  - Shared query string: `?scenario=compressor_fouling&seed=42&i=72`. Hash routing avoids 404s on refresh, because FastAPI's `StaticFiles(html=True)` has no SPA fallback.
- **Below 1024px:** the sidebar becomes a 48px top bar (page name, menu button, at most one action). The menu opens a full-screen sheet with the nav and the same bottom utilities.

---

## 6. Screen specifications

Use **real values from the running API** (seed 42, `compressor_fouling`, sample 73 of 96). Do not invent numbers. Reference points from the demo guide: compressor synthetic efficiency about 81.2% against an 85.0% reference. Units on every figure. Missing values print as `—`. Zero prints as `0`, in grey.

### 6.1 Overview (route `#/overview`)

**Header row.** Title `Overview`. Chip `Synthetic · seed 42`. Right side: `Play replay` (secondary), no primary action here.

**Filter row** (compound outlined groups, 28px tall, 8px apart, reads as a sentence):
`Scenario | Compressor-performance drift` · `Seed | 42` · `Sample | 73 of 96 · 18:00` · `Interval | 15 min`.

**KPI row (amended after Phase 0 review).** Four equal columns, values in Geist Mono 30/500, label 12px grey above, one factual line below. No icons, no tiles, no sparklines.

| Label | Value | Line below |
|---|---|---|
| Reference model | `26.30 MW` | Fixed assumptions |
| Synthetic observation | `24.67 MW` *(ink)* | Model output + generated noise |
| Residual | `−1.63 MW ▾` *(the only coloured KPI: red sign)* | Observation − reference |
| Flagged samples | `0 / 96` | Median-absolute-deviation screen |

These are the live API values for `compressor_fouling`, seed 42, sample index 72 (73 of 96); implementers must read values and flagged counts from the current API response rather than hard-code examples (amended after Phase 0 review).

**Main band** (two columns, 8 / 4 split):
- **Left: the Stage.** A white card with a 1px border holding the 3D viewer. Keep `Load GLB` and `Schematic` as the view switch. Put `Reset camera`, `Explode view`, `Isolate component`, and the `Model sub-parts` mesh picker in the Stage toolbar; the mesh picker is also available on the Component page. Under the viewer, the **Station ledger** shows station 1 ambient temperature and ambient pressure, then temperatures for stations 2–4 with reference and synthetic values where both exist. No per-station pressure is present in the browser API, so do not show it or extend the backend (amended after Phase 0 review).
- **Right: Component ledger.** A card listing the six components as rows (44px): name, a neutral status pill, and the primary metric as a mono figure. The selected row has the same 1px ink marker as the selected 3D part. Below it, the selected component's first four metrics with their provenance in small grey text. A `Open component detail` text link goes to `#/components/<id>`.

**Timeline card** (full width, see §8). Title `Electrical output over 24 hours`, one question: *where does the observation depart from the reference?* Includes the scrubber, play control, and a `View as table` toggle.

**Behaviour**
- Scrubbing, playing, or clicking a flagged sample updates KPIs, the Stage, the Station ledger, the Component ledger, and the chart together, from one store.
- `←` / `→` step one sample, `Shift+←/→` step ten, `Home` / `End` jump, `Space` plays or pauses, `F` jumps to the first flagged sample. Disable `F` when the current run has no flagged samples. Show these in a small `?` popover (amended after Phase 0 review).
- Selecting a part in 3D or a row in the ledger selects the same component everywhere and writes it to the URL.

**States:** skeletons at final dimensions (no spinners, no layout shift); `Engine offline` banner with the exact command to start it; invalid seed shows an inline field error under the Seed group and keeps the last good run on screen.

### 6.2 Component detail (route `#/components/:id`)

Pattern: tabbed object detail.

- **Breadcrumb row** 16/600: `Overview` (grey) `/` `Compressor` (the h1) and a 24px neutral type chip `Synthetic`.
- **Tabs** (14px, 2px ink underline extending 8px past the label, on a full-width 1px rule): `Metrics` · `Over time` · `Evidence`.
- **Metrics tab:** three KPI cards (value 30 mono, label below): synthetic efficiency vs reference, discharge temperature vs reference, compressor power. Then the **metric ledger**: a table with Metric · Synthetic · Reference · Δ · Provenance. Rules and alignment only, no zebra, no header band, numbers right-aligned.
- **Over time tab:** two chart cards on one 24px gutter, from the `snapshots` array already in the API payload: (1) the component's key metric across the 96 samples against its fixed reference line, (2) the residual for the same window. Direct labels, no legend.
- **Evidence tab:** results of an evidence search seeded with the component name, as in §6.3.
- Keep the published 6B.03 reference block on the Component page, with its visible "synthetic replay is not calibrated" caveat. The Boundary sheet references that block (amended after Phase 0 review).
- Put the `Model sub-parts` mesh picker in the Stage toolbar and on the Component page (amended after Phase 0 review).
- Do not stretch a short card to match its neighbour. Do not print legend entries for series with no data.

### 6.3 Evidence (route `#/evidence`)

- **Header:** title `Evidence`, chip `Local lexical retrieval`.
- **Search:** one compound field, `Search | <query>` with the `top_k` selector as a second group.
- **Two panels, equal width.** Left: **Results**, a sorted bar list (row pitch 64px: title line with the citation chip, then a 10px single-colour relevance bar with no track, value 5px after the bar end, longest bar about 88% of the width). Right: **Reader**, the selected excerpt in 14px with the citation, source, section, and page. Excerpts are untrusted text: render as plain text, never as HTML.
- **No-evidence state:** keep the frame. Say exactly: "No supporting passage found for *query*." Show what was searched and the retrieval mode. Never fill the gap.

### 6.4 Assistant (route `#/assistant`)

- **Header:** title `Assistant`. Right side: a segmented control `Local | Cloud`. Local is the default and is labelled as the demo-safe mode.
- **Context bar** (read-only chips): `Compressor-performance drift · seed 42 · sample 73 · Compressor`. This is the server-recomputed context that the assistant receives.
- **Conversation column** (centred, max 720px). Questions are plain right-aligned text, answers are left-aligned text on `--surface` with a 1px border. No avatars, no bubbles with tails, no typing-dots theatre; use a thin 2px indeterminate rule under the composer while waiting.
- **Tool trace:** under each answer, a collapsed ledger row per call: tool name, arguments, and result in mono, expandable. This is what makes the assistant trustworthy, so make it easy to open, not hidden.
- **Cloud consent:** switching to Cloud opens a sheet that states exactly what will be sent (the question, tool results). Document excerpts are a **separate** checkbox, off by default. If cloud fails or no key exists, show the API's `warning` text in a neutral banner and label the answer `Local fallback`.
- **Suggested questions** (3, real, one line each), for example "Explain the compressor-efficiency drift result."
- **Composer:** one 36px field and one near-black `Ask` button, the only filled primary on this screen. `Enter` sends, `Shift+Enter` adds a line.

### 6.5 Global states (design every one, not just the happy path)

Loading skeleton · empty · no evidence · engine offline · invalid seed · request failed (with retry) · 3D failed (fall back to the existing schematic turbine and say so) · reduced-motion · narrow viewport.

---

## 7. The 3D stage (art direction)

- **Look.** Flat and matte. Light neutral parts (`--stage-part`) with hairline edges (`--stage-edge`) on a flat `--stage-bg`. No gradient background, no bloom, no glow, no floor reflection.
- **Selection.** The selected part gets a 1.5px outline in `--stage-selected` plus a leader line to a 12px HTML label in ink. Status is never shown as glow; it is a pill in the Component ledger.
- **Tokens, not literals.** Read `--stage-*` from `getComputedStyle` at mount and on theme change. Delete the hardcoded `SELECTED_TONE`.
- **Controls (amended after Phase 0 review).** Keep `Load GLB` and `Schematic` as the view switch. Put `Reset camera`, `Explode view`, `Isolate component`, and the `Model sub-parts` mesh picker in the Stage toolbar; keep the mesh picker available on the Component page too. `No auto-rotate` applies to the camera only. The existing `Pause rotor` control remains an opt-in, visual-only rotor animation toggle, off by default and off under `prefers-reduced-motion`. Camera moves ease over `--dur-slow`. Cap device pixel ratio at 2.
- **Accessibility.** The Component ledger is the accessible path to every part. The canvas gets a descriptive `aria-label` and is not a keyboard trap.
- **Do not touch** the component-ID aliases or the GLB mapping contract. Split `TurbineViewer.tsx` into `GLBModel`, `SchematicTurbine`, `selection`, and `camera` modules without changing behaviour; run `tests/test_blender_asset.py` after.
- Keep the 3D bundle lazy-loaded.

---

## 8. Data visualisation rules (timeline)

Hand-rolled SVG is fine under 1,000 points (this project has at most 288). Make it responsive with a `ResizeObserver` instead of a fixed viewBox. The current fixed viewBox makes axis text illegible on mobile; the rewrite must keep axis labels at a readable minimum of 11px at every width (amended after Phase 0 review).

| Series | Style | Notes |
|---|---|---|
| Reference model | `--chart-1` ink, 1.5px solid | The comparison baseline |
| Synthetic observation | `--chart-3`, 1.5px solid | **The one hue**, because it is the main data element |
| Synthetic truth | `--chart-2` grey, 1px dashed | Optional toggle; off by default |
| Residual strip | Signed bars under the main plot, grey; flagged samples in ink with a small ▲ marker | Own y-scale, zero line visible |

- Y axis is always visible with 4–5 ticks and units (MW). 3–7 faint gridlines at most. No legend for fewer than three series; use **direct end labels**.
- Series differ by **line style and direct label as well as colour** (ui-ux-pro-max chart guidance: never distinguish series by hue alone).
- Playhead: 1px ink vertical line with a readout chip (time, reference, observation, residual).
- Keyboard: the chart region is focusable. Focus reveals the values at the playhead. Arrow keys follow §6.1.
- **`View as table`** toggle replaces the plot with an accessible table plus a one-sentence trend summary.
- Honest data states: zero residual prints `0.00 MW` in grey; no flagged samples prints `0 / 96`, not a blank.

---

## 9. Voice, naming, and microcopy

The product's credibility depends on not over-claiming. Keep the existing boundary language and make it consistent.

- **Glossary (use exactly):** Reference model · Synthetic observation · Synthetic truth · Residual (observation − reference) · Residual screen · Flagged sample.
- **Never write:** fault, failure, diagnosis, anomaly detected, AI-powered, smart, insights. A flagged sample is "flagged by the residual screen".
- **Sentence case** for all UI text. Units after every value, with a thin space (`25.46 MW`). Dates and times in 24h UTC with the zone shown once in the sample filter.
- **Every empty or error message** says what happened, what it means for the data, and the next action in one line each.
- The words **synthetic** and **simplified model** appear in the header chip and in the Boundary sheet. They must never be removable by a layout change.

---

## 10. Accessibility and responsiveness

- **Contrast:** text 4.5:1 minimum, UI and chart marks 3:1, in both themes. `--muted` on `--ground` and `--chart-3` on `--surface` must be measured, not assumed.
- **Focus:** a visible 2px ring on every interactive element, never removed. Logical tab order. Skip link to main content.
- **Touch:** 44×44px hit area for every control on touch devices (the 28–36px visual height is fine if the hit area grows).
- **Colour independence:** signs and triangles accompany every colour signal.
- **Motion (amended after Phase 0 review):** 120–240ms, opacity and transform only. `No auto-rotate` applies to the camera only. The visual-only `Pause rotor` animation remains opt-in, starts off, and stays off under `prefers-reduced-motion`; reduced motion also removes autoplay interpolation and camera easing.
- **Zoom:** usable at 200% and with 320px width without horizontal scroll (the chart and tables scroll inside their own containers).
- **Breakpoints to verify:** 375, 768, 1024, 1440. KPIs go 2×2 on phones; panels stack; the Stage keeps a fixed 4:3 aspect on phones and uses touch orbit controls.
- **Screen readers:** the replay announces the selected sample politely, throttled to settle after scrubbing. Never announce every playback tick.

---

## 11. Frontend architecture

Keep the stack: React 19, Vite, TypeScript, React Three Fiber and drei, lucide-react. **Do not add a UI framework, a CSS framework, or a router.** Plain CSS with variables and CSS Modules (Vite supports them natively).

```
frontend/src/
  app/
    App.tsx              # shell + route outlet only (target < 80 lines)
    router.ts            # tiny hash router + query-string helpers
    store.tsx            # run, sample, selection, theme (useReducer + context)
  design/
    tokens.css           # §4
    base.css             # reset, focus ring, typography, reduced motion
    fonts.css            # Geist, Geist Mono @font-face (local files)
  components/
    ui/                  # Button, IconButton, Chip, Pill, Tabs, Segmented, Field,
                         # Select, CompoundFilter, Card, Kpi, DataTable, BarList,
                         # Tooltip, Sheet, Skeleton, EmptyState, Banner
    shell/               # Sidebar, MobileBar, PageHeader, BoundarySheet, ThemeToggle
    brand/               # CycleGlyph.tsx, Wordmark.tsx
  features/
    overview/            # KpiRow, ComponentLedger, StationLedger, ReplayTimeline,
                         # TimelineChart, TimelineTable
    viewer/              # TurbineViewer, GLBModel, SchematicTurbine, selection, camera
    component-detail/    # Metrics, OverTime, MetricLedger
    evidence/            # SearchBar, ResultsList, Reader
    assistant/           # Conversation, Composer, ToolTrace, CloudConsentSheet
  lib/
    api.ts  format.ts  units.ts  keyboard.ts
  types.ts               # unchanged
```

**Decisions**
- **URL is state.** `scenario`, `seed`, `i` (sample index) and the component ID are read from and written to the hash. Reloading or sharing a link restores the exact view.
- **One store** for the run payload and selection. Components receive typed props; nothing reads `useState` three levels up.
- **Theme:** `data-theme` on `<html>` (`light`, `dark`, or unset for system). Persist the choice in `localStorage` inside `try/catch`.
- **No hardcoded colours in TSX.** Anything that needs a colour reads a CSS variable.
- **Charts:** keep hand-rolled SVG, rewritten as `TimelineChart` with `ResizeObserver`, direct labels, and a table fallback.
- **New dev dependencies only:** `@playwright/test`, `@axe-core/playwright`, `vitest`, `@testing-library/react`, `jsdom`. No new runtime dependencies. If a font package is preferred over committed `.woff2` files, `@fontsource/geist-sans` and `@fontsource/geist-mono` are acceptable (both bundled, no CDN).
- **Local-first guard:** a Playwright test records every network request and fails on any host other than the page's own origin.
- **Python side:** no changes required. Run `pytest` and `ruff` unchanged as a regression guard.

---

## 12. Phased delivery

Work on a branch `redesign/v2`. Each phase ends in a mergeable state with the gates green. Sizes are relative: S, M, L.

| Phase | Size | What happens | Done when |
|---|---|---|---|
| **0. Setup and baseline** | S | Install the three skills (Appendix A). Run the app. Capture "before" screenshots at 375, 768, 1024, 1440 into `docs/redesign/before/`. Record the baseline bundle size and Lighthouse scores. | Before-set committed; `npm run build`, `npm run lint`, `pytest`, `ruff` all green. |
| **1. Direction lock** | S | Run `taste-skill draw --app` as in Appendix B and save `.taste-skill/direction.json` (it is the committed art-direction record; replace the old `data-terminal` one). Run the ui-ux-pro-max domain searches in Appendix B and note anything that tightens §10. Download Geist fonts. Draw the final cycle glyph. | `direction.json` matches §3; fonts and licence files in place; glyph SVG reviewed. |
| **2. Foundation** | M | `tokens.css`, `base.css`, `fonts.css`. UI primitives. Shell (Sidebar, MobileBar, PageHeader, BoundarySheet). Hash router, store, URL state. Delete `TurbineIQ.css` as screens migrate. | Empty routes render inside the new shell in light and dark; keyboard and focus work; `taste lint` clean on shell files. |
| **3. Overview** | L | KpiRow, ComponentLedger, StationLedger, ReplayTimeline with the new chart, keyboard map, Boundary sheet content. | §6.1 met with live API data; keyboard map works; scrubbing keeps all panels in sync. |
| **4. Component, Evidence, Assistant** | L | §6.2, §6.3, §6.4 including cloud-consent sheet, tool trace, no-evidence state. | Each screen answers its one question; all states in §6.5 exist for them. |
| **5. 3D stage** | M | Split `TurbineViewer.tsx`; token-driven scene colours; selection outline and labels; Exploded and Reset; perf cap. | §7 met; `tests/test_blender_asset.py` and API tests unchanged and green; viewer chunk still lazy. |
| **6. Dark theme and responsive** | M | Dark tokens tuned and verified. Layouts at 375/768/1024/1440. Reduced-motion paths. | Both themes pass the same gates; no horizontal page scroll at 320px. |
| **7. Hardening and docs** | M | Run all gates in §13. Fix findings. Update README screenshots, `DEMO_GUIDE.md`, `ARCHITECTURE.md`; remove the GLB contradiction. | Gates green; docs match the product. |
| **8. Demo deck** | S | Build the 3-minute demo as an HTML deck with `frontend-slides` (see §14). | Deck runs offline, 16:9 stage, exports to PDF. |

---

## 13. Quality gates and acceptance criteria

A phase is not done until every gate that applies to it passes. Do not claim a gate passed without running it and keeping the output.

| Gate | Tool | Pass condition |
|---|---|---|
| House style | `taste-skill`: `lint.mjs` on changed files, `inspect.mjs` on each route (app rules) | No errors. Warnings explained in the report. The `mono` flag is justified once, per §3. |
| Colour budget | taste inspector | Under 1% coloured pixels in light; chart hue sits on the data. |
| Accessibility | `@axe-core/playwright` on every route and both themes | Zero serious or critical violations. |
| Contrast | Measured pairs for text, muted text, chart marks, pills | Text ≥ 4.5:1, UI and marks ≥ 3:1 in both themes. |
| Keyboard | Playwright script | Every action in §6 works with no pointer; focus always visible; no trap in the 3D canvas. |
| Responsive | Playwright screenshots at 375, 768, 1024, 1440, light and dark | No overflow, no clipped rows, no orphaned KPI. |
| Local-first | Playwright network log | Zero requests to any other origin. |
| Performance | Lighthouse (performance, a11y, best practice) | Not worse than the Phase 0 baseline; a11y ≥ 95; no layout shift from skeleton to content. |
| Unit | `vitest` | Formatters (units, signs, dashes), URL-state round trip, keyboard map. |
| Backend regression | `python -m pytest -q` and `ruff check src tests` | Unchanged results (69 tests passing at baseline). |
| Build | `npm run build` and `npm run lint` | Clean. |
| ui-ux-pro-max checklist | Its pre-delivery checklist (cursor, hover timing 150–300ms, focus, reduced motion, 375/768/1024/1440) | All boxes ticked with evidence. |
| Visual review | Look at the screenshots yourself | Compare against §3 and §6; list anything you changed from the plan and why. |

**Fallback if Chrome is unavailable to the taste scripts in the Codex sandbox:** run the app, capture screenshots with Playwright's Chromium, and say plainly in the report that `inspect.mjs` could not run.

---

## 14. Demo deck (Phase 8, `frontend-slides`)

`frontend-slides` makes zero-dependency HTML decks on a fixed 1920×1080 stage. It does not apply to the app UI. Use it only for a short deck that mirrors `docs/DEMO_GUIDE.md`.

- **Density:** low, speaker-led. One idea per slide, large type, 1–3 lines.
- **Look:** reuse §4 tokens (same ground, ink, Geist, one blue). Do not pick a preset from its style library that fights the product.
- **Slides (about 8):** 1 Title and boundary (synthetic, simplified, no connection) · 2 The question · 3 Reference vs observation · 4 Compressor drift at seed 42 · 5 Component in 3D · 6 Cited evidence · 7 Assistant with tool trace · 8 Guardrails and what is next.
- **Visuals:** real screenshots from the redesigned app, not mock shapes.
- **Output:** one `demo/turbineiq-demo.html`, plus a PDF export with its export script.

---

## 15. Master prompt for Codex (copy and paste)

> You are redesigning the TurbineIQ frontend. Read `docs/REDESIGN_PLAN.md` fully before doing anything, then follow it phase by phase.
>
> **Skills.** Use `design-taste-frontend` (taste-skill) as the authority for all visual decisions and its `lint.mjs` and `inspect.mjs --app` as gates. Use `ui-ux-pro-max` only through domain and stack searches (`--domain ux|chart|icons|react`, `--stack react|threejs`) and its pre-delivery checklist. Never adopt its `--design-system` output. Use `frontend-slides` only in Phase 8 for the demo deck. If skills conflict, follow section 0 of the plan.
>
> **Constraints.** Do not change the Python API, `types.ts`, component IDs, or the GLB contract. No new runtime dependencies, no CDN or external requests, no external fonts. Keep every "synthetic" and "simplified model" statement visible. Use real values from the running API, never invented numbers. Keep the UI language in English.
>
> **Process.** Work on branch `redesign/v2`. Do one phase at a time. After each phase, run the gates that apply (section 13), keep the outputs, look at your own screenshots, and report: what changed, what you decided differently from the plan and why, and what you could not verify. Do not mark a gate as passed unless you ran it. Stop after each phase and wait for review.
>
> **Start with Phase 0 and Phase 1 only.**

---

## 16. Open decisions for Anis

1. **Typeface.** Recommended: Geist plus Geist Mono (the dealt sheet's choice, and it breaks the "default dashboard kit" look). Alternative: keep Fira for continuity. Fira is what the generator picks for any dashboard.
2. **Default theme.** Recommended: light first, dark as a full token swap. If the 3D stage is meant to feel like a dark viewport, say so before Phase 5.
3. **Scenarios page.** Not in scope. Scenario and seed live in the filter row. Add a page only if more scenarios are planned.
4. **Brand mark.** The starter glyph is a construction spec, not final art. Finalise it by hand in your design tool.
5. **Third-party names.** The UI references a published GE 6B.03 rating set. Keep it worded as "conceptual reference" with no logos or imagery implying endorsement.

---

## Appendix A — Installing the skills for Codex

**taste-skill** (needs Node 22+ and Chrome, Edge, or Chromium; no API keys):
```bash
npx skills add https://github.com/Leonxlnx/taste-skill --skill "design-taste-frontend"
# or, as a Codex plugin:
codex plugin marketplace add Leonxlnx/taste-skill
codex plugin add taste-skill@taste-skill
# start a new Codex session afterwards so the skill loads
```

**ui-ux-pro-max** (needs Python 3, standard library only):
```bash
npm install -g ui-ux-pro-max-cli
uipro init --ai codex
```

**frontend-slides** (no installer for Codex): tell Codex to read `https://github.com/zarazhangrui/frontend-slides` and follow its `SKILL.md` for Phase 8, or clone it into a local skills folder.

## Appendix B — Commands to run in Phase 1

Deal the app direction (already dealt once for this plan; re-run so the file lands in the repo):
```bash
node <taste-skill>/scripts/draw.mjs --app --kind analytics \
  --brief "TurbineIQ: engineering workspace comparing a synthetic gas turbine reference model against generated observations, with 3D component inspector and cited evidence assistant" \
  --theme light --style achromatic-ledger --keep type --out .taste-skill
```
Then apply the ground and chart-hue choices in §3 and record why in the report.

Domain searches (run from the ui-ux-pro-max `scripts/` folder; one dominant intent per query):
```bash
python3 search.py "timeline scrubber slider keyboard" --domain ux
python3 search.py "time series residual comparison line chart" --domain chart
python3 search.py "accessible chart table fallback" --domain ux
python3 search.py "icon button accessible label" --domain icons
python3 search.py "context provider performance rerender" --stack react
python3 search.py "canvas orbit controls reduced motion" --stack threejs
```

Lint and inspect during every phase:
```bash
node <taste-skill>/scripts/lint.mjs frontend/src/**/*.tsx frontend/src/**/*.css
node <taste-skill>/scripts/inspect.mjs http://localhost:5173/#/overview
```
