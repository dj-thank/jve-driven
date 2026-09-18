"""Synthetic unit/integration fixtures. NONE are real PLATEAU scene data."""
from __future__ import annotations
import io,json,struct,gzip,math
from pathlib import Path
import httpx
import numpy as np
import pytest
import trimesh
from PIL import Image
from jevdrive.publicworld.geo import Area,Frame,GLTF_TO_ZUP,ENU_TO_GLTF,geodetic_tiles,geodetic_bounds,xyz_tiles,xyz_pixel
from jevdrive.publicworld.download import DownloadStore,verify_lock,validate_url
from jevdrive.publicworld.terrain import decode_quantized_mesh,decode_gsi_png
from jevdrive.publicworld.tiles3d import matrix,intersects,unpack_b3dm,load_geometry,collect_buildings,glb_document
from jevdrive.publicworld.pipeline import read_config,fetch_snapshot,build_snapshot,require_driveable,centerlines_from_osm,REQUIRED_GATES

BASE='https://api.plateauview.mlit.go.jp/'
FRAME=Frame(139.7639,35.68085)
AOI=Area(139.7638,35.68075,139.764,35.68095)

def png(alpha=255):
    img=Image.new('RGBA',(256,256),(21,91,163,alpha));out=io.BytesIO();img.save(out,format='PNG');return out.getvalue()

def terrain_bytes(hmin=45.,hmax=48.):
    # Four TMS corners: SW, SE, NW, NE. A wholly synthetic test tile.
    arrays=[[0,32767,0,32767],[0,0,32767,32767],[0,0,32767,32767]]
    header=bytearray(88);struct.pack_into('<2f',header,24,hmin,hmax)
    data=bytes(header)+struct.pack('<I',4)
    for a in arrays:
        prev=0
        for v in a:
            d=v-prev;data+=struct.pack('<H',(d<<1)^(d>>31));prev=v
    # triangles [0,1,2], [1,3,2], high-water code [0,0,0,2,0,2]
    data+=struct.pack('<I6H',2,0,0,0,2,0,2)
    # Real quantized-mesh edge lists (not needed by decoder).
    for edge in ((0,2),(0,1),(1,3),(2,3)): data+=struct.pack('<I2H',2,*edge)
    return data

def sample_glb():
    mesh=trimesh.creation.box((10,20,10));mesh.apply_translation([0,55,0])
    mesh.visual=trimesh.visual.TextureVisuals(uv=np.zeros((len(mesh.vertices),2)),image=Image.open(io.BytesIO(png())))
    return trimesh.Scene(mesh).export(file_type='glb')

def b3dm(glb,rtc=(1,2,3),binary=False):
    feat={'BATCH_LENGTH':0,'RTC_CENTER':{'byteOffset':0} if binary else list(rtc)}
    fj=json.dumps(feat).encode();fj+=b' '*((8-(28+len(fj))%8)%8)
    fb=struct.pack('<3f',*rtc) if binary else b''
    fb+=b'\0'*((8-(28+len(fj)+len(fb))%8)%8)
    n=28+len(fj)+len(fb)+len(glb)
    return struct.pack('<4s6I',b'b3dm',1,n,len(fj),len(fb),0,0)+fj+fb+glb

def region(area=AOI): return [*np.radians(area.values),0,200]

def config_file(tmp_path,osm=False):
    c={'schema':'jevdrive.public-world-config.v1','name':'SYNTHETIC TEST ONLY',
       'bounds_wgs84':AOI.values,'origin':{'longitude':FRAME.longitude,'latitude':FRAME.latitude},
       'building_spec':'13101-bldg-lod2-texture-latest','imagery_zoom':10,'terrain_zoom':15,
       'terrain_base':'https://tile.plateauview.mlit.go.jp/terrain/',
       'imagery_template':'https://tile.plateauview.mlit.go.jp/tiles/plateau-ortho-2023/{z}/{x}/{y}.png',
       'max_download_bytes':5_000_000,'max_download_files':100,'include_osm_centerlines':osm,'surface_role':'visual_only'}
    path=tmp_path/'config.json';path.write_text(json.dumps(c), encoding='utf8');return path

