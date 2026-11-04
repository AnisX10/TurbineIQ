# Offline GLB compression evaluation

**Report only:** `frontend/public/models/turbine.glb` was not modified.

The source GLB is 1,910,712 bytes. An offline `gltf-transform@4.2.1 meshopt --level high` trial produced an 842,968-byte file, saving 1,067,744 bytes (55.9%). The trial introduces `EXT_meshopt_compression` and `KHR_mesh_quantization`; the source asset uses neither extension, so adopting it would require viewer-loader/contract validation.

The original and trial renders were compared at the same 847×636 viewport. RGB mean absolute difference was 0.05158 on a 0–255 channel scale. 6.7369% of pixels differed at all; 0.06256% differed by more than 5 levels and 0.00037% by more than 20. The absolute-difference image and renders are [`meshopt-absolute-difference.png`](meshopt-absolute-difference.png), [`meshopt-original.png`](meshopt-original.png), and [`meshopt-meshopt.png`](meshopt-meshopt.png). The visual change is very small at this view. No compressed asset was substituted.
