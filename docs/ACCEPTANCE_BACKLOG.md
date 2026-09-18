# Acceptance backlog

All items below are open research/engineering gates, not claims of completion. Tests must run on the integrated commit. Keep fixtures, live sources, inference and engine execution distinguishable.

## P0 — Real public-data snapshot

Fetch the bounded Tokyo configuration, preserve resolved URLs, all hashes and source selection lock. Build a textured GLB and visual audit. Replay the build with networking disabled from the same snapshot. Compare scene bounds and texture coverage; do not equate byte-identical encoding across library versions with geometric identity. Record acquisition date and separately verified capture/survey dates. If a format is unsupported, add a minimal real-format regression fixture with permission, decoder and negative tests. No silent omission or invented replacement assets.

Acceptance: successful live report, offline rebuild, verified locks, nonempty textured geometry, attribution/licensing review and a documented coverage map. Keep geometric accuracy false until independent evidence exists.

## P0 — Street-level fidelity and coordinates

Choose a 100–300 m corridor with licensed ground photos or point clouds. Establish an independent georeferenced control set spanning origin, endpoints, buildings, ground and elevated structures. Report horizontal and vertical residuals, texture projection errors, capture epochs and uncertainty. Predetermine tolerances for the intended simulation use; do not tune acceptance thresholds after seeing results. LOD2 aerial textures alone do not establish driver-view photorealism.

Acceptance: matched viewpoints, measurements and residual report, clear source-vs-generated labels, no guessed facade represented as measured, a reproducible Blender or Unreal render.

## P0 — Drivable road graph

Acquire or author evidence-based lane boundaries, widths, junction connections, directions, stop lines and traffic controls for the same corridor. Preserve source IDs and distinguish unknown values. Fit an OpenDRIVE/Lanelet2 representation against the real road surface, not terrain under a bridge. Implement a separate verified collision mesh and stop at unsupported junctions.

Acceptance: topology tests, lane connectivity, crosswalk/stop-line checks, bridge/tunnel and collision sweeps, coordinate-control evidence and dedicated simulation integration. Do not remove the public-world driveability refusal until an actual adapter and these checks exist.

## P1 — Engine and sensor validation

Pin engine, plugins, map and vehicle/sensor configuration. Verify camera intrinsics/extrinsics, depth scale, LiDAR conventions and synchronization. Save fixed-seed replay and frame-time percentiles. Test cleanup on interruption and partial failure. Separate visual quality, physical fidelity and traffic correctness.

Acceptance: native scene/project, reproducible run command, screenshots plus machine-readable results, failure injection, and independent coordinate tests. A browser replay is not engine evidence.

## P1 — Jev shadow then closed-loop evaluation

Use a rotated local key, bounded requests and synthetic/nonpersonal state only. Record successful response count, model ID, sanitized error counts, latency p50/p95/p99, deadline expiry and total calls. Compare baseline, Jev-shadow and Jev-live on identical scenarios and unseen splits. Report progress as well as collision and rule violations; stopping forever is not success. Calibrate confidence-related thresholds on a separate split, since concentration is not correctness probability.

Acceptance: real API evidence, equal-budget baseline comparison, no secret leakage, auth failures permanently disable, stale/late responses cannot actuate, uncertainty intervals and negative controls. Include semantically ambiguous scenarios that cannot all be solved by the same trivial rule baseline.

## P1 — Perception and control

Replace simulator ground-truth observations through a versioned perception adapter while preserving the source label. Test occlusion, dynamic actors, night/rain and sensor dropout on a limited operational domain. Implement jerk-aware planning without weakening emergency stopping; explicitly model acceleration/actuator limits and time alignment.

Acceptance: source-disjoint evaluation, sensor replay, timing and failure tests, separate perception and planner metrics. Do not describe the current corridor heuristic as an end-to-end autonomous driving system.

## P2 — Reproducibility and distribution

Add platform-specific dependency locks with hashes, full workflow/engine artifact identity, minimal permitted real-data fixtures, and reproducibility checks. Investigate large-AOI chunking, tile seams and resource pressure. Review dataset-specific terms before publishing raw imagery or meshes. Never substitute code MIT licensing for source-data permissions.
