"""Offline source and coordinate contracts; not photorealism or safety evidence."""
import hashlib,json
import numpy as np
import pytest
from jevdrive.hero_assets import normalize_car_bounds,fit_support_plane,validate_render_frames,verify_asset_lock

def test_normalization_preserves_proportions_and_forward():
    lo=np.array([-274.81,-127.861,-7.25]);hi=np.array([319.22,132.189,193.154]);m=normalize_car_bounds(lo,hi)
    points=np.array([[x,y,z,1] for x in [lo[0],hi[0]] for y in [lo[1],hi[1]] for z in [lo[2],hi[2]]])@m.T
    sizes=np.ptp(points[:,:3],axis=0)
    assert sizes[1]==pytest.approx(4.75)
    assert sizes[0]/sizes[1]==pytest.approx((hi[1]-lo[1])/(hi[0]-lo[0]))
    assert points[:,2].min()==pytest.approx(0)
    assert (m@np.array([-1,0,0,0]))[1]>0 and np.linalg.det(m[:3,:3])>0

@pytest.mark.parametrize('lo,hi',[([0,0,0],[0,1,1]),([0,0,0],[1,-1,1]),([0,0,float('nan')],[1,1,1]),([0,0],[1,1])])
def test_bad_bounds(lo,hi):
    with pytest.raises(ValueError):normalize_car_bounds(lo,hi)

@pytest.mark.parametrize('length',[0,-1,10,float('inf'),float('nan'),True])
def test_bad_length(length):
    with pytest.raises(ValueError):normalize_car_bounds([0,0,0],[4,2,1],length)

def test_support_plane():
    xy=np.array([[-1,-1],[-1,1],[1,-1],[1,1]])
    fit,error=fit_support_plane(np.column_stack([xy,40+.01*xy[:,0]+.02*xy[:,1]]))
    np.testing.assert_allclose(fit,[.01,.02,40],atol=1e-10);assert error<1e-10

@pytest.mark.parametrize('points',[[[0,0,0]]*4,[[0,0,0]]*3,[[0,0,float('nan')]]*4,[[-1,-1,0],[-1,1,0],[1,-1,0],[1,1,1]]])
def test_bad_contact(points):
    with pytest.raises(ValueError):fit_support_plane(points)

@pytest.mark.parametrize('mutation',['gap','time','nan','bool_id','fps','count'])
def test_frame_failure(mutation):
    rows=[{'frame':i+1,'time_s':i/30} for i in range(4)];fps=30;count=4
    if mutation=='gap':rows[2]['frame']=4
    if mutation=='time':rows[2]['time_s']=.9
    if mutation=='nan':rows[2]['time_s']=float('nan')
    if mutation=='bool_id':rows[0]['frame']=True
    if mutation=='fps':fps=True
    if mutation=='count':count=5
    with pytest.raises(ValueError):validate_render_frames(rows,fps,count)

def test_valid_frames():
    assert validate_render_frames([{'frame':i+1,'time_s':i/30} for i in range(180)],30,180)

@pytest.mark.parametrize('mutation',['none','bytes','path','duplicate','empty','size'])
def test_source_lock(tmp_path,mutation):
    data=b'source';(tmp_path/'mesh.bin').write_bytes(data)
    row={'path':'mesh.bin','bytes':len(data),'sha256':hashlib.sha256(data).hexdigest()};rows=[row]
    if mutation=='bytes':(tmp_path/'mesh.bin').write_bytes(b'change')
    if mutation=='path':row['path']='../unknown.bin'
    if mutation=='duplicate':rows.append(row.copy())
    if mutation=='empty':rows=[]
    if mutation=='size':row['bytes']=True
    (tmp_path/'download-lock.json').write_text(json.dumps({'resources':rows}),encoding='utf8')
    if mutation=='none':assert verify_asset_lock(tmp_path)['resources']==rows
    else:
        with pytest.raises(ValueError):verify_asset_lock(tmp_path)
