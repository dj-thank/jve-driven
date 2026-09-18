from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys


def main() -> None:
    parser=argparse.ArgumentParser(prog='jevdrive',description='Simulation-only TypeSafe Jev research workbench')
    sub=parser.add_subparsers(dest='command',required=True)
    build=sub.add_parser('build-world',help='Convert an OSM file to a metric scene and GLB')
    build.add_argument('--osm',type=Path,default=Path('data/raw/kirchberg_subset.osm'))
    build.add_argument('--out',type=Path,default=Path('world'))
    sim=sub.add_parser('simulate',help='CPU kinematic smoke run; NOT a CARLA benchmark')
    sim.add_argument('--world',type=Path,default=Path('world/world.json'))
    sim.add_argument('--scenario',default='pedestrian')
    sim.add_argument('--mode',choices=['baseline','jev-live','jev-shadow'],default='baseline')
    sim.add_argument('--realtime',action='store_true')
    sim.add_argument('--seconds',type=float,default=40)
    sim.add_argument('--max-calls',type=int,default=120)
    sim.add_argument('--out',type=Path,default=Path('runs/latest.json'))
    args=parser.parse_args()
    try:
        if args.command=='build-world':
            from .world import export_world
            result=export_world(args.osm,args.out)
        else:
            from .simulation import simulate,write_run
            world=json.loads(args.world.read_text(encoding='utf-8'))
            run=simulate(world,args.scenario,args.mode,args.seconds,realtime=args.realtime,max_calls=args.max_calls)
            write_run(run,args.out)
            result={'output':str(args.out),'mode':run['mode'],'jev_calls':run['jev_calls'],'metrics':run['metrics']}
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (ValueError,RuntimeError,OSError) as exc:
        print(f'ERROR: {exc}',file=sys.stderr)
        raise SystemExit(2) from exc

if __name__=='__main__': main()
