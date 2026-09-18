# Native visual quality: source geometry and appearance are separate

This extension is a **visual inspection renderer**, not a driving controller. It does not enable `require_driveable`, call Jev, run perception, or claim photorealism. It uses the same real-world coordinates for source buildings, LOD3 roads, street furniture, vegetation and the camera.

## Problems found by actually rendering

The earlier ad-hoc car-height video followed an OSM way beyond the downloaded terrain footprint. Its nearest-vertex height fallback could conceal missing ground. This extension clips the route to a connected segment inside the acquired bounds, preserves its direction, and rejects any uncovered camera/look-ahead sample. Heights are barycentric, never zero/nearest-vertex substitutes.

The Chiyoda 2025 catalogue exposes LOD3 roads, urban furniture and vegetation. These were actually fetched and decoded. The road tile inspected had **no image and roughnessFactor=0**, despite the catalogue's `texture=true` label. Catalogue flags are not proof that every primitive has a photographic texture. The unmodified road appeared mirror-like. Two explicit treatments are available: reproject the actual source orthophoto, or select the optional generic CC0 paving appearance. Neither is a measured material calibration.

LOD3 road heights differ from the coarser terrain. Rendering both can bury the correct road surface. The ground-cutout tool removes the coarse terrain only under the projected union of actual road triangles. It preserves remaining triangle planes and interpolates their UVs; it does not raise roads by an invented height offset.

## Reproduce with new output directories

Use Python 3.10+, the repository dependencies, Node 20+ and Blender 5.1. Keep the native Node executable ahead of `.cmd` wrappers in Windows PATH: wrappers requiring LOCALAPPDATA do not work in the decoder's restricted environment. No global PATH change is necessary.

```bash
python -m pip install -e ".[dev]"
npm install --ignore-scripts --no-audit --no-fund --prefix tools/gltf
# Set JEVDRIVE_DECODE_GEOMETRY=1 in this process.
python tools/fetch_quality_catalog.py --out runs/catalog.json
python tools/live_world_check.py --config configs/tokyo-marunouchi.json --out runs/city
python tools/fetch_city_details.py --snapshot runs/city --catalog runs/catalog.json --out runs/details
python tools/carve_source_ground.py --snapshot runs/city --details runs/details --out runs/ground
python tools/texture_detail_roads.py --snapshot runs/city --details runs/details --out runs/appearance
python tools/fetch_quality_assets.py --out runs/assets
python tools/prepare_quality_plan.py --snapshot runs/city --details runs/details --assets runs/assets --out runs/camera-plan.json
```

```bash
blender --background --python-exit-code 2 --python tools/blender_quality_render.py -- --snapshot runs/city --details runs/details --ground runs/ground --appearance runs/appearance --assets runs/assets --plan runs/camera-plan.json --out runs/native-source --source-only --animation --samples 64
```

Use `--paving-look` instead of `--source-only` to opt into the generic photographed paving albedo/normal/roughness. It requires the route's OSM `surface=paving_stones` tag. The current look-development option applies to imported road materials, not a surveyed lane/material segmentation; do not export it as geographic truth. The source orthophoto, unmodified LOD3 tiles and their manifests remain available separately. Native vegetation is used instead of duplicating it with the generic tree pack.

`--source-only` means no generic paving/tree injection. HDRI, exposure, a sun and non-metal facade finish assumptions are still rendering decisions. The source textures may already contain baked shadows; changing the sun cannot recover unobserved surfaces or remove their original lighting. The HDRI is not a photograph of Tokyo's weather.

`--engine CYCLES` uses the CPU explicitly in this implementation. EEVEE is the interactive-quality path. Do not report HIP/CUDA acceleration without actually configuring and testing it. Output is a packed `.blend`, PNG frames and `render-report.json`; a Python exception is a nonzero Blender process exit.

Every frame is checked against the **actual imported road triangles in Blender**. A submillimetre agreement here means only that two representations in this pipeline agree, not that the real street was surveyed to submillimetre accuracy. Cameras use 1.55m height and 80-degree horizontal FOV as configurable research assumptions, not actual vehicle calibration.

## Actual additions and remaining limits

The enlarged base snapshot contains 97,257 building triangles and 2,358 terrain triangles. The separately fetched LOD3 details add 33,705 road, 1,275 furniture and 9,515 vegetation triangles. Dataset meshes can extend beyond the AOI, and a mesh count is not a building count. Individual objects may be outside the camera view; importing a vegetation dataset does not mean every real street tree is covered.

The implemented default path has 300 frames over 10 seconds, 30fps, 4m/s and about 39.87m of camera travel. It is animation on an OSM **centreline**, not validated lane-following or vehicle motion. No traffic agents, collisions, road-rule evaluation or API-driven actuation are represented by this video.

Close-range facade textures remain visibly low-resolution. The catalogue currently selected for Chiyoda has building LOD2, not LOD3 facade geometry. Increasing samples or adding generic objects cannot establish a photo-identical digital twin. The next fidelity gate needs licensed street-level imagery/point clouds and independent camera/control-point alignment, not a claim based on a polished thumbnail.

## Sources and publication

- Chiyoda 2025 dataset: https://www.geospatial.jp/ckan/dataset/plateau-13101-chiyoda-ku-2025
- Catalogue: https://api.plateauview.mlit.go.jp/datacatalog/plateau-datasets
- PLATEAU policy: https://www.mlit.go.jp/plateau/site-policy/
- Poly Haven CC0 assets: https://polyhaven.com/license
- Sky: `kloofendal_48d_partly_cloudy_puresky`; paving: `pavement_01`; optional tree: `tree_small_02`.

On 2026-09-18 the dataset API returned `license_id=plateau` and the PLATEAU site-policy link. Its current policy permits reuse with attribution and a processing notice, and is compatible with CC BY 4.0. Preserve the OSM ODbL attribution independently. The 2025 dataset year is not the verified image-capture year; cross-epoch alignment remains unverified. Distribute rendered research previews with credits and explicit enhancement/no-Jev labels; keep raw city assets outside Git. Do not redistribute system fonts.
