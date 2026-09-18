"""Bounded real-data acquisition, build and audit; preserves failure evidence.

Does not call Jev, request secrets, install an engine or upload licensed assets.
"""
from __future__ import annotations
import argparse
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from jevdrive.publicworld.pipeline import fetch_snapshot, build_snapshot
from jevdrive.publicworld.audit import audit_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', type=Path, default=Path('configs/tokyo-smoke.json'))
    parser.add_argument('--out', type=Path, default=Path('runs/public-smoke'))
    parser.add_argument('--resume', action='store_true')
    args = parser.parse_args()
    # Reuse is explicit; never overwrite a built scene or a different selection.
    report = {
        'schema': 'jevdrive.live-check.v1',
        'started_utc': datetime.now(timezone.utc).isoformat(),
        'commit': os.environ.get('GITHUB_SHA'), 'python': platform.python_version(),
        'mode': 'live_public_data_not_fixture', 'completed': False,
        'live_jev_calls': 0, 'blender_executed': False, 'unreal_executed': False,
        'geometric_accuracy_verified': False, 'driveable': False,
    }
    try:
        report['stage'] = 'fetch'
        meta = fetch_snapshot(args.config, args.out, resume=args.resume)
        report['download_resources'] = meta['download_resources']
        report['download_bytes'] = meta['download_bytes']
        report['stage'] = 'build'
        report['build'] = build_snapshot(args.out)
        report['stage'] = 'audit'
        report['audit'] = audit_snapshot(args.out)
        report.update(stage='complete', completed=True)
        code = 0
    except Exception as exc:
        # Only public URLs and sanitized error classes: no environment/headers.
        report.update(error_type=type(exc).__name__, error=str(exc)[:1500])
        code = 2
    report['finished_utc'] = datetime.now(timezone.utc).isoformat()
    report_path = args.out.parent / (args.out.name + '-live-check.json')
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf8')
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return code


if __name__ == '__main__':
    raise SystemExit(main())
