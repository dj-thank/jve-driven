"""Build an offline replay viewer. No CDN, API key, or fake live model calls."""
from pathlib import Path
import json
import numpy as np
from jevdrive.world import build_scene

ROOT = Path(__file__).resolve().parents[1]
world = json.loads((ROOT/'world/world.json').read_text())
scene = build_scene(world)
triangles = []
for node in scene.graph.nodes_geometry:
    transform, name = scene.graph[node]
    mesh = scene.geometry[name]
    vertices = np.column_stack((mesh.vertices, np.ones(len(mesh.vertices)))) @ transform.T
    for ids, rgba in zip(mesh.faces, mesh.visual.face_colors):
        triangles.append([*[round(float(c), 3) for c in vertices[ids, :3].flatten()], *rgba[:3].tolist(), 0 if name=="assumed_flat_ground" else 1 if name.startswith("osm_road_surface") else 2])
runs = {p.stem: json.loads(p.read_text()) for p in sorted((ROOT/'reports').glob('*.json'))
        if p.stem in {'clear','red_light','pedestrian','obstacle','occlusion','disconnect','stale_reply','adversarial_fixture'}}
data = json.dumps({'world':world, 'triangles':triangles, 'runs':runs}, ensure_ascii=False, separators=(',',':')).replace('</','<\\/')
template = (ROOT/'web/template.html').read_text()
output = template.replace('/*BUNDLED_DATA*/{}', data)
(ROOT/'web/index.html').write_text(output)
print(f'Offline viewer: {len(output.encode()):,} bytes; {len(triangles)} triangles; {len(runs)} runs')
