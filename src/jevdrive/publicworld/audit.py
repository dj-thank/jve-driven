"""Machine-readable visual fidelity evidence; never certifies a driving map."""
from __future__ import annotations
import json
import math
from pathlib import Path
import numpy as np
import trimesh
from .download import sha256
from .integrity import verify_sources


def audit_snapshot(root: Path) -> dict:
    root = Path(root)
    meta = json.loads((root / 'public-world.json').read_text(encoding='utf8'))
    count = verify_sources(root, meta)
    if meta.get('stage') != 'built':
        raise ValueError('Audit requires a completely built snapshot')
    data = (root / 'visual-world.glb').read_bytes()
    if sha256(data) != meta['build']['sha256'] or len(data) != meta['build']['bytes']:
        raise ValueError('Built GLB hash or size changed')
    scene = trimesh.load_scene(root / 'visual-world.glb', process=False)
    if not scene.geometry or not np.isfinite(scene.bounds).all():
        raise ValueError('Empty or non-finite scene')
    triangles = textured = 0
    geometry_decoders = {}
    for mesh in scene.geometry.values():
        if not isinstance(mesh, trimesh.Trimesh) or not np.isfinite(mesh.vertices).all():
            raise ValueError('Non-triangle or non-finite geometry')
        triangles += len(mesh.faces)
        decoder = mesh.metadata.get("geometry_decoder")
        if decoder:
            geometry_decoders[decoder["input_sha256"]] = decoder
        if mesh.visual.kind == 'texture' and mesh.visual.uv is not None:
            if not np.isfinite(mesh.visual.uv).all():
                raise ValueError('Non-finite texture coordinates')
            material = mesh.visual.material
            image = getattr(material, 'baseColorTexture', None)
            if image is None:
                image = getattr(material, 'image', None)
            if image is not None:
                textured += len(mesh.faces)
    if not triangles or not textured:
        raise ValueError('Visual world has no textured triangles')
    latitude = meta['config']['origin']['latitude']
    zoom = meta['config']['imagery_zoom']
    gsd = math.cos(math.radians(latitude)) * 2 * math.pi * 6378137 / (256 * 2**zoom)
    report = {
        'schema': 'jevdrive.visual-audit.v1',
        'name': meta['name'], 'source_resources_verified': count,
        'source_lock_sha256': sha256((root / 'source-lock.json').read_bytes()),
        'glb_sha256': sha256(data), 'glb_bytes': len(data),
        'geometry_count': len(scene.geometry), 'triangles': triangles,
        'textured_triangles': textured,
        'textured_triangle_fraction': textured / triangles,
        'bounds_gltf_y_up_m': scene.bounds.tolist(),
        'ortho_nominal_pixel_spacing_m': gsd,
        'pixel_spacing_is_not_survey_accuracy': True,
        'road_centerlines': meta.get('road_way_count', 0),
        'appearance': meta['appearance'],
        'geometry_decoders': list(geometry_decoders.values()),
        'capture_dates_verified': False, 'geometric_accuracy_verified': False,
        'street_level_photorealism_verified': False, 'driveable': False,
        'license_review': meta.get('license_review'),
        'attribution': meta['attribution'],
        'checksums_are_not_authenticity_proof': True,
    }
    (root / 'visual-audit.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf8')
    return report
