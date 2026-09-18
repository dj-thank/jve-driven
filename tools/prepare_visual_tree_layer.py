"""Prepare a bounded optional appearance layer on real LOD3 surface heights."""
import argparse, hashlib, json
from pathlib import Path
from shapely.geometry import LineString
import numpy as np
from jevdrive.publicworld.geo import Frame
from jevdrive.publicworld.integrity import verify_sources
from jevdrive.visual_quality import load_detail_road_sampler
from jevdrive.visual_enrichment import authored_tree_layer, validate_tree_layer


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--snapshot',type=Path,required=True)
    p.add_argument('--details',type=Path,required=True)
    p.add_argument('--plan',type=Path,required=True)
    p.add_argument('--out',type=Path,required=True)
    a=p.parse_args()
    if a.out.exists(): raise FileExistsError('Keep previous authored layers')
    verify_sources(a.snapshot)
    meta=json.loads((a.snapshot/'public-world.json').read_text(encoding='utf8'))
    plan=json.loads(a.plan.read_text(encoding='utf8'))
    if plan['source_glb_sha256']!=meta['build']['sha256']:
        raise ValueError('Source and plan mismatch')
    roads=json.loads((a.snapshot/'roads-centerlines.geojson').read_text(encoding='utf8'))
    road=next(f for f in roads['features'] if str(f['id'])==plan['osm_way_id'])
    frame=Frame(**meta['config']['origin'])
    ll=np.asarray(road['geometry']['coordinates'])
    xy=frame.points(ll[:,0],ll[:,1],np.zeros(len(ll)))[:,:2]
    route=LineString(xy[::-1] if plan['osm_tags'].get('oneway')=='-1' else xy)
    surface,details=load_detail_road_sampler(a.details,meta['config']['origin'])
    if plan.get('details_glb_sha256')!=details['glb_sha256']:
        raise ValueError('Road surface differs from the camera plan')
    digest=hashlib.sha256(a.plan.read_bytes()).hexdigest()
    layer=authored_tree_layer(plan,route,surface.height,plan_sha256=digest)
    validate_tree_layer(layer,plan,digest)
    layer['details_glb_sha256']=details['glb_sha256']
    a.out.parent.mkdir(parents=True,exist_ok=True)
    a.out.write_text(json.dumps(layer,indent=2),encoding='utf8')
    print(json.dumps({'trees':len(layer['trees']),'rejected':len(layer['rejected']),
        'placement_source':layer['placement_source'],'path':str(a.out)}))


if __name__=='__main__': main()
