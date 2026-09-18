"""Camera/asset contracts only; these do not establish photorealism or safety."""
import hashlib, json
import numpy as np
import pytest
from shapely.geometry import LineString, box
from jevdrive.visual_quality import TerrainSampler, clip_directed_route, verify_asset_pack

TRI=[[[0,0,5],[10,0,15],[0,10,25]]]

@pytest.mark.parametrize('x,y,z',[(0,0,5),(10,0,15),(0,10,25),(2,3,13),(5,5,20)])
def test_barycentric_heights_not_nearest_vertices(x,y,z):
    assert TerrainSampler(TRI).height(x,y)==pytest.approx(z)

@pytest.mark.parametrize('x,y',[(-1,0),(11,0),(6,6),(50,0),(0,float('nan'))])
def test_outside_or_invalid_has_no_fabricated_height(x,y):
    with pytest.raises(ValueError): TerrainSampler(TRI).height(x,y)

def test_overlapping_surfaces_are_not_silently_selected():
    high=(np.array(TRI)+[0,0,1]).tolist()
    with pytest.raises(ValueError,match='Ambiguous'):
        TerrainSampler(TRI+high).height(2,3)

def test_degenerate_triangle_is_not_a_surface():
    with pytest.raises(ValueError): TerrainSampler([[[0,0,0]]*3]).height(0,0)

def test_shared_edge_is_continuous():
    sam=TerrainSampler(TRI+[[[10,0,15],[10,10,35],[0,10,25]]])
    assert sam.height(5,5)==pytest.approx(20)

@pytest.mark.parametrize('reverse',[False,True])
def test_clip_preserves_one_way_direction(reverse):
    coordinates=[(-20,0),(20,0)]
    if reverse: coordinates.reverse()
    line=LineString(coordinates); clipped=clip_directed_route(line,box(-5,-5,5,5))
    assert clipped.length==pytest.approx(10)
    assert clipped.coords[0][0]==(5 if reverse else -5)

def test_disconnected_coverage_is_not_bridged():
    line=LineString([(-20,0),(20,0)])
    region=box(-10,-2,-5,2).union(box(3,-2,10,2))
    result=clip_directed_route(line,region)
    assert result.length==pytest.approx(7)
    assert region.covers(result)

def test_missing_coverage_fails():
    with pytest.raises(ValueError):
        clip_directed_route(LineString([(0,0),(10,0)]),box(20,20,30,30))

@pytest.mark.parametrize('tamper',[False,True])
def test_asset_bytes_are_checked(tmp_path,tamper):
    data=b'fixture'; (tmp_path/'asset.bin').write_bytes(data)
    manifest={'resources':[{'path':'asset.bin','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()}]}
    (tmp_path/'asset-lock.json').write_text(json.dumps(manifest), encoding='utf8')
    if tamper:
        (tmp_path/'asset.bin').write_bytes(b'changed')
        with pytest.raises(ValueError): verify_asset_pack(tmp_path)
    else: assert verify_asset_pack(tmp_path)==manifest

def test_asset_path_cannot_escape_pack(tmp_path):
    manifest={'resources':[{'path':'../other','bytes':0,'sha256':'x'}]}
    (tmp_path/'asset-lock.json').write_text(json.dumps(manifest), encoding='utf8')
    with pytest.raises(ValueError,match='outside'): verify_asset_pack(tmp_path)

@pytest.mark.parametrize('triangles',[[],[[1,2,3]],[[[0,0,float('nan')],[1,0,0],[0,1,0]]]])
def test_invalid_triangle_input(triangles):
    with pytest.raises(ValueError): TerrainSampler(triangles)

def detail_fixture(tmp_path):
    import trimesh
    from jevdrive.publicworld.geo import ENU_TO_GLTF
    scene=trimesh.Scene()
    mesh=trimesh.Trimesh(vertices=[[0,0,5],[10,0,6],[0,10,7]],faces=[[0,1,2]],process=False)
    scene.add_geometry(mesh,geom_name='detail_tran_fixture',node_name='detail_tran_fixture')
    scene.apply_transform(ENU_TO_GLTF)
    data=scene.export(file_type='glb'); (tmp_path/'details.glb').write_bytes(data)
    lock=tmp_path/'download-lock.json'
    lock.write_text(json.dumps({'resources':[]}), encoding='utf8')
    origin={'longitude':139.76,'latitude':35.68,'ellipsoid_height_m':0}
    meta={'frame':origin,'glb_sha256':hashlib.sha256(data).hexdigest(),
          'download_lock_sha256':hashlib.sha256(lock.read_bytes()).hexdigest()}
    (tmp_path/'details-manifest.json').write_text(json.dumps(meta), encoding='utf8')
    return origin

def test_real_detail_axis_and_surface_sampling(tmp_path):
    from jevdrive.visual_quality import load_detail_road_sampler
    origin=detail_fixture(tmp_path)
    sampler,_=load_detail_road_sampler(tmp_path,origin)
    assert sampler.height(2,3)==pytest.approx(5.8)

@pytest.mark.parametrize('changed',['origin','bytes','lock'])
def test_detail_identity_drift_fails(tmp_path,changed):
    from jevdrive.visual_quality import load_detail_road_sampler
    origin=detail_fixture(tmp_path)
    if changed=='origin': origin={**origin,'longitude':origin['longitude']+.001}
    elif changed=='bytes': (tmp_path/'details.glb').write_bytes(b'changed')
    else: (tmp_path/'download-lock.json').write_text('{"resources":[],"changed":true}', encoding='utf8')
    with pytest.raises(ValueError): load_detail_road_sampler(tmp_path,origin)

def test_detail_plan_changes_only_source_surface_and_preserves_input(tmp_path):
    from jevdrive.visual_quality import apply_detail_surface
    origin=detail_fixture(tmp_path)
    frame={'xyz':[2,3,2],'target':[3,2,2],'terrain_z':.45}
    plan={'frames':[frame],'camera_height_m':1.55,'trees':[{'generic':'not used'}]}
    updated=apply_detail_surface(plan,tmp_path,origin)
    assert plan['frames'][0]['xyz'][2]==2
    assert updated['frames'][0]['xyz'][2]==pytest.approx(7.35)
    assert updated['frames'][0]['surface_z']==pytest.approx(5.8)
    assert updated['trees']==[]
    assert updated['height_surface']=='PLATEAU LOD3 road mesh'
