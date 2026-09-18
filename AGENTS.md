# Development contract

This is a simulation-only research project. Never add a real-vehicle interface.

1. Read README.md and docs/ACCEPTANCE_BACKLOG.md before changing behavior.
2. Run the full test suite on the integrated tree, not an earlier commit. Preserve baseline behavior unless a semantic change has its own evidence.
3. Distinguish synthetic fixtures, real public-data downloads, live Jev inference, and Blender/CARLA/Unreal execution in every report. A unit test is not evidence of real-world accuracy.
4. Never commit API keys, .env files, raw provider responses containing sensitive data, generated city assets, or unreviewed third-party data. Keep attribution and dataset licenses distinct from the code license.
5. Public-world builds remain visual-only. Missing lane topology, signals, road collision surfaces or surveyed alignment must not be fabricated or marked verified.
6. Keep snapshot selection, tile transforms, downloads and derived sources hash-locked. Hashes detect changes, not publisher authenticity.
7. Authenticated Jev requests must use only the pinned official endpoint, with no redirects and no environment proxy configuration. No live calls in default CI.
8. Use `python -m pytest -q`, `python -m compileall -q src tools`, and `python tools/check_repository.py`. Record exact commands, commit and limitations.
9. New capabilities need success, failure and tampering regression tests. Do not weaken tests to make the workflow green.
10. Follow-up issues must contain concrete acceptance evidence and avoid unsupported completion claims.
