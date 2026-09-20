# Native authored-district playback

This is executable Blender scene playback, not a planning checklist. It preserves the existing Jev and real-public-world code paths.

The independently delivered Urban District v0.7 package contains the authored district generator, external-model normalizer, UV/alpha/material repairs, asset replacement code, verified raw assets, prepared LODs, generated GLB and tests. This repository experiment contains the reusable native playback engine. Raw assets, generated city meshes, renders and Blender binaries are deliberately not committed.

In the consolidated PR #5–#11 integration, this directory is an **experimental playback layer**. Canonical reusable asset acquisition/preparation lives in the PR #9 hero-library and PR #10 Asset Studio paths. The former PR #11 acquisition/runtime workflows are preserved verbatim under `workflows/historical/` so the executed evidence is not lost, but they are not active Actions here.

Run with the delivered `output/district-release` directory:

```sh
blender --background --python-exit-code 2 --python experiments/urban-render/tools/blender_district.py -- --scene /path/to/output/district-release --out /path/to/new-render --engine CYCLES --samples 32 --frame 1 --detail-views
```

The output directory must not already exist. PNG renders and a packed `.blend` scene are written with a machine-readable report. The GLB and HDRI hashes are checked before use. Integer animation frames are baked explicitly; the render material path keeps glTF transmission and clearcoat rather than the VTK preview's approximate opacity.

`--animation` requests all frames; `--render-stills` requests beginning/middle/end. These options execute real rendering, not promises of completed outputs. CPU rendering can be expensive. Only outputs listed in a completed `render-report.json` count as evidence.

The broader source package replaces six procedural sedans and twelve near-camera trees, adds eight potted plants and four detailed entry assemblies, and replaces road/sidewalk PBR surfaces. The source car is Khronos's CC0 **toy** model scaled to 4.3 m, not surveyed real-vehicle geometry. Surface choices and vegetation placement are authored, not site reconstruction. Pedestrians remain proxies. No Jev inference, vehicle dynamics or real-vehicle interface is used.

Historical source acquisition is retained in this directory for provenance only. The original PR #11 runs remain the evidence of those downloads and Blender/runtime checks; new integrated work should use the PR #9/#10 canonical asset pipeline unless this experiment specifically needs its locked Urban District package.