def fake_client(*,missing=None,alpha=255):
    glb=sample_glb();transform=np.linalg.inv(FRAME.ecef_to_enu).flatten(order='F').tolist()
    tileset={'asset':{'version':'1.0'},'root':{'boundingVolume':{'region':region()},'geometricError':0,
            'transform':transform,'content':{'uri':'https://assets.cms.plateau.reearth.io/test.glb'}}}
    def handler(req):
        assert 'authorization' not in req.headers and 'cookie' not in req.headers
        p=req.url.path
        if missing and missing in p: return httpx.Response(404)
        if p.endswith('tileset.json'): return httpx.Response(200,json=tileset)
        if p.endswith('test.glb'): return httpx.Response(200,content=glb)
        if p.endswith('layer.json'): return httpx.Response(200,json={'format':'quantized-mesh-1.0',
            'projection':'EPSG:4326','scheme':'tms','maxzoom':15,'tiles':['{z}/{x}/{y}.terrain'],'attribution':'SYNTHETIC'})
        if p.endswith('.terrain'): return httpx.Response(200,content=terrain_bytes())
        if p.endswith('.png'): return httpx.Response(200,content=png(alpha))
        if p.endswith('/map'): return httpx.Response(200,content=b'<osm><node id="1" lat="35.68" lon="139.76"/><node id="2" lat="35.681" lon="139.761"/><way id="3"><nd ref="1"/><nd ref="2"/><tag k="highway" v="residential"/></way></osm>')
        raise AssertionError(f'Unexpected fixture URL: {req.url}')
    return httpx.Client(transport=httpx.MockTransport(handler),follow_redirects=False)

def test_frame_origin(): np.testing.assert_allclose(FRAME.points([FRAME.longitude],[FRAME.latitude],[0]),[[0,0,0]],atol=1e-8)
def test_frame_up(): np.testing.assert_allclose(FRAME.points([FRAME.longitude],[FRAME.latitude],[70]),[[0,0,70]],atol=1e-7)
def test_frame_east_north():
    east,north=FRAME.points([FRAME.longitude+.0001,FRAME.longitude],[FRAME.latitude,FRAME.latitude+.0001],[0,0])
    assert east[0]>8 and abs(east[1])<.01 and north[1]>10 and abs(north[0])<.01

def test_axis_roundtrip(): np.testing.assert_array_equal(ENU_TO_GLTF@GLTF_TO_ZUP,np.eye(4))
@pytest.mark.parametrize('bounds',[(0,0,1,1),(0,0,-1,1),(0,0,.01,float('nan')),(179,0,-179,.01)])
def test_bad_aoi(bounds):
    with pytest.raises(ValueError): Area(*bounds)
def test_geodetic_tms_axis(): assert geodetic_bounds(0,0,0)==[-180,-90,0,90]
def test_tile_index_not_xyz():
    z,x,y=geodetic_tiles(AOI,15)[0];w,s,e,n=geodetic_bounds(z,x,y)
    assert w<AOI.east and e>AOI.west and s<AOI.north and n>AOI.south
    assert y!=xyz_tiles(AOI,15)[0][2]
def test_xyz_center(): np.testing.assert_allclose(xyz_pixel(0,0,1),(256,256))
def test_column_major_matrix():
    t=np.eye(4);t[:3,3]=[1,2,3];np.testing.assert_array_equal(matrix(t.flatten(order='F')),t)
def test_invalid_matrix():
    with pytest.raises(ValueError): matrix(np.full(16,np.nan))
def test_region_ignores_transform(): assert intersects({'region':region()},np.eye(4)*2,FRAME,AOI)
def test_region_outside(): assert not intersects({'region':region(Area(139.8,35.7,139.81,35.71))},np.eye(4),FRAME,AOI)
@pytest.mark.parametrize('volume',[{'sphere':[0,0,50,10]},{'box':[0,0,50,10,0,0,0,10,0,0,0,20]}])
def test_box_sphere_culling(volume): assert intersects(volume,np.linalg.inv(FRAME.ecef_to_enu),FRAME,AOI)
def test_unknown_volume():
    with pytest.raises(ValueError): intersects({},np.eye(4),FRAME,AOI)
def test_quantized_mesh():
    lon,lat,h,f=decode_quantized_mesh(terrain_bytes(),0,1,0)
    np.testing.assert_allclose(lon,[0,180,0,180]);np.testing.assert_allclose(lat,[-90,-90,90,90])
    np.testing.assert_allclose(h,[45,45,48,48]);np.testing.assert_array_equal(f,[[0,1,2],[1,3,2]])
def test_gzip_quantized_mesh():
    a=decode_quantized_mesh(terrain_bytes(),15,*geodetic_tiles(AOI,15)[0][1:])
    b=decode_quantized_mesh(gzip.compress(terrain_bytes()),15,*geodetic_tiles(AOI,15)[0][1:])
    for x,y in zip(a,b): np.testing.assert_array_equal(x,y)
@pytest.mark.parametrize('raw',[b'',b'x'*91,terrain_bytes()[:100],terrain_bytes(hmin=9,hmax=-2)])
def test_bad_quantized_mesh(raw):
    with pytest.raises(ValueError): decode_quantized_mesh(raw,0,0,0)
def test_invalid_terrain_indices():
    raw=bytearray(terrain_bytes());struct.pack_into('<H',raw,120,4)
    with pytest.raises(ValueError,match='index'): decode_quantized_mesh(raw,0,0,0)
