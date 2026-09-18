"""Prepare real public geometry and a camera path; keep base source locks unchanged."""
from __future__ import annotations
import argparse, json
from pathlib import Path
import numpy as np
import trimesh
from jevdrive.publicworld.pipeline import fetch_snapshot, build_snapshot, read_config
from jevdrive.publicworld.integrity import verify_sources, canonical
from jevdrive.publicworld.download import DownloadStore, sha256
from jevdrive.publicworld.tiles3d import collect_buildings, load_geometry, matrix
from jevdrive.publicworld.geo import GLTF_TO_ZUP, ENU_TO_GLTF
from jevdrive.egoview import CameraSpec, select_camera_path


def prepare(config, out, spec=CameraSpec()):
    out = Path(out)
    if out.exists() and any(out.iterdir()):
        raise ValueError('Output must be empty; do not overwrite an earlier capture')
    out.mkdir(parents=True, exist_ok=True)
    cfg, area, frame = read_config(config)
    base = out/'source'
    meta = fetch_snapshot(config, base)
    build_snapshot(base); verify_sources(base)
    source = trimesh.load_scene(base/'visual-world.glb', process=False)
    source.apply_transform(GLTF_TO_ZUP)
    scene = trimesh.Scene()
    terrain = []; surfaces = []
    for node in source.graph.nodes_geometry:
        transform, name = source.graph[node]; mesh = source.geometry[name].copy()
        mesh.apply_transform(transform)
        scene.add_geometry(mesh, node_name=name, geom_name=name)
        if name.startswith('public_terrain'):
            terrain.extend(mesh.triangles)
    report = {'base_source_lock_sha256': sha256((base/'source-lock.json').read_bytes()), 'layers': {},
              'dataset_year': 2025, 'source_data_unchanged': True, 'synthetic_geometry_added': False}
    for role in ('tran', 'frn', 'veg'):
        root = out/'layers'/role
        store = DownloadStore(root, max_bytes=80_000_000, max_files=100)
        url = f'https://api.plateauview.mlit.go.jp/datacatalog/3dtiles/13101-{role}-lod3-2025/tileset.json'
        evidence = {'url': url, 'status': 'not_acquired', 'mesh_count': 0}
        try:
            tiles = collect_buildings(store, url, frame, area)
            staged = []
            for i, tile in enumerate(tiles):
                part = load_geometry((root/tile['path']).read_bytes(), matrix(tile['transform_column_major']), frame, f'urban_{role}_{i}')
                staged.extend(part.geometry.items())
            for name, mesh in staged:
                mesh.metadata['public_layer_role'] = role
                scene.add_geometry(mesh, node_name=name, geom_name=name)
                if role == 'tran': surfaces.extend(mesh.triangles)
            evidence.update(status='acquired', mesh_count=len(staged), tiles=tiles)
        except Exception as exc:
            evidence.update(status='unavailable', error_type=type(exc).__name__, error=str(exc)[:500])
        finally:
            store.save(); store.close()
        evidence['download_lock_sha256'] = sha256((root/'download-lock.json').read_bytes())
        report['layers'][role] = evidence
        print(json.dumps({'layer': role, **{k:v for k,v in evidence.items() if k != 'tiles'}}, ensure_ascii=False), flush=True)
    if not terrain:
        raise ValueError('No actual terrain mesh')
    roads = json.loads((base/'roads-centerlines.geojson').read_text())
    capture = select_camera_path(roads, area, frame, np.array(terrain), spec,
                                 np.array(surfaces) if surfaces else None)
    scene.apply_transform(ENU_TO_GLTF)
    data = scene.export(file_type='glb'); (out/'ego-world.glb').write_bytes(data)
    capture.update(scene_sha256=sha256(data), scene_bytes=len(data), source_manifest=report,
                   coordinate_frame=frame.as_dict(), source_attribution=meta['attribution'],
                   image_credits='Public data: MLIT PLATEAU / Tokyo 2025; terrain: Mapterhorn / GSI; route: OpenStreetMap contributors. Processed by Jev Drive Lab.',
                   license_review='See docs/EGO_DATA_LICENSES.md. Derived renders only; no raw city assets distributed.')
    (out/'capture.json').write_bytes(canonical(capture)+b'\n')
    (out/'capture.sha256').write_text(sha256((out/'capture.json').read_bytes())+'\n')
    print(json.dumps({'prepared': True, 'scene_bytes': len(data), 'route_id': capture['route']['osm_way_id'],
                      'surface': capture['route']['surface_source'], 'frames': len(capture['route']['frames'])}), flush=True)
    return capture


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--config', type=Path, default=Path('configs/tokyo-smoke.json'))
    p.add_argument('--out', type=Path, required=True)
    a = p.parse_args(); prepare(a.config, a.out)
