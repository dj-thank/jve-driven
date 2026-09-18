"""Create a covered, source-locked car-height inspection plan."""
import argparse, json
from pathlib import Path
from jevdrive.visual_quality import build_plan, verify_asset_pack, apply_detail_surface

p=argparse.ArgumentParser(description=__doc__)
p.add_argument('--snapshot',type=Path,required=True)
p.add_argument('--assets',type=Path,required=True)
p.add_argument('--out',type=Path,required=True)
p.add_argument('--osm-id',default='1105290311')
p.add_argument('--details',type=Path)
a=p.parse_args()
if a.out.exists(): raise FileExistsError('Keep previous plans; choose a new output')
verify_asset_pack(a.assets)
plan=build_plan(a.snapshot,a.osm_id)
if a.details:
    meta=json.loads((a.snapshot/'public-world.json').read_text(encoding='utf8'))
    plan=apply_detail_surface(plan,a.details,meta['config']['origin'])
a.out.parent.mkdir(parents=True,exist_ok=True)
a.out.write_text(json.dumps(plan,indent=2,ensure_ascii=False),encoding='utf8')
print(json.dumps({'frames':len(plan['frames']),'osm_trees':len(plan['trees']),
    'start':plan['frames'][0]['xyz'],'end':plan['frames'][-1]['xyz'],
    'covered_frames':len(plan['frames']),'driveable':False},indent=2))
