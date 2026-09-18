"""Download -> datum-aligned visual GLB. Does not certify a driveable road map."""
from __future__ import annotations
import io,json,re
from pathlib import Path
from datetime import datetime,timezone
from urllib.parse import urljoin
import xml.etree.ElementTree as ET
import numpy as np
from PIL import Image
import trimesh
from .download import DownloadStore,verify_lock,sha256
from .geo import Area,Frame,ENU_TO_GLTF,geodetic_tiles,xyz_tiles,xyz_pixel
from .tiles3d import collect_buildings,load_geometry,matrix
from .terrain import decode_quantized_mesh
from .integrity import seal_sources,verify_sources

REQUIRED_GATES=('lane_topology','road_surface_collision','traffic_controls','coordinate_alignment',
                'sensor_calibration','independent_geometric_validation')
ATTRIBUTION='建物・航空写真: 国土交通省 Project PLATEAU / 地形: PLATEAU | Mapterhorn | 国土地理院 / 道路中心線: © OpenStreetMap contributors'


def require_driveable(manifest):
    if manifest.get('schema')!='jevdrive.public-world.v1': raise ValueError('Not a public-world manifest')
    missing=[g for g in REQUIRED_GATES if manifest.get('acceptance',{}).get(g)!='verified']
    if manifest.get('stage')!='built' or missing:
        raise RuntimeError('Visual-only map: driving disabled; missing '+', '.join(missing))
    raise RuntimeError('Public-world driving adapter is not implemented; this build is visual-only')


def read_config(path):
    c=json.loads(Path(path).read_text(encoding='utf8'))
    if c.get('schema')!='jevdrive.public-world-config.v1': raise ValueError('Unsupported config')
    area=Area(*c['bounds_wgs84']);frame=Frame(**c['origin'])
    if not re.fullmatch(r'\d{5}-bldg-lod[1234]-texture-(latest|20\d{2})',c['building_spec']):
        raise ValueError('Choose an explicit building LOD and require textures')
    if c.get('surface_role')!='visual_only': raise ValueError('Only visual-only builds are supported')
    if not 10<=c['imagery_zoom']<=19 or not 0<=c['terrain_zoom']<=17:
        raise ValueError('Zoom outside supported limits')
    if not (area.west<=frame.longitude<=area.east and area.south<=frame.latitude<=area.north):
        raise ValueError('Origin must be inside AOI')
    return c,area,frame


def centerlines_from_osm(data):
    """Preserve original tags. Missing widths, signals, lanes remain unknown."""
    if len(data)>64_000_000 or b'<!DOCTYPE' in data.upper() or b'<!ENTITY' in data.upper():
        raise ValueError('Oversized or unsafe OSM XML')
    root=ET.fromstring(data)
    if root.tag!='osm': raise ValueError('Expected OSM XML')
    nodes={}
    for n in root.findall('node'):
        lon,lat=float(n.attrib['lon']),float(n.attrib['lat'])
        if not -180<=lon<=180 or not -90<=lat<=90: raise ValueError('Bad OSM coordinates')
        nodes[n.attrib['id']]=[lon,lat]
    features=[]
    for way in root.findall('way'):
        tags={t.attrib['k']:t.attrib['v'] for t in way.findall('tag')}
        if 'highway' not in tags or tags.get('area')=='yes': continue
        refs=[n.attrib['ref'] for n in way.findall('nd')]
        if len(refs)<2 or any(n not in nodes for n in refs): raise ValueError('Incomplete OSM road geometry')
        features.append({'type':'Feature','id':way.attrib['id'],'properties':{
            'osm_tags':tags,'kind':'centerline_not_lane','elevation':None,
            'width_m':None,'lane_geometry':None,'driveable':False,
            'note':'OSM tags retained verbatim; no width or lane defaults inferred'},
            'geometry':{'type':'LineString','coordinates':[nodes[n] for n in refs]}})
    return {'type':'FeatureCollection','features':features,
            'attribution':'© OpenStreetMap contributors','license':'ODbL-1.0',
            'note':'Centerlines only; not a surveyed HD map; relations/turn restrictions are not converted'}


