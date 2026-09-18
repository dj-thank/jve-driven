"""Seal source selection and transformations, not only downloaded bytes.

Checksums detect accidental changes; these are not publisher signatures. A
malicious author who can replace the lock can reseal it. Review source URLs,
licenses, and survey control points independently.
"""
from __future__ import annotations
import json
from pathlib import Path
from .download import sha256, verify_lock

SOURCE_FIELDS = (
    'schema', 'name', 'config', 'frame', 'appearance', 'surface_role',
    'building_tiles', 'terrain_tiles', 'imagery_tiles', 'roads_source_sha256',
    'road_way_count', 'attribution', 'terrain_source_attribution',
)


def canonical(value) -> bytes:
    return json.dumps(value, sort_keys=True, separators=(',', ':'),
                      ensure_ascii=False, allow_nan=False).encode('utf8')


def selection(meta):
    return {key: meta[key] for key in SOURCE_FIELDS if key in meta}


def seal_sources(root: Path, meta: dict) -> dict:
    root = Path(root)
    seal = {
        'schema': 'jevdrive.source-lock.v1',
        'selection_sha256': sha256(canonical(selection(meta))),
        'download_lock_sha256': sha256((root / 'download-lock.json').read_bytes()),
        'derived': {},
        'authenticity': 'checksum_only_not_a_publisher_signature',
    }
    roads = root / 'roads-centerlines.geojson'
    if roads.exists():
        seal['derived'][roads.name] = sha256(roads.read_bytes())
    (root / 'source-lock.json').write_bytes(canonical(seal) + b'\n')
    return seal


def verify_sources(root: Path, meta: dict | None = None) -> int:
    root = Path(root).resolve()
    count = verify_lock(root)
    if meta is None:
        meta = json.loads((root / 'public-world.json').read_text(encoding='utf8'))
    seal = json.loads((root / 'source-lock.json').read_text(encoding='utf8'))
    if seal.get('schema') != 'jevdrive.source-lock.v1':
        raise ValueError('Unsupported source lock')
    if seal['selection_sha256'] != sha256(canonical(selection(meta))):
        raise ValueError('Source selection, coordinate transform or config changed')
    if seal['download_lock_sha256'] != sha256((root / 'download-lock.json').read_bytes()):
        raise ValueError('Download lock changed after source selection was sealed')
    for relative, expected in seal['derived'].items():
        path = (root / relative).resolve()
        if not path.is_relative_to(root):
            raise ValueError('Derived path outside snapshot')
        if not path.is_file() or sha256(path.read_bytes()) != expected:
            raise ValueError('Derived source file changed: ' + relative)
    return count