def test_gsi_negative_missing():
    out=decode_gsi_png(np.array([[[0,0,100],[255,255,156],[128,0,0],[0,0,1]]],np.uint8))
    assert out[0,0]==1 and out[0,1]==-1 and np.isnan(out[0,2]) and out[0,3]==.01
@pytest.mark.parametrize('binary',[False,True])
def test_b3dm_rtc(binary):
    glb=sample_glb();decoded,rtc,batch=unpack_b3dm(b3dm(glb,binary=binary))
    assert decoded==glb;np.testing.assert_array_equal(rtc,[1,2,3]);assert batch['batch_length']==0
def test_b3dm_length_invalid():
    with pytest.raises(ValueError): unpack_b3dm(b3dm(sample_glb())[:-1])
def test_glb_loaded_with_height_and_texture():
    sc=load_geometry(sample_glb(),np.linalg.inv(FRAME.ecef_to_enu),FRAME,'fixture')
    assert abs(sc.bounds[0,2]-45)<1e-5 and abs(sc.bounds[1,2]-65)<1e-5
    assert next(iter(sc.geometry.values())).visual.kind=='texture'
def test_b3dm_rtc_applied_after_axis():
    sc=load_geometry(b3dm(sample_glb(),(10,20,30)),np.linalg.inv(FRAME.ecef_to_enu),FRAME,'fixture')
    np.testing.assert_allclose(sc.centroid,[10,20,85],atol=1e-6)
@pytest.mark.parametrize('url',['http://api.plateauview.mlit.go.jp/x','https://evil.test/x','https://api.plateauview.mlit.go.jp.evil.test/x','https://user@api.plateauview.mlit.go.jp/x','https://api.plateauview.mlit.go.jp/x?key=secret','https://api.plateauview.mlit.go.jp:444/x'])
def test_unapproved_urls(url):
    with pytest.raises(ValueError): validate_url(url)
def test_store_budget(tmp_path):
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=b'1234'))) as c:
        store=DownloadStore(tmp_path,max_bytes=3,client=c)
        with pytest.raises(RuntimeError,match='budget'): store.fetch(BASE+'a')
        assert not store.records

def test_store_redirect_not_followed_to_unknown(tmp_path):
    calls=[]
    def handler(req): calls.append(str(req.url));return httpx.Response(302,headers={'location':'https://evil.test/secret'})
    with httpx.Client(transport=httpx.MockTransport(handler)) as c:
        with pytest.raises(ValueError): DownloadStore(tmp_path,client=c).fetch(BASE+'a')
    assert len(calls)==1

def test_store_hash_and_tamper(tmp_path):
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=b'valid'))) as c:
        store=DownloadStore(tmp_path,client=c);data,r=store.fetch(BASE+'a');assert verify_lock(tmp_path)==1
        (tmp_path/r['path']).write_bytes(b'wrong')
        with pytest.raises(RuntimeError): verify_lock(tmp_path)
        with pytest.raises(RuntimeError): store.fetch(BASE+'a')

def test_lock_path_traversal(tmp_path):
    (tmp_path/'download-lock.json').write_text(json.dumps({'resources':[{'path':'../secret','bytes':0,'sha256':'a'}]}), encoding='utf8')
    with pytest.raises(ValueError): verify_lock(tmp_path)

def test_osm_no_invented_lanes():
    with fake_client() as c: data=c.get('https://api.openstreetmap.org/api/0.6/map').content
    road=centerlines_from_osm(data)['features'][0]['properties']
    assert road['width_m'] is None and road['lane_geometry'] is None and road['driveable'] is False
@pytest.mark.parametrize('xml',[b'<!DOCTYPE osm><osm/>',b'<osm><way><nd ref="1"/><tag k="highway" v="road"/></way></osm>',b'<html/>'])
def test_unsafe_incomplete_osm(xml):
    with pytest.raises(ValueError): centerlines_from_osm(xml)
def test_driveability_gate_cannot_be_flipped():
    with pytest.raises(RuntimeError,match='adapter'): require_driveable({'schema':'jevdrive.public-world.v1','stage':'built','acceptance':dict.fromkeys(REQUIRED_GATES,'verified')})
def test_driveability_fail_closed():
    with pytest.raises(RuntimeError,match='lane_topology'): require_driveable({'schema':'jevdrive.public-world.v1','stage':'built','acceptance':{}})
