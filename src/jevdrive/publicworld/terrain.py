"""Decode real quantized-mesh heights and preserve their ellipsoid datum."""
from __future__ import annotations
import gzip,struct
import numpy as np
from .geo import geodetic_bounds


def decode_quantized_mesh(data:bytes,z:int,x:int,y:int):
    if data[:2]==b'\x1f\x8b':
        import io
        with gzip.GzipFile(fileobj=io.BytesIO(data)) as f:
            data=f.read(64_000_001)
        if len(data)>64_000_000: raise ValueError('Decompressed terrain tile exceeds size cap')
    if len(data)<92: raise ValueError('Truncated quantized mesh')
    hmin,hmax=struct.unpack_from('<2f',data,24)
    if not np.isfinite([hmin,hmax]).all() or hmax<hmin: raise ValueError('Invalid terrain height range')
    n=struct.unpack_from('<I',data,88)[0]
    if not 3<=n<=2_000_000 or 92+n*6>len(data): raise ValueError('Invalid terrain vertex count')
    packed=np.frombuffer(data,dtype='<u2',count=3*n,offset=92).reshape(3,n).astype(np.int64)
    decoded=np.cumsum((packed>>1)^(-(packed&1)),axis=1)
    if np.any(decoded<0) or np.any(decoded>32767): raise ValueError('Out-of-range quantized vertex')
    offset=92+6*n
    itemsize=4 if n>65536 else 2
    offset=(offset+itemsize-1)//itemsize*itemsize
    if offset+4>len(data): raise ValueError('Missing triangle count')
    tri_count=struct.unpack_from('<I',data,offset)[0];offset+=4
    if tri_count>4_000_000 or offset+tri_count*3*itemsize>len(data): raise ValueError('Invalid terrain triangle count')
    codes=np.frombuffer(data,dtype='<u4' if itemsize==4 else '<u2',count=tri_count*3,offset=offset).astype(np.int64)
    high=0;indices=np.empty(len(codes),np.int64)
    for i,code in enumerate(codes):
        indices[i]=high-int(code)
        if code==0: high+=1
    if np.any(indices<0) or np.any(indices>=n): raise ValueError('Invalid high-water-mark index')
    west,south,east,north=geodetic_bounds(z,x,y)
    u,v,h=decoded/32767
    lon=west+(east-west)*u;lat=south+(north-south)*v
    heights=hmin+(hmax-hmin)*h
    return lon,lat,heights,indices.reshape(-1,3)


def decode_gsi_png(pixels):
    """Ancillary GSI DEM decoder; these heights are NOT automatically ellipsoidal."""
    a=np.asarray(pixels)
    if a.ndim!=3 or a.shape[2] not in (3,4): raise ValueError('Expected RGB/RGBA')
    rgb=a[:,:,:3].astype(np.int64)
    code=rgb[:,:,0]*65536+rgb[:,:,1]*256+rgb[:,:,2]
    missing=code==2**23
    if a.shape[2]==4: missing|=a[:,:,3]==0
    metres=np.where(code<2**23,code,code-2**24).astype(float)*.01
    metres[missing]=np.nan
    return metres
