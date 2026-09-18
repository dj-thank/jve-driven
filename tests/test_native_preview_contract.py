"""Negative controls for the preview labels; no native render is fabricated."""
import importlib.util, json, sys
from pathlib import Path
import pytest

MODULE=Path(__file__).resolve().parents[1]/'tools/package_native_preview.py'
spec=importlib.util.spec_from_file_location('native_preview',MODULE)
preview=importlib.util.module_from_spec(spec); spec.loader.exec_module(preview)

def setup_args(tmp_path,monkeypatch,report):
    source=tmp_path/'render'; (source/'frames').mkdir(parents=True)
    (source/'render-report.json').write_text(json.dumps(report))
    monkeypatch.setattr(sys,'argv',['pack','--render',str(source),'--out',str(tmp_path/'out'),
                                   '--font',str(tmp_path/'not_accessed.ttf')])
    return source

def test_missing_frames_cannot_be_reported_as_complete(tmp_path,monkeypatch):
    setup_args(tmp_path,monkeypatch,{'frames_rendered':2})
    with pytest.raises(ValueError,match='Missing/extra'): preview.main()

@pytest.mark.parametrize('field,value',[('jev_calls',1),('driveable',True),('physics_simulated',True)])
def test_inspection_label_cannot_misclassify_other_run_types(tmp_path,monkeypatch,field,value):
    report={'frames_rendered':1,'jev_calls':0,'driveable':False,'physics_simulated':False,field:value}
    source=setup_args(tmp_path,monkeypatch,report)
    (source/'frames/frame_0001.png').write_bytes(b'not read before rejection')
    with pytest.raises(ValueError,match='only visual inspections'): preview.main()
