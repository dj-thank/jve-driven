"""Explicit, bounded geometry-only decode; no downloads or mesh simplification.

The original source bytes remain in the snapshot. Derived bytes, decoder script,
and exact dependency manifest/lock identities are included in build evidence.
"""
from __future__ import annotations
import hashlib
import os
from pathlib import Path
import shutil
import subprocess

GEOMETRY_EXTENSIONS = {'KHR_draco_mesh_compression', 'EXT_meshopt_compression'}
MAX_INPUT = 64_000_000
MAX_OUTPUT = 128_000_000


def decode_geometry(data: bytes, extensions: set[str]):
    if not extensions or not extensions <= GEOMETRY_EXTENSIONS:
        raise ValueError('Only Draco/meshopt geometry decoding is supported')
    if os.environ.get('JEVDRIVE_DECODE_GEOMETRY') != '1':
        raise RuntimeError('Compressed geometry requires explicit opt-in: install tools/gltf dependencies and set JEVDRIVE_DECODE_GEOMETRY=1; found ' + ', '.join(sorted(extensions)))
    if len(data) > MAX_INPUT:
        raise ValueError('Compressed GLB exceeds 64 MB decode limit')
    directory = Path(__file__).resolve().parents[3] / 'tools' / 'gltf'
    script = directory / 'decode.mjs'
    manifest = directory / 'package.json'
    node = shutil.which('node')
    if not node or not script.is_file() or not manifest.is_file():
        raise RuntimeError('Geometry decoder requires Node.js and the repository tools/gltf directory')
    # No auth tokens, NODE_OPTIONS, proxy settings or arbitrary shell commands.
    env = {k: os.environ[k] for k in ('PATH', 'SYSTEMROOT', 'WINDIR', 'TMP', 'TEMP') if k in os.environ}
    try:
        result = subprocess.run([str(Path(node).resolve()), '--max-old-space-size=512', str(script)],
                                input=data, capture_output=True, timeout=45, env=env, check=False)
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError('Geometry decoder exceeded 45-second deadline') from exc
    if result.returncode:
        raise RuntimeError('Geometry decoder failed; install the pinned tools/gltf dependencies (stderr withheld)')
    decoded = result.stdout
    if not 20 <= len(decoded) <= MAX_OUTPUT or decoded[:4] != b'glTF':
        raise ValueError('Geometry decoder returned invalid or oversized GLB')
    sha = lambda b: hashlib.sha256(b).hexdigest()
    lock = directory / 'package-lock.json'
    return decoded, {
        'name': 'gltf-transform-geometry-only', 'extensions': sorted(extensions),
        'input_sha256': sha(data), 'output_sha256': sha(decoded),
        'script_sha256': sha(script.read_bytes()),
        'dependency_manifest_sha256': sha(manifest.read_bytes()),
        'dependency_lock_sha256': sha(lock.read_bytes()) if lock.exists() else None,
        'simplified': False, 'textures_reencoded': False,
        'metadata_source': 'original locked tile; non-rendering extensions may not survive conversion',
    }
