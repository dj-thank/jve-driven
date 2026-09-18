"""Remove coarse terrain ONLY inside the actual LOD3 road footprint."""
import argparse, hashlib, json
from pathlib import Path
import numpy as np
import trimesh
from shapely.geometry import Polygon
from shapely.ops import unary_union, triangulate
from jevdrive.visual_quality import load_detail_road_sampler
from jevdrive.publicworld.geo import GLTF_TO_ZUP, ENU_TO_GLTF

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--snapshot',type=Path,required=True)
p.add_argument('--details',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
if a.out.exists(): raise FileExistsError('Preserve existing derived terrain')
m=json.loads((a.snapshot/'public-world.json').read_text(encoding='utf8'))
sampler,dm=load_detail_road_sampler(a.details,m['config']['origin'])
footprint=unary_union([Polygon(t[:,:2]) for t in sampler.triangles])
print('ROAD_FOOTPRINT',footprint.area,flush=True)
source=trimesh.load_scene(a.snapshot/'visual-world.glb',process=False)
result=trimesh.Scene(); before=after=0
for node in source.graph.nodes_geometry:
    transform,name=source.graph[node]
    if not str(node).startswith('public_terrain_'): continue
    mesh=source.geometry[name].copy(); mesh.apply_transform(GLTF_TO_ZUP @ transform)
    vertices=[]; faces=[]; uv=[]
    for face in mesh.faces:
        t=mesh.vertices[face]; poly=Polygon(t[:,:2]); before+=poly.area
        remainder=poly.difference(footprint)
        if remainder.is_empty: continue
        parts=[remainder] if isinstance(remainder,Polygon) else list(remainder.geoms)
        basis=np.column_stack((t[1,:2]-t[0,:2],t[2,:2]-t[0,:2]))
        if abs(np.linalg.det(basis))<1e-12: continue
        inv=np.linalg.inv(basis)
        for part in parts:
            if not isinstance(part,Polygon): continue
            for tri in triangulate(part):
                if not part.covers(tri): continue
                xy=np.asarray(tri.exterior.coords)[:3]
                weights=(xy-t[0,:2]) @ inv.T
                z=t[0,2]+weights[:,0]*(t[1,2]-t[0,2])+weights[:,1]*(t[2,2]-t[0,2])
                tex=mesh.visual.uv[face]
                newuv=tex[0]+weights[:,0,None]*(tex[1]-tex[0])+weights[:,1,None]*(tex[2]-tex[0])
                k=len(vertices); vertices.extend(np.column_stack((xy,z))); uv.extend(newuv)
                faces.append([k,k+1,k+2]); after+=tri.area
    if faces:
        clipped=trimesh.Trimesh(vertices=vertices,faces=faces,process=False,
            visual=trimesh.visual.TextureVisuals(uv=np.asarray(uv),material=mesh.visual.material))
        result.add_geometry(clipped,geom_name='quality_ground_'+str(node),node_name='quality_ground_'+str(node))
if not result.geometry: raise ValueError('Derived terrain empty')
result.apply_transform(ENU_TO_GLTF); data=result.export(file_type='glb')
a.out.mkdir(parents=True); (a.out/'ground.glb').write_bytes(data)
report={'schema':'jevdrive.road-cutout.v1','source_glb_sha256':m['build']['sha256'],
    'details_glb_sha256':dm['glb_sha256'],'glb_sha256':hashlib.sha256(data).hexdigest(),
    'before_area_m2':before,'after_area_m2':after,'removed_area_m2':before-after,
    'method':'exact projected road-triangle union; original terrain plane and UV interpolation',
    'height_offsets_added':False,'driveable':False}
(a.out/'ground-manifest.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps(report,indent=2))
