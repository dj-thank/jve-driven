# PR #5–#11 integration map

This branch consolidates the September 18 rendering/asset work without changing the public-world driving refusal boundary or upgrading any visual result into a driving-performance claim.

## Canonical layering

1. **Ego/public-world + Jev evidence** — PR #5, integrated with the native-render work by PR #7 and retained through #8/#9.
   - `src/jevdrive/decision_audit.py`, `egoview.py`, Jev request/reply timing evidence, ego camera metadata and media validation.
2. **Native PLATEAU/LOD3 rendering + lookdev** — PR #6, integrated by #7, then hardened by #8.
   - LOD3 roads/city furniture/vegetation, source-ground carving, material audit, native Windows locale coverage.
3. **Reusable hero-asset library** — PR #9.
   - Hash-locked CC0 car/tree/bench/planter sources and reusable GLB/.blend export.
4. **Asset Studio** — PR #10.
   - Canonical external-asset preparation/review layer. It intentionally consumes the PR #9 hero-library artifact, adds reviewed Rocketbox people, native import checks and Cycles review.
5. **Authored-district playback experiment** — PR #11.
   - Kept under `experiments/urban-render/` as a playback/contract experiment. It is not the canonical acquisition pipeline and does not replace the PLATEAU/public-world path.

## Duplicate-workflow cleanup

PR #11 originally carried separate asset-intake, Blender-runtime, foliage-mask and surface-intake workflows. Their exact YAML blobs are preserved under:

`experiments/urban-render/workflows/historical/`

They are intentionally not active GitHub Actions in this integration branch. The active `urban-render-contract.yml` remains to test the experiment code. Canonical acquisition/preparation is the PR #9 -> PR #10 pipeline.

## Preserved execution evidence

- PR #5 offline-validation: run 35344144280 — success.
- PR #6 offline-validation: run 35357049391 — success. Native render release evidence documents the 300-frame/10s H.264 capture and source hashes.
- PR #7 offline-validation: run 35359644848 — success.
- PR #8 offline-validation: run 35363183330 — success; includes Japanese Windows encoding hardening.
- PR #9 final head `46ad223ff7d8ae0ccbb6e2913d37ebfb2ba0526d`:
  - offline-validation 35385731626 — success.
  - hero-library-export 35385727394 — success.
  - native review 35384651516 — success on the preceding render head; the final commit only decoupled library export.
- PR #10 final head `c709eb353d9b957ca291bdee91a50c4a6ca5663b`:
  - acquisition 35386939547 — success.
  - people 35388104419 — success.
  - native inspect 35389000107 — success.
  - native review 35389985374 — success.
  - final offline-validation 35390231162 — success. The final two commits add documentation/tests after the successful native-review head.
- PR #11 final head `c53bf0f6095c486ef109048eadda360818829af0`:
  - Urban render contracts 35392769149 — success.
  - offline-validation 35392769091 — success.
  - source/runtime acquisition runs 35388833358, 35389753082, 35390945103 and 35391159975 — success after the documented earlier surface-intake failures were corrected.

## Merge gates

Before merging this integration branch to `main`:

- run the repository offline-validation matrix on the integrated tree;
- run `urban-render-contract` on the integrated tree;
- confirm no public-world driving refusal gate or Jev evidence schema regressed;
- keep raw city/source assets, downloaded models, fonts, credentials and Blender binaries out of Git;
- treat authored materials, authored vegetation/people placement and the authored-district experiment as visual studies, not surveyed Tokyo truth or autonomous-driving validation.

The integration branch has the PR #9, PR #10 and PR #11 heads as commit parents, so their histories and original evidence remain reachable.
