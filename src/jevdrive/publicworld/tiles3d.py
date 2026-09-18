"""Bounded 3D Tiles traversal and glTF-to-local-ENU conversion.

Unsupported encodings fail explicitly. They remain viewable with Cesium rather
than being silently exported with missing buildings or missing textures.
"""
from __future__ import annotations
import io,json,struct,math
from urllib.parse import urljoin
import numpy as np
import trimesh
from .geo import Area,Frame,GLTF_TO_ZUP
from .compression import decode_geometry,GEOMETRY_EXTENSIONS


def matrix(values=None):
    a=np.eye(4) if values is None else np.asarray(values,float).reshape((4,4),order='F')
    if not np.isfinite(a).all() or not np.allclose(a[3],[0,0,0,1]):
        raise ValueError('Invalid 3D Tiles affine transform')
    return a


def intersects(volume,transform,frame:Frame,area:Area):
    if 'region' in volume:
        # A region is already WGS84; tile.transform MUST NOT transform a region.
        r=volume['region']
        if len(r)!=6 or not np.isfinite(r).all(): raise ValueError('Invalid region')
        return area.intersects_region(r)
    local=frame.ecef_to_enu@transform
    aoi=frame.points([area.west,area.east,area.west,area.east],
                     [area.south,area.north,area.north,area.south],[0]*4)
    lo=aoi[:,:2].min(0);hi=aoi[:,:2].max(0)
    if 'sphere' in volume:
        s=np.asarray(volume['sphere'],float)
        if s.shape!=(4,) or not np.isfinite(s).all() or s[3]<0: raise ValueError('Invalid sphere')
        center=(local@np.r_[s[:3],1])[:3]
        radius=s[3]*np.linalg.norm(local[:3,:3],ord=2)
        return bool(np.all(center[:2]+radius>=lo) and np.all(center[:2]-radius<=hi))
    if 'box' in volume:
        b=np.asarray(volume['box'],float)
        if b.shape!=(12,) or not np.isfinite(b).all(): raise ValueError('Invalid box')
        center=(local@np.r_[b[:3],1])[:3]
        half_axes=b[3:].reshape((3,3),order='F')
        extent=np.abs(local[:3,:3]@half_axes).sum(axis=1)
        return bool(np.all(center[:2]+extent[:2]>=lo) and np.all(center[:2]-extent[:2]<=hi))
    raise ValueError('Unknown bounding volume; refusing an unbounded download')


def unpack_b3dm(data):
    if len(data)<28: raise ValueError('Truncated b3dm')
    magic,version,size,fj,fb,bj,bb=struct.unpack_from('<4s6I',data)
    if magic!=b'b3dm' or version!=1 or size!=len(data): raise ValueError('Invalid b3dm header')
    offset=28+fj+fb+bj+bb
    if offset+12>len(data): raise ValueError('Invalid b3dm section sizes')
    feature=json.loads(data[28:28+fj].rstrip(b' \x00')) if fj else {}
    rtc=feature.get('RTC_CENTER',[0,0,0])
    if isinstance(rtc,dict):
        index=rtc.get('byteOffset')
        if not isinstance(index,int) or index<0 or index+12>fb: raise ValueError('Bad binary RTC_CENTER')
        rtc=struct.unpack_from('<3f',data,28+fj+index)
    rtc=np.asarray(rtc,float)
    if rtc.shape!=(3,) or not np.isfinite(rtc).all(): raise ValueError('Invalid RTC_CENTER')
    batch=json.loads(data[28+fj+fb:28+fj+fb+bj].rstrip(b' \x00')) if bj else {}
    return data[offset:],rtc,{'batch_length':feature.get('BATCH_LENGTH'), 'batch_properties':list(batch)}


def glb_document(data):
    if len(data)<20: raise ValueError('Truncated GLB')
    magic,version,size=struct.unpack_from('<4sII',data)
    if magic!=b'glTF' or version!=2 or size!=len(data): raise ValueError('Expected valid glTF 2 GLB')
    n,kind=struct.unpack_from('<I4s',data,12)
    if kind!=b'JSON' or 20+n>len(data): raise ValueError('Bad GLB JSON chunk')
    return json.loads(data[20:20+n])


