"""Do not automatically bundle detailed application records into public replays."""
import json
from pathlib import Path
import runpy
import shutil
from jevdrive.world import parse_osm

ROOT=Path(__file__).resolve().parents[1]


def test_replay_strips_large_trace_but_keeps_original_run(tmp_path):
    for name in ('tools','world','web','reports'):(tmp_path/name).mkdir()
    shutil.copyfile(ROOT/'tools/build_viewer.py',tmp_path/'tools/build_viewer.py')
    world=parse_osm(ROOT/'data/raw/kirchberg_subset.osm')
    (tmp_path/'world/world.json').write_text(json.dumps(world),encoding='utf8')
    original={'mode':'baseline','frames':[],'steps':[{'internal':'detailed-control'}],
              'jev_evidence':[{'internal':'application-request'}]}
    (tmp_path/'reports/clear.json').write_text(json.dumps(original),encoding='utf8')
    (tmp_path/'web/template.html').write_text('/*BUNDLED_DATA*/{}',encoding='utf8')
    runpy.run_path(str(tmp_path/'tools/build_viewer.py'))
    output=json.loads((tmp_path/'web/index.html').read_text(encoding='utf8'))
    assert output['runs']['clear']=={'mode':'baseline','frames':[]}
    assert json.loads((tmp_path/'reports/clear.json').read_text(encoding='utf8'))==original


def test_live_workflow_is_manual_main_only_and_has_no_default_secret_exposure():
    source=(ROOT/'.github/workflows/jev-live.yml').read_text(encoding='utf8')
    assert 'workflow_dispatch:' in source and '\n  push:' not in source and '\n  pull_request:' not in source
    assert "if: github.ref == 'refs/heads/main'" in source
    assert source.count('secrets.TYPESAFE_API_KEY')==2
    assert 'persist-credentials: false' in source
    assert source.index('secrets.TYPESAFE_API_KEY')>source.index('pip install')
