"""Evidence-bound camera inspections. Not a driving or perception controller."""
from __future__ import annotations
import hashlib, json, math
from pathlib import Path
import xml.etree.ElementTree as ET
import numpy as np
from shapely.geometry import LineString, Polygon, Point
from .publicworld.geo import Frame, Area
from .publicworld.terrain import decode_quantized_mesh
from .publicworld.integrity import verify_sources

class TerrainSampler:
    """Barycentric heights on actual triangles; no nearest-vertex fallback."""
    def __init__(self, triangles):
        self.triangles = np.asarray(triangles, dtype=float)
        if (self.triangles.ndim != 3 or self.triangles.shape[1:] != (3,3)
                or not np.isfinite(self.triangles).all()):
            raise ValueError('Invalid terrain triangles')
        self.a = self.triangles[:,0,:2]
        self.b = self.triangles[:,1,:2]-self.a
        self.c = self.triangles[:,2,:2]-self.a
        self.den = self.b[:,0]*self.c[:,1]-self.c[:,0]*self.b[:,1]
        self.valid = np.abs(self.den)>1e-10

    def height(self, x, y):
        if not np.isfinite([x,y]).all(): raise ValueError('Non-finite query')
        q = np.array([x,y])-self.a
        d = np.where(self.valid,self.den,1)
        u = (q[:,0]*self.c[:,1]-self.c[:,0]*q[:,1])/d
        v = (self.b[:,0]*q[:,1]-q[:,0]*self.b[:,1])/d
        hit = self.valid & (u>=-1e-8) & (v>=-1e-8) & (u+v<=1+1e-8)
        if not hit.any(): raise ValueError('Point outside rendered terrain')
        t = self.triangles[hit]
        heights = t[:,0,2]+u[hit]*(t[:,1,2]-t[:,0,2])+v[hit]*(t[:,2,2]-t[:,0,2])
        if np.ptp(heights)>.05: raise ValueError('Ambiguous overlapping terrain')
        return float(np.mean(heights))

def load_terrain(snapshot, meta):
    frame = Frame(**meta['config']['origin'])
    area = Area(*meta['config']['bounds_wgs84']); kept = []
    for r in meta['terrain_tiles']:
        lon,lat,h,faces=decode_quantized_mesh((snapshot/r['path']).read_bytes(),r['z'],r['x'],r['y'])
        xy = np.stack([lon[faces],lat[faces]],axis=2)
        lo=xy.min(1); hi=xy.max(1)
        mask=(hi[:,0]>=area.west)&(lo[:,0]<=area.east)&(hi[:,1]>=area.south)&(lo[:,1]<=area.north)
        kept.extend(frame.points(lon,lat,h)[faces[mask]])
    return TerrainSampler(kept)

def verify_asset_pack(path):
    path=Path(path).resolve()
    meta=json.loads((path/'asset-lock.json').read_text(encoding='utf8'))
    for r in meta['resources']:
        p=(path/r['path']).resolve()
        if not p.is_relative_to(path): raise ValueError('Asset path outside pack')
        data=p.read_bytes()
        if len(data)!=r['bytes'] or hashlib.sha256(data).hexdigest()!=r['sha256']:
            raise ValueError('Asset integrity failure')
    return meta

def clip_directed_route(line, coverage):
    cut=line.intersection(coverage)
    parts=[cut] if isinstance(cut,LineString) else list(getattr(cut,'geoms',[]))
    parts=[p for p in parts if isinstance(p,LineString) and p.length>1]
    if not parts: raise ValueError('No route inside source coverage')
    segment=max(parts,key=lambda p:p.length)
    if line.project(Point(segment.coords[-1])) < line.project(Point(segment.coords[0])):
        segment=LineString(list(segment.coords)[::-1])
    return segment

