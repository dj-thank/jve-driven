import hashlib
import json
from pathlib import Path
import math
import pytest
import trimesh
from shapely.geometry import Polygon
from pyproj import Transformer
from jevdrive.world import parse_osm,export_world,DEFAULT_PROJ,enu_to_carla,enu_to_unreal_cm,number,speed_mps
from jevdrive.simulation import simulate,SCENARIOS

ROOT=Path(__file__).resolve().parents[1]
OSM=ROOT/'data/raw/kirchberg_subset.osm'


def test_input_hash_and_real_ids():
    m=json.loads((ROOT/'data/raw/PROVENANCE.json').read_text(encoding='utf8'))
    assert hashlib.sha256(OSM.read_bytes()).hexdigest()==m['local_sha256']
    w=parse_osm(OSM)
    assert len(w['roads'])==3 and len(w['buildings'])==10
    assert {r['osm_id'] for r in w['roads']}=={'25216931','25216933','123874631'}
    assert w['source_snapshot_utc']=='2020-08-10T00:00:00Z'
    assert all(Polygon(b['points']).is_valid for b in w['buildings'])
    assert 240<sum(r['length_m'] for r in w['roads'])<250


def test_join_node_preserved():
    w=parse_osm(OSM)
    a,b=w['roads'][:2]
    assert a['points'][a['node_ids'].index('274969427')]==b['points'][-1]


def test_projection_origin_roundtrip():
    t=Transformer.from_crs('EPSG:4326',DEFAULT_PROJ,always_xy=True)
    back=Transformer.from_crs(DEFAULT_PROJ,'EPSG:4326',always_xy=True)
    x,y=t.transform(10.0701,48.13565)
    assert abs(x)<1e-6 and abs(y)<1e-6
    x,y=t.transform(10.0704523,48.1360495)
    lon,lat=back.transform(x,y)
    assert abs(lon-10.0704523)<1e-8 and abs(lat-48.1360495)<1e-8
    assert enu_to_carla(x,y)==(x,-y,0)
    assert enu_to_unreal_cm(x,y)==(100*x,-100*y,0)


def test_build_and_reload_glb(tmp_path):
    report=export_world(OSM,tmp_path)
    scene=trimesh.load(tmp_path/'kirchberg.glb',force='scene')
    assert len(scene.geometry)==report['geometry_count']
    assert all(g.is_watertight for g in scene.geometry.values())
    assert scene.bounds[1][1]>6  # glTF Y is height


@pytest.mark.parametrize('text,expected',[('5',5),('5.5 m',5.5),('10 ft',3.048),('10;12',None),('bad',None)])
def test_lengths(text,expected):
    assert number(text)==expected


def test_mph():
    assert speed_mps('30 mph')==pytest.approx(13.4112)


@pytest.mark.parametrize('badxml',[
 '<osm><way id="1"><nd ref="1"/><nd ref="2"/><tag k="highway" v="residential"/></way></osm>',
 '<!DOCTYPE osm [<!ENTITY a "bad">]><osm/>',
 '<osm><node id="1" lat="999" lon="0"/></osm>',
 '<html/>'])
def test_invalid_maps_rejected(tmp_path,badxml):
    p=tmp_path/'bad.osm';p.write_text(badxml, encoding='utf8')
    with pytest.raises(ValueError): parse_osm(p)


@pytest.mark.parametrize('scenario',SCENARIOS)
def test_kinematic_smoke(scenario):
    r=simulate(parse_osm(OSM),scenario)
    assert r['mode']=='baseline' and r['jev_calls']==0
    assert r['observation_source']=='ground_truth_debug'
    assert not r['metrics']['collision_proxy']
    assert not r['metrics']['red_line_crossing_proxy']
    assert r['metrics']['max_cross_track_error_m']<.4
    assert r['metrics']['max_speed_mps']<=30/3.6+.01
    assert not r['jevs_real_driving_performance_evaluated']


def test_live_requires_realtime():
    with pytest.raises(ValueError,match='realtime'):
        simulate(parse_osm(OSM),mode='jev-live')


def test_uniform_prisms_export_without_optional_scipy_conversion(tmp_path, monkeypatch):
    # A fresh CI environment has no SciPy. Uniform materials should not need
    # a sparse face-to-vertex average; the geometry and colour are unchanged.
    import trimesh.visual.color
    def forbidden(*args, **kwargs):
        raise AssertionError('Uniform prism colours must not request face averaging')
    monkeypatch.setattr(trimesh.visual.color, 'face_to_vertex_color', forbidden)
    report = export_world(OSM, tmp_path)
    assert report['triangles'] == 4516
    scene = trimesh.load_scene(tmp_path / 'kirchberg.glb')
    assert all(g.visual.kind == 'vertex' for g in scene.geometry.values())
    assert all((g.visual.vertex_colors == g.visual.vertex_colors[0]).all()
               for g in scene.geometry.values())