def load_geometry(data,transform,frame:Frame,name):
    rtc=np.zeros(3);batch={}
    if data[:4]==b'b3dm': data,rtc,batch=unpack_b3dm(data)
    doc=glb_document(data)
    extensions=set(doc.get('extensionsUsed',[])) | set(doc.get('extensionsRequired',[]))
    if 'KHR_texture_basisu' in extensions:
        raise RuntimeError('KTX2/BasisU textures require a texture decoder; refusing missing textures')
    if 'CESIUM_RTC' in doc.get('extensions',{}):
        raise RuntimeError('Legacy CESIUM_RTC extension is not supported by this offline exporter')
    for obj in doc.get('images',[])+doc.get('buffers',[]):
        if 'uri' in obj and not obj['uri'].startswith('data:'):
            raise RuntimeError('External glTF texture/buffer: snapshot is not self-contained; conversion halted')
    decoder=None
    if extensions & GEOMETRY_EXTENSIONS:
        data,decoder=decode_geometry(data,extensions & GEOMETRY_EXTENSIONS)
        remaining=set(glb_document(data).get('extensionsUsed',[]))
        if remaining & (GEOMETRY_EXTENSIONS | {'KHR_texture_basisu'}):
            raise ValueError('Decoder did not remove unsupported compression')
    scene=trimesh.load_scene(io.BytesIO(data),file_type='glb',process=False)
    t=np.eye(4);t[:3,3]=rtc
    final=frame.ecef_to_enu@transform@t@GLTF_TO_ZUP
    out=trimesh.Scene();count=0
    for node in scene.graph.nodes_geometry:
        node_transform,geom_name=scene.graph[node]
        mesh=scene.geometry[geom_name].copy()
        if not isinstance(mesh,trimesh.Trimesh): raise RuntimeError('Non-triangle glTF primitive unsupported')
        mesh.apply_transform(final@node_transform)
        if not np.isfinite(mesh.vertices).all(): raise RuntimeError('Non-finite mesh')
        mesh.metadata.update(source_tile=name,batch_metadata=batch,height_reference='ellipsoid',role='visual_only',geometry_decoder=decoder)
        out.add_geometry(mesh,node_name=f'{name}_{count}',geom_name=f'{name}_{count}');count+=1
    if not count: raise RuntimeError('No decoded mesh primitives; refusing empty export')
    return out


def collect_buildings(store,url,frame:Frame,area:Area):
    """Return only the selected REPLACE frontier, not parent+child duplicates."""
    records=[]
    visited=0
    def visit(tile,base,parent,refine,stack,depth):
        nonlocal visited
        visited+=1
        if visited>100000: raise RuntimeError('Tileset traversal exceeds node budget')
        if depth>40: raise RuntimeError('Tileset nesting exceeds 40 levels')
        transform=parent@matrix(tile.get('transform'))
        if not intersects(tile.get('boundingVolume',{}),transform,frame,area): return []
        if 'implicitTiling' in tile or '3DTILES_implicit_tiling' in tile.get('extensions',{}):
            raise RuntimeError('Implicit tiling is not supported by the offline exporter; use live Cesium viewer')
        mode=tile.get('refine',refine)
        if mode not in {'ADD','REPLACE'}: raise ValueError('Invalid refine mode')
        child_records=[]
        for child in tile.get('children',[]):
            child_records.extend(visit(child,base,transform,mode,stack,depth+1))
        contents=tile.get('contents',[])
        if tile.get('content'): contents=[tile['content']]+contents
        own=[]
        if not child_records or mode=='ADD':
            for content in contents:
                uri=content.get('uri',content.get('url'))
                if not uri: raise ValueError('Missing tile content URI')
                resource=urljoin(base,uri)
                data,rec=store.fetch(resource,'building_content')
                if data.lstrip()[:1]==b'{':
                    if resource in stack: raise ValueError('Cyclic external tileset')
                    doc=json.loads(data)
                    if doc.get('asset',{}).get('gltfUpAxis','Y')!='Y':
                        raise RuntimeError('Nonstandard glTF axis is unsupported')
                    if 'root' not in doc: raise ValueError('Expected external tileset JSON')
                    own.extend(visit(doc['root'],resource,transform,mode,stack+(resource,),depth+1))
                elif data[:4] in (b'b3dm',b'glTF'):
                    own.append({'path':rec['path'],'url':resource,'sha256':rec['sha256'],
                                'transform_column_major':transform.flatten(order='F').tolist()})
                else:
                    raise RuntimeError('Unsupported tile encoding: expected GLB or b3dm')
        return own+child_records
    doc,_=store.json(url,'building_tileset')
    if doc.get('asset',{}).get('gltfUpAxis','Y')!='Y': raise RuntimeError('Unsupported glTF up axis')
    records=visit(doc['root'],url,np.eye(4),'REPLACE',(url,),0)
    if not records: raise RuntimeError('No building tiles intersect requested AOI; no synthetic fallback')
    return records
