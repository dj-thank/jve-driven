"""Record and audit bounded Jev or baseline execution, not a photoreal city demo.

The networked modes use the official endpoint only. A missing key, failed API,
shadow-only use, or stationary vehicle is never labelled live API-driven motion.
"""
from __future__ import annotations
import argparse
import getpass
import hashlib
import json
import os
import platform
import sys
from datetime import datetime, timezone
from pathlib import Path
from jevdrive.decision_audit import audit_control_trace
from jevdrive.simulation import simulate, write_run, SCENARIOS
from jevdrive.world import parse_osm


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--mode', choices=['baseline','jev-shadow','jev-live'], default='baseline')
    p.add_argument('--scenario', choices=SCENARIOS, default='pedestrian')
    p.add_argument('--seconds', type=int, default=12, choices=range(1,61))
    p.add_argument('--max-calls', type=int, default=24, choices=range(1,121))
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--osm', type=Path, default=Path('data/raw/kirchberg_subset.osm'))
    a=p.parse_args()
    if a.out.exists():
        p.error('Output exists; choose a new evidence directory')
    a.out.mkdir(parents=True)
    summary={'schema':'jevdrive.recorded-execution.v1',
        'started_utc':datetime.now(timezone.utc).isoformat(),
        'mode':a.mode,'completed':False,'live_control_evidence_present':False,
        'python':platform.python_version(),'commit':os.environ.get('GITHUB_SHA'),
        'camera_perception_evaluated':False,'tokyo_public_world_driving':False}
    prior_key=os.environ.get('TYPESAFE_API_KEY'); key=prior_key or ''
    try:
        if a.mode != 'baseline' and not key:
            if not sys.stdin.isatty():
                raise RuntimeError('missing_typesafe_api_key')
            key=getpass.getpass('TypeSafe API key (not saved): ').strip()
            if not key: raise RuntimeError('missing_typesafe_api_key')
            os.environ['TYPESAFE_API_KEY']=key
        world=parse_osm(a.osm)
        result=simulate(world,scenario=a.scenario,mode=a.mode,duration=a.seconds,
                        realtime=a.mode!='baseline',max_calls=a.max_calls)
        audit=audit_control_trace(result)
        # Reject an accidental credential echo in any payload before disk output.
        encoded=json.dumps(result,ensure_ascii=False,allow_nan=False)
        if key and key in encoded: raise RuntimeError('credential_echo_rejected')
        write_run(result,a.out/'run.json')
        (a.out/'decision-audit.json').write_text(json.dumps(audit,indent=2),encoding='utf8')
        summary.update(completed=True,decision_audit=audit,
            live_control_evidence_present=audit['live_control_evidence_present'],
            run_sha256=hashlib.sha256((a.out/'run.json').read_bytes()).hexdigest(),
            source_osm_sha256=world['input_sha256'])
        if a.mode=='baseline': code=0
        elif a.mode=='jev-shadow': code=0 if audit['validated_responses']>0 and audit['fixture_response_records']==0 else 3
        else: code=0 if audit['live_control_evidence_present'] else 3
    except Exception as exc:
        # No raw network exception, headers, key, or environment values in logs.
        summary.update(error_type=type(exc).__name__,error='execution_or_evidence_validation_failed')
        code=2
    finally:
        if prior_key is None: os.environ.pop('TYPESAFE_API_KEY',None)
        else: os.environ['TYPESAFE_API_KEY']=prior_key
        key=''
    summary['exit_code']=code
    summary['finished_utc']=datetime.now(timezone.utc).isoformat()
    (a.out/'execution.json').write_text(json.dumps(summary,indent=2),encoding='utf8')
    print(json.dumps(summary,indent=2))
    return code


if __name__=='__main__':raise SystemExit(main())