def build_plan(snapshot, osm_id, *, fps=30, seconds=10, speed=4, camera_height=1.55):
    snapshot=Path(snapshot).resolve()
    if not 1<=fps<=60 or not 1<=seconds<=30 or not 0<speed<=10:
        raise ValueError('Invalid inspection timing')
    if not .5<=camera_height<=3: raise ValueError('Invalid camera height')
    verify_sources(snapshot)
    meta=json.loads((snapshot/'public-world.json').read_text(encoding='utf8'))
    data=(snapshot/'visual-world.glb').read_bytes()
    if hashlib.sha256(data).hexdigest()!=meta['build']['sha256']:
        raise ValueError('GLB mismatch')
    frame=Frame(**meta['config']['origin']); terrain=load_terrain(snapshot,meta)
    roads=json.loads((snapshot/'roads-centerlines.geojson').read_text(encoding='utf8'))
    road=next((f for f in roads['features'] if str(f['id'])==str(osm_id)),None)
    if road is None: raise ValueError('OSM way unavailable')
    tags=road['properties']['osm_tags']
    if tags.get('highway') not in {'residential','tertiary','secondary','primary','service','unclassified','living_street'}:
        raise ValueError('Not a motor-road inspection candidate')
    if tags.get('bridge','no')!='no' or tags.get('tunnel','no')!='no' or tags.get('layer','0')!='0':
        raise ValueError('Terrain cannot represent elevated/underground road surfaces')
    ll=np.asarray(road['geometry']['coordinates'])
    points=frame.points(ll[:,0],ll[:,1],np.zeros(len(ll)))[:,:2]
    line=LineString(points)
    if tags.get('oneway')=='-1': line=LineString(list(line.coords)[::-1])
    w,s,e,n=meta['config']['bounds_wgs84']
    corners=frame.points([w,e,e,w],[s,s,n,n],[0]*4)[:,:2]
    coverage=Polygon(corners).buffer(-25)
    route=clip_directed_route(line,coverage)
    travel=speed*(seconds-1/fps)
    if route.length<travel+20: raise ValueError('Not enough covered route for requested recording')
    start=(route.length-travel)/2
    frames=[]
    for i in range(int(round(seconds*fps))):
        distance=start+speed*i/fps
        p=route.interpolate(distance); ahead=route.interpolate(min(route.length,distance+6))
        if not coverage.covers(p) or not coverage.covers(ahead):
            raise ValueError('Camera/lookahead left coverage')
        z=terrain.height(p.x,p.y); za=terrain.height(ahead.x,ahead.y)
        frames.append({'frame':i+1,'time_s':i/fps,'distance_m':speed*i/fps,
            'xyz':[p.x,p.y,z+camera_height],
            'target':[ahead.x,ahead.y,za+camera_height],
            'terrain_z':z,'clearance_m':camera_height})
    lock=json.loads((snapshot/'download-lock.json').read_text(encoding='utf8'))
    osm=next(r for r in lock['resources'] if r['kind']=='osm_centerlines')
    doc=ET.fromstring((snapshot/osm['path']).read_bytes()); trees=[]
    for node in doc.findall('node'):
        nt={t.attrib['k']:t.attrib['v'] for t in node.findall('tag')}
        if nt.get('natural')!='tree': continue
        x,y,_=frame.points([float(node.attrib['lon'])],[float(node.attrib['lat'])],[0])[0]
        if not coverage.covers(Point(x,y)) or route.distance(Point(x,y))>55: continue
        try: z=terrain.height(x,y)
        except ValueError: continue
        trees.append({'osm_node_id':node.attrib['id'],'xyz':[float(x),float(y),z],
            'position_source':'OSM natural=tree', 'shape_source':'Poly Haven tree_small_02',
            'species_verified':False,'height_verified':False,'original_osm_tags':nt})
    # Keep a bounded number of native mesh instances nearest the actual camera segment.
    camera_line=LineString([f['xyz'][:2] for f in frames])
    trees.sort(key=lambda t:camera_line.distance(Point(t['xyz'][:2])))
    return {'schema':'jevdrive.visual-quality-plan.v1','source_glb_sha256':meta['build']['sha256'],
        'source_lock_sha256':hashlib.sha256((snapshot/'source-lock.json').read_bytes()).hexdigest(),
        'osm_way_id':str(osm_id),'osm_tags':tags,'coverage_inset_m':25,
        'width':1920,'height':1080,'horizontal_fov_degrees':80,'fps':fps,
        'camera_height_m':camera_height,'speed_mps':speed,'frames':frames,'trees':trees[:24],
        'coordinate_system':'ENU metres, ellipsoidal datum','route_kind':'OSM centerline, NOT lane geometry',
        'driveable':False,'jev_calls':0,'physics_simulated':False,
        'fidelity_limits':['not surveyed camera','generic tree shape and size',
            'terrain is not independently surveyed road surface','lighting not local weather'],
        'attribution':meta['attribution']}

def load_detail_road_sampler(details, origin):
    import trimesh
    from .publicworld.geo import GLTF_TO_ZUP
    from .publicworld.download import verify_lock
    details=Path(details).resolve(); verify_lock(details)
    meta=json.loads((details/'details-manifest.json').read_text(encoding='utf8'))
    if meta['frame']!=origin: raise ValueError('Detail source has a different ENU origin')
    if hashlib.sha256((details/'download-lock.json').read_bytes()).hexdigest()!=meta['download_lock_sha256']:
        raise ValueError('Detail source download lock changed')
    if hashlib.sha256((details/'details.glb').read_bytes()).hexdigest()!=meta['glb_sha256']:
        raise ValueError('Detail source GLB changed')
    scene=trimesh.load_scene(details/'details.glb',process=False); triangles=[]
    for node in scene.graph.nodes_geometry:
        transform, name=scene.graph[node]
        if not str(node).startswith('detail_tran_'): continue
        mesh=scene.geometry[name].copy(); mesh.apply_transform(GLTF_TO_ZUP @ transform)
        mask=np.abs(mesh.face_normals[:,2])>.6
        triangles.extend(mesh.triangles[mask])
    if not triangles: raise ValueError('No real LOD3 road surfaces')
    return TerrainSampler(triangles), meta

def apply_detail_surface(plan, details, origin):
    sampler,meta=load_detail_road_sampler(details,origin)
    result=json.loads(json.dumps(plan)); residuals=[]
    for f in result['frames']:
        z=sampler.height(*f['xyz'][:2]); zt=sampler.height(*f['target'][:2])
        residuals.append(z-f['terrain_z']); f['xyz'][2]=z+result['camera_height_m']
        f['target'][2]=zt+result['camera_height_m']; f['surface_z']=z
    result['height_surface']='PLATEAU LOD3 road mesh'
    result['details_glb_sha256']=meta['glb_sha256']
    result['details_manifest_sha256']=hashlib.sha256((Path(details)/'details-manifest.json').read_bytes()).hexdigest()
    result['road_minus_terrain_m']={'min':min(residuals),'max':max(residuals)}
    result['trees']=[]  # Native PLATEAU vegetation, not duplicated generic instances.
    return result
