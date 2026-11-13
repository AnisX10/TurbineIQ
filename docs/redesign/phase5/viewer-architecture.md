# Phase 5 viewer implementation

## Module split

`frontend/src/features/viewer/` contains the Canvas shell, GLB model, schematic, component and mesh selection mapping, camera controller, theme tokens, lights, and shared viewer types. The public `TurbineViewer` props and six component IDs remain unchanged. `StageCard` lazy-loads the new feature module. The mapping tests cover the existing component aliases and GLB mesh-name rules.

## Selection treatment

Selected GLB meshes use a 1.5 CSS-pixel, screen-scaled outline in `--stage-selected`. A 12px HTML label and a thin leader line follow the selected mesh. The schematic fallback has the matching HTML label and keeps its simple selection ring. The selected material no longer receives emissive highlighting. No bloom, glow, gradient, or added floor reflection is used. Status remains in the Component ledger.

Light and dark Stage captures before and after the selection treatment are in [`stage-before-light.webp`](stage-before-light.webp), [`stage-before-dark.webp`](stage-before-dark.webp), [`stage-after-light.webp`](stage-after-light.webp), and [`stage-after-dark.webp`](stage-after-dark.webp). The before images were captured from the B1 viewer at the same 1440px viewport and component selection as the after images.

## Camera and rendering

Reset and isolate camera moves ease over the `--dur-slow` token (240ms). The controller observes `prefers-reduced-motion` while mounted and applies destinations immediately when reduction is requested. A capped delta keeps the transition smooth after demand-rendering idle periods. The Canvas uses `dpr={[1, 2]}` and `frameloop="demand"`; OrbitControls invalidates on control changes, scene state/theme changes explicitly invalidate, camera transitions invalidate only while moving, and rotor motion invalidates while enabled. Auto-rotate remains off.

## Viewer change log

- B1: split the 720-line viewer into modules without changing its public props, model asset, component IDs, GLB naming rules, and interactions.
- B2: added mesh outlines and HTML callouts; removed the previous selected-material emissive glow from both GLB and schematic views.
- B3: moved reset/focus camera movement into a reduced-motion-aware controller and set the renderer DPR cap to 2.
- B4: switched the renderer to on-demand frames and added invalidation for theme, selection, view, explode/isolate, model, camera, controls, and rotor state.
- B5 verification: delayed non-Overview route code in separate chunks, retaining a dimensioned route skeleton so those screens do not add to the initial Overview bundle.
- Runtime fix: mounted Drei HTML callouts in a stable Stage-owned overlay instead of the Canvas event target. This preserves label positioning and avoids a React `removeChild` error during viewer initialization and responsive resizes. The public `TurbineViewer` props are unchanged.

## Focused validation

`npm run build --prefix frontend`, `npm run lint --prefix frontend`, and `npm test --prefix frontend` passed (18 tests). The full Playwright suite passed all 16 tests. Its four viewer tests cover keyboard access through stage controls and mesh pickers for all six components, idle-frame/camera/rotor behavior, reduced-motion behavior, and resizing the loaded GLB without browser errors. Final command output is recorded in [`final-build.log`](final-build.log), [`final-lint.log`](final-lint.log), [`final-vitest.log`](final-vitest.log), and [`final-playwright.log`](final-playwright.log).
