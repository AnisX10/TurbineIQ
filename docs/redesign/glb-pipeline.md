# Turbine GLB compression pipeline

The approved pipeline keeps the source recoverable from Git history and writes the temporary trial outside the repository. It uses the existing Drei/three-stdlib Meshopt decoder at runtime. Draco is disabled for this asset, so no default decoder URL is used.

## Reproduce the trial

PowerShell:

```powershell
npx --yes @gltf-transform/cli@4.2.1 meshopt frontend/public/models/turbine.glb "$env:TEMP\turbineiq-turbine-meshopt.glb" --level high
```

POSIX shell:

```sh
npx --yes @gltf-transform/cli@4.2.1 meshopt frontend/public/models/turbine.glb "$TMPDIR/turbineiq-turbine-meshopt.glb" --level high
```

To make the approved replacement, copy the validated trial to `frontend/public/models/turbine.glb` and commit the asset change. The pre-compression asset remains recoverable from the commit history (`git show 83a7e86:frontend/public/models/turbine.glb`). No duplicate source or compressed GLB is stored in the repository.

## This run

The source was 1,910,712 bytes (SHA-256 `9869b9aeae47db510f72634b4adb3a9821a7a6569f495d8e4857c1daa13c0d5f`). Meshopt level high produced an 842,968-byte GLB (SHA-256 `ce1c922bd01380766f7914be4800727992cee014bed93566333ee5588badc3e6`), saving 1,067,744 bytes (55.9%). The output uses `EXT_meshopt_compression` and `KHR_mesh_quantization`.

Counts and ordered names were extracted from both files and compared:

| Collection | Source | Compressed |
|---|---:|---:|
| Nodes | 328 | 328 |
| Meshes | 320 | 320 |
| Materials | 8 | 8 |
| Animations | 0 | 0 |

The JSON name dumps and identical-structure result are in [`phase5/glb-structure-before.json`](phase5/glb-structure-before.json), [`phase5/glb-structure-after.json`](phase5/glb-structure-after.json), and [`phase5/glb-structure-diff.txt`](phase5/glb-structure-diff.txt). The reproducible extractor is [`phase5/dump_glb_names.py`](phase5/dump_glb_names.py).

The unchanged `tests/test_blender_asset.py` passed all three tests against the compressed asset. The glTF Transform validator reported no errors; it reports the unsupported `EXT_meshopt_compression` extension and an unused buffer as warnings. The model was also loaded and rendered through the application viewer using Drei's existing MeshoptDecoder, with a local-origin-only request log in [`phase5/viewer-network-origins.json`](phase5/viewer-network-origins.json). Before/after renders are in [`phase5/stage-after-light.png`](phase5/stage-after-light.png) and [`phase5/stage-compressed-light.png`](phase5/stage-compressed-light.png), and their dark-theme counterparts.

The screenshot difference at 873 × 841 pixels was:

| Theme | Mean absolute RGB difference | Pixels changed | Pixels with max channel difference >5 | >20 |
|---|---:|---:|---:|---:|
| Light | 0.051845 / 255 | 5.3485% | 0.15963% | 0.02166% |
| Dark | 0.047056 / 255 | 4.9535% | 0.13866% | 0.02138% |

The measured visual difference is very small at this view. The difference images are [`phase5/meshopt-visual-difference-light.png`](phase5/meshopt-visual-difference-light.png) and [`phase5/meshopt-visual-difference-dark.png`](phase5/meshopt-visual-difference-dark.png).
