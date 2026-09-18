"""Fetch real LOD3 road/furniture/vegetation tiles without inventing features."""
from __future__ import annotations
import argparse, hashlib, json
from pathlib import Path
import trimesh
from jevdrive.publicworld.download import DownloadStore, verify_lock
from jevdrive.publicworld.geo import Area, Frame, ENU_TO_GLTF
from jevdrive.publicworld.tiles3d import collect_buildings, load_geometry, matrix

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--snapshot',type=Path,required=True)
p.add_argument('--catalog',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
a=p.parse_args()
if a.out.exists(): raise FileExistsError('Choose a new detail snapshot')
a.out.mkdir(parents=True)
meta=json.loads((a.snapshot/'public-world.json').read_text(encoding='utf8'))
cat=json.loads(a.catalog.read_text(encoding='utf8'))
frame=Frame(**meta['config']['origin']); area=Area(*meta['config']['bounds_wgs84'])
selected=[x for x in cat['datasets'] if str(x.get('ward_code') or x.get('city_code'))=='13101'
          and x.get('type_en') in {'tran','frn','veg'} and str(x.get('lod'))=='3'
          and x.get('texture') is True and x.get('year')==2025]
if not selected: raise ValueError('No catalog-resolved LOD3 detail datasets')
store=DownloadStore(a.out,max_bytes=350_000_000,max_files=500)
scene=trimesh.Scene(); layers=[]
try:
    for i,item in enumerate(selected):
        kind=item['type_en']; print('FETCH',kind,item['name'],flush=True)
        try:
            records=collect_buildings(store,item['url'],frame,area)
        except RuntimeError as exc:
            if 'No building tiles intersect' not in str(exc): raise
            layers.append({'type':kind,'name':item['name'],'url':item['url'],
                           'status':'no_coverage_in_aoi','tiles':[]})
            continue
        triangles=0
        for j,r in enumerate(records):
            part=load_geometry((a.out/r['path']).read_bytes(),matrix(r['transform_column_major']),
                               frame,f'detail_{kind}_{i}_{j}')
            for name,mesh in part.geometry.items():
                scene.add_geometry(mesh,node_name=name,geom_name=name); triangles+=len(mesh.faces)
        layers.append({'type':kind,'name':item['name'],'url':item['url'],'year':item['year'],
                       'status':'decoded','tiles':records,'triangles':triangles})
        print('DECODED',kind,len(records),'tiles',triangles,'triangles',flush=True)
    if not scene.geometry: raise ValueError('No actual LOD3 features in the target area')
    scene.apply_transform(ENU_TO_GLTF); data=scene.export(file_type='glb')
    (a.out/'details.glb').write_bytes(data)
    store.save(); verify_lock(a.out)
    report={'schema':'jevdrive.public-details.v1','frame':meta['config']['origin'],
        'source_catalog_sha256':hashlib.sha256(a.catalog.read_bytes()).hexdigest(),
        'download_lock_sha256':hashlib.sha256((a.out/'download-lock.json').read_bytes()).hexdigest(),
        'glb_sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'layers':layers,
        'geometry_count':len(scene.geometry),'triangles':sum(len(m.faces) for m in scene.geometry.values()),
        'driveable':False,'geometric_accuracy_verified':False,'attribution':meta['attribution']}
    (a.out/'details-manifest.json').write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf8')
    print('COMPLETE',len(data),'bytes',report['triangles'],'triangles',flush=True)
finally:
    store.save(); store.close()
