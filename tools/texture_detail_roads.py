"""Reproject source orthophotos only onto untextured real LOD3 road geometry."""
import argparse, hashlib, json
from pathlib import Path
import numpy as np
from PIL import Image
from pyproj import Transformer
import trimesh
from jevdrive.publicworld.geo import Frame, GLTF_TO_ZUP, xyz_pixel
from jevdrive.visual_quality import load_detail_road_sampler

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--snapshot',type=Path,required=True)
p.add_argument('--details',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
if a.out.exists(): raise FileExistsError('Choose a new appearance derivative')
m=json.loads((a.snapshot/'public-world.json').read_text(encoding='utf8'))
_,dm=load_detail_road_sampler(a.details,m['config']['origin'])
frame=Frame(**m['config']['origin']); to_ecef=np.linalg.inv(frame.ecef_to_enu)
transformer=Transformer.from_crs(4978,4979,always_xy=True)
imgs=m['imagery_tiles']; minx=min(r['x'] for r in imgs); miny=min(r['y'] for r in imgs)
image=Image.open(a.snapshot/'orthophoto-mosaic.jpg').convert('RGB'); w,h=image.size
scene=trimesh.load_scene(a.details/'details.glb',process=False); mapped=[]
material=trimesh.visual.material.PBRMaterial(name='SourceOrtho_Reprojected_RoughnessAssumed',
    baseColorTexture=image, metallicFactor=0.0,roughnessFactor=0.9,doubleSided=False)
for node in scene.graph.nodes_geometry:
    transform,name=scene.graph[node]
    if not str(node).startswith('detail_tran_'): continue
    mesh=scene.geometry[name]
    old=getattr(mesh.visual,'material',None)
    if getattr(old,'baseColorTexture',None) is not None: continue
    hom=np.column_stack((mesh.vertices,np.ones(len(mesh.vertices))))
    ecef=hom @ (to_ecef @ GLTF_TO_ZUP @ transform).T
    lon,lat,_=transformer.transform(ecef[:,0],ecef[:,1],ecef[:,2])
    px,py=xyz_pixel(lon,lat,imgs[0]['z'])
    uv=np.column_stack(((px-minx*256)/w,1-(py-miny*256)/h))
    # Omit outside-mosaic triangles rather than clamp/duplicate an unrelated image.
    covered=np.all((uv>=0)&(uv<=1),axis=1)
    mask=covered[mesh.faces].all(1)
    if not mask.any(): continue
    derived=mesh.copy(); derived.update_faces(mask); derived.remove_unreferenced_vertices()
    # Recompute UV for retained vertices using a temporary old-index mapping.
    ids=np.unique(mesh.faces[mask]); derived.visual=trimesh.visual.TextureVisuals(uv=uv[ids],material=material)
    derived.metadata.update(appearance='source_ortho_reprojection',roughness_assumed=0.9)
    scene.geometry[name]=derived
    mapped.append({'mesh':name,'original_triangles':len(mesh.faces),'kept_triangles':len(derived.faces)})
if not mapped: raise ValueError('No untextured roads covered by the actual orthophoto')
data=scene.export(file_type='glb'); a.out.mkdir(parents=True)
(a.out/'appearance.glb').write_bytes(data)
report={'schema':'jevdrive.road-appearance.v1','source_glb_sha256':m['build']['sha256'],
    'details_glb_sha256':dm['glb_sha256'],'glb_sha256':hashlib.sha256(data).hexdigest(),
    'ortho_sha256':hashlib.sha256((a.snapshot/'orthophoto-mosaic.jpg').read_bytes()).hexdigest(),
    'mapped':mapped,'road_geometry_changed':False,'outside_imagery_faces_omitted':True,
    'source_capture_epoch_alignment_verified':False,'roughness_assumed':0.9,'driveable':False}
(a.out/'appearance-manifest.json').write_text(json.dumps(report,indent=2),encoding='utf8')
print(json.dumps({'mapped_meshes':len(mapped),'bytes':len(data)},indent=2))
