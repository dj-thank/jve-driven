from __future__ import annotations
import argparse,json,sys
from pathlib import Path
from .pipeline import fetch_snapshot,build_snapshot,require_driveable
from .integrity import verify_sources
from .audit import audit_snapshot


def main():
    p=argparse.ArgumentParser(description='Public-data visual worlds. Not a certified autonomous-driving environment.')
    sub=p.add_subparsers(dest='command',required=True)
    f=sub.add_parser('fetch');f.add_argument('--config',type=Path,default=Path('configs/tokyo-marunouchi.json'));f.add_argument('--out',type=Path,required=True);f.add_argument('--resume',action='store_true')
    for command in ('build','verify','audit','check-driving'):
        s=sub.add_parser(command);s.add_argument('snapshot',type=Path)
    a=p.parse_args()
    try:
        if a.command=='fetch': result=fetch_snapshot(a.config,a.out,resume=a.resume)
        elif a.command=='build': result=build_snapshot(a.snapshot)
        elif a.command=='verify': result={'verified_resources':verify_sources(a.snapshot)}
        elif a.command=='audit': result=audit_snapshot(a.snapshot)
        else:
            require_driveable(json.loads((a.snapshot/'public-world.json').read_text()));result={}
        print(json.dumps(result,indent=2,ensure_ascii=False))
    except Exception as e:
        print(f'ERROR ({type(e).__name__}): {e}',file=sys.stderr);return 2
    return 0

if __name__=='__main__': raise SystemExit(main())