def test_fetch_build_offline_integration(tmp_path):
    config=config_file(tmp_path,True);out=tmp_path/'snapshot'
    with fake_client() as c: manifest=fetch_snapshot(config,out,client=c)
    assert manifest['stage']=='fetched' and manifest['road_way_count']==1 and not manifest['capture_dates_verified']
    stats=build_snapshot(out)
    assert stats['building_triangles']==12 and stats['terrain_triangles']>=2
    assert stats['verified_input_resources']>=6 and not stats['blender_executed']
    scene=trimesh.load_scene(out/'visual-world.glb',process=False)
    assert len(scene.geometry)>=2
    assert all(g.visual.kind=='texture' for g in scene.geometry.values())
    with pytest.raises(RuntimeError): require_driveable(json.loads((out/'public-world.json').read_text(encoding='utf8')))
@pytest.mark.parametrize('missing',['.glb','.terrain','.png'])
def test_missing_data_stops_no_fake_fallback(tmp_path,missing):
    config=config_file(tmp_path);out=tmp_path/'snapshot'
    with fake_client(missing=missing) as c:
        with pytest.raises(httpx.HTTPStatusError): fetch_snapshot(config,out,client=c)
    assert json.loads((out/'public-world.json').read_text(encoding='utf8'))['stage']=='failed'
    assert not (out/'visual-world.glb').exists()
    with pytest.raises(ValueError,match='incomplete'): build_snapshot(out)
def test_transparent_imagery_stops(tmp_path):
    config=config_file(tmp_path);out=tmp_path/'snapshot'
    with fake_client(alpha=0) as c:
        with pytest.raises(RuntimeError,match='transparent'): fetch_snapshot(config,out,client=c)
    assert not (out/'visual-world.glb').exists()
def test_existing_snapshot_not_overwritten(tmp_path):
    config=config_file(tmp_path);out=tmp_path/'snapshot';out.mkdir();(out/'keep').write_text('keep', encoding='utf8')
    with pytest.raises(ValueError): fetch_snapshot(config,out)
    assert (out/'keep').read_text(encoding='utf8')=='keep'

@pytest.mark.parametrize('refine,expected',[('REPLACE',['child.glb']),('ADD',['parent.glb','child.glb'])])
def test_tiles_frontier_no_duplicate_parent(tmp_path,refine,expected):
    calls=[];url=BASE+'tileset.json'
    doc={'asset':{'version':'1.0'},'root':{'boundingVolume':{'region':region()},'refine':refine,
         'content':{'uri':'parent.glb'},'children':[{'boundingVolume':{'region':region()},'content':{'uri':'child.glb'}}]}}
    def handler(req):
        calls.append(req.url.path)
        return httpx.Response(200,json=doc) if req.url.path.endswith('.json') else httpx.Response(200,content=sample_glb())
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        records=collect_buildings(DownloadStore(tmp_path,client=client),url,FRAME,AOI)
    assert [r['url'].split('/')[-1] for r in records]==expected
    if refine=='REPLACE': assert '/parent.glb' not in calls

def test_external_tileset_inherits_transform(tmp_path):
    t=np.eye(4);t[:3,3]=[11,22,33]
    root={'asset':{'version':'1.0'},'root':{'boundingVolume':{'region':region()},
          'transform':t.flatten(order='F').tolist(),'content':{'uri':'child.json'}}}
    child={'asset':{'version':'1.0'},'root':{'boundingVolume':{'region':region()},'content':{'uri':'a.glb'}}}
    def handler(req):
        if req.url.path.endswith('/root.json'): return httpx.Response(200,json=root)
        if req.url.path.endswith('/child.json'): return httpx.Response(200,json=child)
        return httpx.Response(200,content=sample_glb())
    with httpx.Client(transport=httpx.MockTransport(handler)) as client:
        records=collect_buildings(DownloadStore(tmp_path,client=client),BASE+'root.json',FRAME,AOI)
    np.testing.assert_array_equal(matrix(records[0]['transform_column_major']),t)

def test_external_tileset_cycle_rejected(tmp_path):
    doc={'asset':{'version':'1.0'},'root':{'boundingVolume':{'region':region()},'content':{'uri':'root.json'}}}
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=doc))) as client:
        with pytest.raises(ValueError,match='Cyclic'):
            collect_buildings(DownloadStore(tmp_path,client=client),BASE+'root.json',FRAME,AOI)

def test_implicit_tiling_explicitly_rejected(tmp_path):
    doc={'asset':{'version':'1.1'},'root':{'boundingVolume':{'region':region()},'implicitTiling':{}}}
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,json=doc))) as client:
        with pytest.raises(RuntimeError,match='Implicit'):
            collect_buildings(DownloadStore(tmp_path,client=client),BASE+'root.json',FRAME,AOI)

def test_empty_asset_rejected(tmp_path):
    with httpx.Client(transport=httpx.MockTransport(lambda r:httpx.Response(200,content=b''))) as c:
        with pytest.raises(RuntimeError,match='Empty'): DownloadStore(tmp_path,client=c).fetch(BASE+'a')
