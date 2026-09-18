# Jve Driven / Jev Drive Lab

公開地理データと TypeSafe Jev を用いる、**シミュレーション専用**の自動運転研究基盤。

## Repository bootstrap — 2026-09-18

This repository is being initialized from the conversation's v0.2 public-data workbench. The initial README does not assert that a city has been reconstructed or driven. Source, tests and reproducible workflows are introduced through a follow-up pull request.

- Real-world geometry and textures must retain provenance and dataset-specific attribution.
- Visual meshes are not automatically drivable HD maps.
- Offline fixtures, live data downloads, live Jev inference, and engine execution must be reported separately.
- API credentials must never be committed or embedded in browser code.
- No real-vehicle control is supported.
