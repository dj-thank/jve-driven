"""Rebuild a verified snapshot without fetching; CI supplies an empty network namespace."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from jevdrive.publicworld.audit import audit_snapshot
from jevdrive.publicworld.pipeline import build_snapshot


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('snapshot', type=Path)
    args = parser.parse_args()
    before = audit_snapshot(args.snapshot)
    build_snapshot(args.snapshot)
    after = audit_snapshot(args.snapshot)
    fields = ('glb_sha256', 'glb_bytes', 'triangles', 'textured_triangles', 'bounds_gltf_y_up_m', 'source_lock_sha256')
    checks = {name: before[name] == after[name] for name in fields}
    report = {
        'schema': 'jevdrive.offline-rebuild.v1',
        'same_environment_repeat': True,
        'cross_version_byte_identity_claimed': False,
        'network_isolation': 'caller_responsibility; CI uses sudo unshare --net',
        'checks': checks, 'passed': all(checks.values()),
        'glb_sha256': after['glb_sha256'],
        'source_lock_sha256': after['source_lock_sha256'],
        'live_jev_calls': 0, 'driveable': False,
    }
    (args.snapshot / 'offline-rebuild.json').write_text(json.dumps(report, indent=2), encoding='utf8')
    print(json.dumps(report, indent=2))
    return 0 if report['passed'] else 2


if __name__ == '__main__':
    raise SystemExit(main())
