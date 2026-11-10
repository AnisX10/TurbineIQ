# Phase 5 B1: Viewer module split

The viewer has been split into focused modules under `frontend/src/features/viewer/`: the `TurbineViewer` shell, `GLBModel`, `SchematicTurbine`, selection and mesh metadata mapping, camera reset, theme tokens, and scene lights. `StageCard` now lazy-loads the feature module. The public viewer props, six component IDs, mesh alias mapping, and GLB loading behavior remain unchanged.

Selection tests cover all existing component aliases, metadata and parent-name mapping, mesh inspection fields, and rotor mesh-name patterns.

Validation: `npm run build --prefix frontend`, `npm test --prefix frontend` (18 tests), and `npm run lint --prefix frontend` passed. Full outputs are in the adjacent `b1-*.log` files.
