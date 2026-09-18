# Native look development and material-reference regression

This change is stacked on PR #7, commit `33456eaf646d2f2a1acca4d98ea3109896219379`, which integrates #5 and #6. Other worktrees, existing videos and raw source snapshots are not modified. No real-vehicle interface, Jev request or driving-acceptance gate is added.

## Correct imported-material reference

`--source-only` now preserves the imported building and road shader values and connections. The previous renderer also rewrote metallic values and roughness in this mode. Before/after native material snapshots are written to `material-audit.json`; a changed source-only snapshot aborts. Input derivatives may already have orthophoto remapping, so this is an **imported-material reference**, not original unprocessed survey radiometry.

Enhanced modes log old/new metallic and roughness values, preserve linked inputs and configure shared materials once. Paving albedo replacement is no longer labelled as preserving the source colour. Still-frame selection rejects invalid clocks and removes duplicates.

## Explicit appearance supplement

Use `--look-preset neutral-daylight` to select the bounded light/exposure preset and route-aligned metric paving UVs. Legacy settings remain the default. These are art-direction choices, not measured local weather or pavement calibration. Existing facade images are not upscaled or replaced with invented detail.

`--tree-grates` requires `--tree-layer` and refuses source-only mode. It adds small procedural cast-iron grids and soil around the **authored** tree placements. Every corner is sampled from the actual imported road; missing road coverage aborts. A 0.038 m decorative offset is explicitly recorded. Original street meshes are unchanged. Grates are visual dressing, not surveyed infrastructure or physics actors. The trunk opening, geometry dimensions and UV handedness have regression tests.

Renderer and helper hashes are captured before work and compared after capture. Editing either file during a render invalidates the result. Render reports record all input identities and a hash of the material audit. The video packager verifies and copies the audit and keeps permanent no-Jev/no-driving and authored-appearance captions.

## Japanese Windows regression

On the actual Windows PC with its native cp932 locale, the integrated base failed 10 of 301 tests. JSON/HTML file operations implicitly used the locale encoding. The fix explicitly specifies UTF-8 at file boundaries; no geographic data or assertions are changed. CI adds a Windows pass with `PYTHONUTF8=0`, and a regression test rejects future implicit `Path.read_text/write_text` calls in source/tools/tests.

## Limits

A native camera animation is not vehicle motion or closed-loop driving. Tree positions, shape, root grates, pavement appearance and lighting remain supplements. Imported LOD2 facade textures are visibly coarse; sample-count increases cannot recover missing street-level measurements. A 30 fps export is not a real-time rendering claim. No API key or system font is distributed.
