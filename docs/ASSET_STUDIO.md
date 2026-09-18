# Asset Studio — external model replacement work

This is an isolated visual-asset workstream. It does not enable real-vehicle control, Jev inference, or the public-world driving gate. No purchase or gated license acceptance is performed.

## Actual source selection

| Source | Assets | Rights retained | Treatment |
|---|---|---|---|
| Computer Graphics Archive, Mike Pan / Morgan McGuire | BMW-derived coupe | CC0/Public Domain | Prepared car from this repository's prior native library; preserve attribution, record source identity; not a measured sedan or endorsement. |
| Poly Haven | tree_small_02, modular_street_seating, potted_plant_02, pavement_01, pavement_05, sky | CC0-1.0 | Preserve authored source textures; runtime-scale/placement changes recorded. Powered by Poly Haven. |
| Microsoft Rocketbox | Business_Male_01, Business_Female_01 | MIT, Copyright (c) 2020 Microsoft | Preserve MIT notice. Repair missing FBX texture bindings; author relaxed standing poses; retain rigged sources separately. |

Primary source policies:
- https://casual-effects.com/g3d/data10/
- https://polyhaven.com/license
- https://github.com/Poly-Haven/Public-API/blob/master/ToS.md
- https://github.com/microsoft/Microsoft-Rocketbox/blob/master/LICENSE.md

The model filenames, geometry, texture maps and authors remain identifiable in the source/download records. Public-domain mesh rights do not establish endorsement or release unrelated trademark rights. The official download catalogs are not photographs of Tokyo's current streets.

## Executed acquisition and inspection

The `asset-studio-acquisition` workflow acquired the car, three model families, two materials, HDRI and catalogue metadata. `asset-studio-people` acquired two specific avatar FBXs and matching textures; every downloaded model/texture was checked against the reviewed Git blob. `asset-studio-native-inspect` actually imported all six models with Blender 5.1.2. This exposed incorrect original-author texture paths in the Rocketbox FBX and a 2,062,487-triangle LOD0 tree.

The native integration intentionally reuses the already prepared car and source LOD1 tree from commit `46ad223ff7d8ae0ccbb6e2913d37ebfb2ba0526d`, rather than presenting previous work as newly authored. The bench is assembled from the newly acquired glTF's existing aligned components; unrelated kit variants are excluded. The potted plant retains its leaves while the excessively tessellated hidden soil is reduced. The people keep their original textured mesh and 81-bone rig; static relaxed-pose exports are separate from editable rigs.

## Native review

`tools/asset_studio/render_review.py` exports six GLBs plus an editable asset-library `.blend`, then constructs an **authored art-review street** with real external assets and modeled storefront depth. It renders car-height, car-detail and sidewalk-detail images with Cycles CPU. This is a new inspection stage, not a claim that the existing 640m v0.6 district has already been modified. Dimensions, ground contacts, exact source hashes, native version, samples and elapsed time are recorded.

The area of the authored base is 640m x 400m; the detailed frontage is much shorter. A large ground rectangle is not a complete detailed city. The models and source v0.6 district remain independently reusable.

The current native workflow performs 1280x720/16-sample diagnostic stills first. Those images must be visually reviewed before any high-resolution production render is called approved. Test success or a saved `.blend` is not proof of photorealism.

## Local reproduction after downloading workflow artifacts

Run in a new directory. Do not copy over another worktree or existing output:

```bash
python -m pip install bpy==5.1.2 Pillow==12.3.0
python tools/asset_studio/render_review.py \
  --assets /path/to/reviewed-external-assets \
  --people /path/to/reviewed-business-avatars \
  --legacy-library /path/to/unpacked/hero-library \
  --out /new/path/native-review --samples 16 --width 1280
```

`hero-library` is the previously completed native library from workflow run `35385727394`; acquisition run IDs are fixed in the review workflow. Workflow artifacts expire, so retain the source locks and source archive before reproduction. The downloader can create a **new** snapshot from the public sources; never silently replace an existing locked source.

## Remaining integration gates

- Compare the actual new renders, not only code/triangle counts; correct orientation, skin shading, bench assembly and visible material tiling.
- Validate the six exports in the existing v0.6 district before claiming its placements were replaced.
- Establish matched-camera old/new comparisons from that actual district.
- Rigged walking, foot locking, crowd behavior, braking/indicator timing and physics remain separate tasks. Static character exports are not motion-captured pedestrians.
- Facade changes, repeated people/trees, glass, shadows and paving scale require visual review. Generic source assets are not a surveyed reconstruction.
- Preserve source notices and keep every font file out of project deliveries. No Blender runtime is part of the asset pack.
