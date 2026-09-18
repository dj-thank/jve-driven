"""Pure validation for reusable art assets; no real-vehicle interfaces."""
from __future__ import annotations
import hashlib,json,math
from pathlib import Path
import numpy as np

def file_sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
    return h.hexdigest()

def verify_asset_lock(root):
    root=Path(root).resolve();lock=json.loads((root/'download-lock.json').read_text(encoding='utf8'))
    rows=lock.get('resources')
    if not isinstance(rows,list) or not rows:raise ValueError('Empty asset lock')
    seen=set()
    for row in rows:
        path=(root/row['path']).resolve()
        if not path.is_relative_to(root) or path in seen:raise ValueError('Duplicate or escaping asset path')
        if type(row.get('bytes')) is not int or row['bytes']<=0:raise ValueError('Invalid asset byte count')
        if not path.is_file() or path.stat().st_size!=row['bytes'] or file_sha256(path)!=row['sha256']:raise ValueError('Source asset integrity failed')
        seen.add(path)
    return lock

def normalize_car_bounds(lo,hi,length_m=4.75):
    lo=np.asarray(lo,float);hi=np.asarray(hi,float)
    if lo.shape!=(3,) or hi.shape!=(3,) or not np.isfinite([lo,hi]).all() or np.any(hi<=lo):raise ValueError('Invalid model bounds')
    if isinstance(length_m,bool) or not isinstance(length_m,(int,float)) or not math.isfinite(length_m) or not 2<=length_m<=8:raise ValueError('Invalid target length')
    scale=length_m/(hi[0]-lo[0]);rotation=np.array([[0,1,0],[-1,0,0],[0,0,1]],float)
    matrix=np.eye(4);matrix[:3,:3]=rotation*scale
    center=np.array([(hi[0]+lo[0])/2,(hi[1]+lo[1])/2,lo[2]])
    matrix[:3,3]=-matrix[:3,:3]@center
    return matrix

def fit_support_plane(points,tolerance_m=.025):
    points=np.asarray(points,float)
    if points.shape!=(4,3) or not np.isfinite(points).all():raise ValueError('Expected four finite wheel supports')
    if not math.isfinite(tolerance_m) or not 0<tolerance_m<=.05:raise ValueError('Invalid contact tolerance')
    design=np.column_stack((points[:,:2],np.ones(4)))
    fit,_,rank,_=np.linalg.lstsq(design,points[:,2],rcond=None)
    if rank!=3:raise ValueError('Degenerate support arrangement')
    error=float(np.max(np.abs(design@fit-points[:,2])))
    if error>tolerance_m:raise ValueError('Support plane exceeds contact tolerance')
    return fit,error

def validate_render_frames(rows,fps,expected_count):
    if type(fps) is not int or not 1<=fps<=60:raise ValueError('Invalid fps')
    if type(expected_count) is not int or not 1<=expected_count<=900:raise ValueError('Invalid frame count')
    if len(rows)!=expected_count:raise ValueError('Missing frames')
    for i,row in enumerate(rows):
        if type(row.get('frame')) is not int or row['frame']!=i+1:raise ValueError('Frame numbering changed')
        if not math.isfinite(row.get('time_s',float('nan'))) or abs(row['time_s']-i/fps)>1e-8:raise ValueError('Frame clock changed')
    return True