def fetch_snapshot(config_path:Path,out:Path,client=None,*,resume=False):
    c,area,frame=read_config(config_path)
    out=Path(out)
    if out.exists() and any(out.iterdir()):
        if not resume: raise ValueError('Output must be a new/empty directory (or explicitly --resume)')
        previous=json.loads((out/'public-world.json').read_text(encoding='utf8'))
        if previous.get('config')!=c: raise ValueError('Resume config differs from original snapshot')
        if previous.get('stage') not in ('failed','fetching'):
            raise ValueError('Only failed/in-progress downloads may be resumed')
        verify_lock(out)
    out.mkdir(parents=True,exist_ok=True)
    manifest={'schema':'jevdrive.public-world.v1','name':c['name'],'stage':'fetching',
              'created_utc':datetime.now(timezone.utc).isoformat(),'config':c,
              'frame':frame.as_dict(),'attribution':ATTRIBUTION,
              'appearance':'source_textures_no_generated_facades','surface_role':'visual_only',
              'capture_dates_verified':False,'license_review':'dataset_specific_review_required_before_redistribution',
              'acceptance':{g:'not_verified' for g in REQUIRED_GATES}}
    def save():
        (out/'public-world.json').write_text(json.dumps(manifest,indent=2,ensure_ascii=False),encoding='utf8')
    save()
    store=DownloadStore(out,c['max_download_bytes'],c['max_download_files'],client=client,resume=resume)
    try:
        root_url='https://api.plateauview.mlit.go.jp/datacatalog/3dtiles/'+c['building_spec']+'/tileset.json'
        manifest['building_tiles']=collect_buildings(store,root_url,frame,area)
        layer,rec=store.json(urljoin(c['terrain_base'],'layer.json'),'terrain_layer')
        if layer.get('format') not in ('quantized-mesh-1.0',): raise ValueError('Unsupported terrain format')
        if layer.get('projection','EPSG:4326')!='EPSG:4326' or layer.get('scheme','tms')!='tms':
            raise ValueError('Terrain must use geographic TMS, not XYZ')
        z=c['terrain_zoom']
        if z>layer.get('maxzoom',z): raise ValueError('Requested terrain zoom unavailable')
        template=layer.get('tiles',[None])[0]
        if not template: raise ValueError('Missing terrain tile template')
        terrain_records=[];all_lon=[];all_lat=[]
        for tz,x,y in geodetic_tiles(area,z):
            uri=template.format(z=tz,x=x,y=y,version=layer.get('version','1.0.0'))
            data,r=store.fetch(urljoin(c['terrain_base'],uri),'terrain')
            lon,lat,h,faces=decode_quantized_mesh(data,tz,x,y)
            # Retain the original mesh; include one triangle fringe at the AOI edge.
            coords=np.stack([lon[faces],lat[faces]],axis=2)
            lo=coords.min(axis=1);hi=coords.max(axis=1)
            keep=(hi[:,0]>=area.west)&(lo[:,0]<=area.east)&(hi[:,1]>=area.south)&(lo[:,1]<=area.north)
            if not keep.any(): continue
            indices=np.unique(faces[keep])
            all_lon.extend(lon[indices]);all_lat.extend(lat[indices])
            terrain_records.append({'path':r['path'],'z':tz,'x':x,'y':y,'sha256':r['sha256']})
        if not terrain_records: raise RuntimeError('No terrain available; no flat-ground fallback')
        manifest['terrain_tiles']=terrain_records
        imagery_area=Area(min(all_lon),min(all_lat),max(all_lon),max(all_lat))
        tile_ids=xyz_tiles(imagery_area,c['imagery_zoom'])
        if len(tile_ids)>300: raise RuntimeError('Imagery needs >300 tiles; reduce AOI or image zoom')
        images=[]
        for z,x,y in tile_ids:
            url=c['imagery_template'].format(z=z,x=x,y=y)
            data,r=store.fetch(url,'orthophoto')
            im=Image.open(io.BytesIO(data));im.load()
            if im.size!=(256,256): raise ValueError('Expected 256px orthophoto tiles')
            a=np.asarray(im.convert('RGBA'))[:,:,3]
            if np.any(a!=255): raise RuntimeError('Missing/transparent orthophoto pixels; no fabricated fill')
            images.append({'path':r['path'],'z':z,'x':x,'y':y,'sha256':r['sha256']})
        manifest['imagery_tiles']=images
        manifest['terrain_source_attribution']=layer.get('attribution')
        if c.get('include_osm_centerlines'):
            url='https://api.openstreetmap.org/api/0.6/map?bbox='+','.join(map(str,area.values))
            data,r=store.fetch(url,'osm_centerlines')
            roads=centerlines_from_osm(data)
            (out/'roads-centerlines.geojson').write_text(json.dumps(roads,ensure_ascii=False,indent=2),encoding='utf8')
            manifest['roads_source_sha256']=r['sha256']
            manifest['road_way_count']=len(roads['features'])
        manifest['stage']='fetched'
        manifest['download_bytes']=store.used
        manifest['download_resources']=len(store.records)
        store.save()
        save()
        seal_sources(out,manifest)
        return manifest
    except Exception as exc:
        manifest['stage']='failed'
        manifest['error']=str(exc)
        save()
        raise
    finally:
        store.save();store.close()


