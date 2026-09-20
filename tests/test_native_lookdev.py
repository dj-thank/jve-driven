"""Geometry/preset contracts; native image evidence is recorded separately."""
import ast
import importlib.util
import math
from pathlib import Path
from types import SimpleNamespace as NS
import pytest

ROOT=Path(__file__).resolve().parents[1]
spec=importlib.util.spec_from_file_location('lookdev_test',ROOT/'tools/native_lookdev.py')
look=importlib.util.module_from_spec(spec); spec.loader.exec_module(look)

@pytest.mark.parametrize('forward',[(1,0),(0,1),(3,4),(-4,3)])
def test_paving_has_metric_scale_and_consistent_handedness(forward):
    length=math.hypot(*forward); t=[v/length for v in forward]; origin=(20,30)
    assert look.paving_uv(*origin,origin,forward,2)==(0,0)
    assert look.paving_uv(20+2*t[0],30+2*t[1],origin,forward,2)==pytest.approx((0,1))
    assert look.paving_uv(20+2*t[1],30-2*t[0],origin,forward,2)==pytest.approx((1,0))

@pytest.mark.parametrize('repeat',[-1,0,.01,21,math.inf,math.nan,True])
def test_uv_scale_invalid(repeat):
    with pytest.raises(ValueError): look.paving_uv(0,0,(0,0),(1,0),repeat)

def test_uv_direction_cannot_be_zero():
    with pytest.raises(ValueError): look.paving_uv(0,0,(0,0),(0,0),1)

@pytest.mark.parametrize('args',[{}, {'half':1,'opening':.35,'pitch':.1,'bar':.025}])
def test_grate_retains_trunk_opening(args):
    opening=args.get('opening',.28); half=args.get('half',.70)
    boxes=look.grate_segments(**args)
    assert len(boxes)>30
    for x0,y0,x1,y1 in boxes:
        assert x1>x0 and y1>y0
        assert max(abs(x0),abs(x1),abs(y0),abs(y1))<=half+.061
        assert x1<=-opening or x0>=opening or y1<=-opening or y0>=opening

@pytest.mark.parametrize('kwargs',[{'half':3},{'opening':0},{'opening':.8},{'pitch':.001},{'bar':.2}])
def test_bad_grate_config(kwargs):
    with pytest.raises(ValueError): look.grate_segments(**kwargs)

def test_unknown_light_preset_rejected():
    with pytest.raises(ValueError): look.configure_lighting(None,'fake')

def test_explicit_utf8_for_text_files():
    # CI previously forced UTF-8, concealing ten failures under Japanese Windows.
    missing=[]
    for folder in ('src','tools','tests'):
        for path in (ROOT/folder).rglob('*.py'):
            if 'node_modules' in path.parts: continue
            tree=ast.parse(path.read_text(encoding='utf8'))
            for node in ast.walk(tree):
                if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr in ('read_text','write_text'):
                    if not any(k.arg=='encoding' for k in node.keywords): missing.append(str(path.relative_to(ROOT))+':'+str(node.lineno))
    assert missing==[]
