# Integrated native capture and decision evidence

This work integrates the two independent PR heads `7b56c908ba94e708f6da604357eb41f0fb6e43f8` (#5) and `e1927ff136f262920a365de26e4b01fdc658c95c` (#6) in a separate worktree. Existing working files and previously generated snapshots are not overwritten.

## Separate evidence paths

- `decision_audit.py` checks recorded Jev requests, replies, application times and kinematic motion. It does not turn an unrelated camera-path movie into a Jev driving result.
- `blender_quality_render.py` imports locked real PLATEAU building/road/terrain data and optional attributed appearance assets. Its camera-path output explicitly reports zero Jev calls, no vehicle physics, and `driveable=false`.
- No real-vehicle interface or public-world driving acceptance gate is changed.

## Optional tree appearance

`prepare_visual_tree_layer.py` selects authored tree positions alongside the explicitly selected OSM road and queries the actual locked LOD3 road mesh for their base heights. Missing or ambiguous coverage is rejected. These positions are NOT surveyed tree locations, species, sizes, or traffic actors. Records have no invented OSM IDs and are locked to the camera plan and source GLB.

The native renderer accepts `--tree-layer` explicitly, verifies its identity, checks the tree bases independently with Blender ray casts, and instantiates a shared asset. `--source-only` refuses this layer. Without `--tree-layer`, previous behavior remains unchanged.

An optional `--tree-lod1-assets` pack loads Poly Haven's named native `tree_small_02_LOD1` object after validating every resource against its SHA-256 lock. Source UVs and texture images are retained. Authored tree height is 6.5 m, not a measurement. Native LOD1 reduces repeated geometry workload; it is not a claim of equal detail to LOD0.

## Actual media validation

Before packaging, every PNG is decoded/verified with its exact dimensions and a SHA-256 recorded. Missing, extra, corrupt or changed frames fail. The H.264 output is independently read with `ffprobe -count_frames`, frame rate/duration/dimensions are compared, and a full `ffmpeg -xerror` decode is required. Input frame hashes must remain unchanged after encoding.

Captions permanently distinguish source geography from optional paving/tree appearance and state that Jev and vehicle physics were not used. Font files are never copied into deliverables. A 30 fps MP4 is a playback rate, not a real-time rendering benchmark.

## Limitations

Native facade textures remain low-detail or incomplete near ground. Additional tree/paving assets do not establish photographic accuracy. Lighting, generic pavement and authored tree positions are not a measured reconstruction of present-day Marunouchi. Actual tree placement/source updates need licensed independent references. Jev inference remains a separate unexecuted task until a local key is configured without exposing it.

Assets: https://polyhaven.com/a/tree_small_02 and https://polyhaven.com/license. Source conditions: https://www.mlit.go.jp/plateau/site-policy/ . Existing source download/selection locks and render manifests remain authoritative for the exact inputs.