def build_snapshot(root:Path):
    root=Path(root)
    verified=verify_lock(root)
    meta=json.loads((root/'public-world.json').read_text(encoding='utf8'))
    if meta.get('schema')!='jevdrive.public-world.v1' or meta.get('stage') not in ('fetched','built'):
        raise ValueError('Snapshot is incomplete; cannot build')
    verify_sources(root,meta)
    # Every mesh-reference must correspond to a verified lock record.
    lock=json.loads((root/'download-lock.json').read_text(encoding='utf8'))
    by_path={r['path']:r for r in lock['resources']}
    for key in ('building_tiles','terrain_tiles','imagery_tiles'):
        if not meta.get(key): raise ValueError(f'Missing {key}')
        for r in meta[key]:
            if r['path'] not in by_path or r['sha256']!=by_path[r['path']]['sha256']:
                raise ValueError('Manifest asset not covered by download lock')
    c=meta['config'];area=Area(*c['bounds_wgs84']);frame=Frame(**c['origin'])
    scene=trimesh.Scene();building_faces=0;terrain_faces=0
    for i,r in enumerate(meta['building_tiles']):
        part=load_geometry((root/r['path']).read_bytes(),matrix(r['transform_column_major']),frame,f'public_building_tile_{i}')
        for name,geom in part.geometry.items():
            scene.add_geometry(geom,node_name=name,geom_name=name);building_faces+=len(geom.faces)
    imgs=meta['imagery_tiles'];minx=min(r['x'] for r in imgs);maxx=max(r['x'] for r in imgs)
    miny=min(r['y'] for r in imgs);maxy=max(r['y'] for r in imgs)
    expected={(x,y) for x in range(minx,maxx+1) for y in range(miny,maxy+1)}
    if {(r['x'],r['y']) for r in imgs}!=expected: raise ValueError('Incomplete orthophoto mosaic')
    if len({r['z'] for r in imgs})!=1: raise ValueError('Mixed image zoom')
    w,h=(maxx-minx+1)*256,(maxy-miny+1)*256
    if w*h>50_000_000: raise ValueError('Texture mosaic >50MP; split AOI')
    image=Image.new('RGB',(w,h))
    for r in imgs:
        im=Image.open(root/r['path']).convert('RGB')
        image.paste(im,((r['x']-minx)*256,(r['y']-miny)*256))
    image.save(root/'orthophoto-mosaic.jpg',quality=95)
    material=trimesh.visual.material.PBRMaterial(name='Public_orthophoto_baked_lighting',
              baseColorTexture=image,metallicFactor=0.0,roughnessFactor=1.0,doubleSided=False)
    for i,r in enumerate(meta['terrain_tiles']):
        lon,lat,height,faces=decode_quantized_mesh((root/r['path']).read_bytes(),r['z'],r['x'],r['y'])
        coords=np.stack([lon[faces],lat[faces]],axis=2);lo=coords.min(1);hi=coords.max(1)
        keep=(hi[:,0]>=area.west)&(lo[:,0]<=area.east)&(hi[:,1]>=area.south)&(lo[:,1]<=area.north)
        faces=faces[keep]
        if not len(faces): continue
        used,inverse=np.unique(faces,return_inverse=True)
        px,py=xyz_pixel(lon[used],lat[used],imgs[0]['z'])
        uv=np.column_stack([(px-minx*256)/w,1-(py-miny*256)/h])
        if np.any(uv<-.0001) or np.any(uv>1.0001): raise RuntimeError('Terrain vertices outside imagery coverage')
        mesh=trimesh.Trimesh(vertices=frame.points(lon[used],lat[used],height[used]),
                faces=inverse.reshape(-1,3),process=False,
                visual=trimesh.visual.TextureVisuals(uv=uv,material=material))
        mesh.metadata.update(role='visual_terrain_not_road_collision',height_reference='ellipsoid')
        name=f'public_terrain_{i}';scene.add_geometry(mesh,node_name=name,geom_name=name);terrain_faces+=len(mesh.faces)
    if not building_faces or not terrain_faces: raise RuntimeError('Incomplete visual scene')
    scene.metadata.update(public_world=meta['name'],frame=frame.as_dict(),attribution=ATTRIBUTION,
              surface_role='visual_only',not_driveable=True)
    scene.apply_transform(ENU_TO_GLTF)
    glb=scene.export(file_type='glb')
    temporary=root/'visual-world.glb.tmp';temporary.write_bytes(glb);temporary.replace(root/'visual-world.glb')
    meta.update(stage='built',build={'sha256':sha256(glb),'bytes':len(glb),
                'building_triangles':building_faces,'terrain_triangles':terrain_faces,
                'verified_input_resources':verified,'glb_convention':'Y-up, metres',
                'blender_executed':False,'unreal_executed':False,'real_world_accuracy_verified':False})
    (root/'public-world.json').write_text(json.dumps(meta,indent=2,ensure_ascii=False),encoding='utf8')
    return meta['build']
