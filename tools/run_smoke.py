"""Regenerate the 8 offline baseline / fault-injection smoke runs, never call Jev."""
from pathlib import Path
import json
from jevdrive.simulation import SCENARIOS, simulate, write_run
ROOT=Path(__file__).resolve().parents[1]
world=json.loads((ROOT/'world/world.json').read_text(encoding='utf-8'))
summary={}
for name in SCENARIOS:
    result=simulate(world,scenario=name,mode='baseline')
    write_run(result,ROOT/'reports'/f'{name}.json')
    summary[name]=result['metrics']
(ROOT/'reports/smoke_summary.json').write_text(json.dumps(summary,indent=2))
print('8 offline smoke runs completed. Actual Jev calls: 0.')
