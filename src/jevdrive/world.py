"""OSM to metric scene / GLB. Geographic facts and visual assumptions stay separate."""
from __future__ import annotations
import hashlib
import json
import math
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any
import numpy as np
from pyproj import CRS, Transformer
from shapely.geometry import LineString, Polygon, box
from shapely.geometry.polygon import orient
from shapely.ops import triangulate, unary_union
import trimesh

ROAD_TYPES = {'residential', 'living_street', 'service', 'unclassified', 'tertiary',
              'secondary', 'primary', 'trunk', 'motorway', 'track', 'tertiary_link',
              'secondary_link', 'primary_link', 'motorway_link', 'trunk_link'}
DEFAULT_PROJ = '+proj=tmerc +lat_0=48.135650 +lon_0=10.070100 +k=1 +x_0=0 +y_0=0 +datum=WGS84 +units=m +no_defs'


def number(value: str | None) -> float | None:
    if value is None:
        return None
    match = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*(m|ft|\')?\s*', value)
    if not match:
        return None
    n = float(match.group(1))
    return n * (0.3048 if match.group(2) in {'ft', "'"} else 1.0)


def speed_mps(value: str | None) -> float | None:
    if value is None:
        return None
    match = re.fullmatch(r'\s*(\d+(?:\.\d+)?)\s*(mph|km/h)?\s*', value)
    if not match:
        return None
    return float(match.group(1)) * (0.44704 if match.group(2) == 'mph' else 1/3.6)


def parse_osm(path: Path, projection: str = DEFAULT_PROJ) -> dict[str, Any]:
    content = path.read_bytes()
    if len(content) > 64_000_000 or b'<!DOCTYPE' in content.upper() or b'<!ENTITY' in content.upper():
        raise ValueError('OSM must be <=64 MB with no DTD/entity declarations')
    root = ET.fromstring(content)
    if root.tag != 'osm':
        raise ValueError('Not an OSM XML document')
    projection_crs = CRS.from_user_input(projection)
    transform = Transformer.from_crs('EPSG:4326', projection_crs, always_xy=True)
    nodes: dict[str, tuple[float, float]] = {}
    for n in root.findall('node'):
        lon, lat = float(n.attrib['lon']), float(n.attrib['lat'])
        if not (-180 <= lon <= 180 and -90 <= lat <= 90):
            raise ValueError('Invalid geographic coordinate')
        nodes[n.attrib['id']] = transform.transform(lon, lat)
    roads, buildings, skipped = [], [], []
    for way in root.findall('way'):
        tags = {t.attrib['k']: t.attrib['v'] for t in way.findall('tag')}
        road = tags.get('highway') in ROAD_TYPES
        building = tags.get('building') not in {None, 'no'}
        if not (road or building):
            continue
        refs = [n.attrib['ref'] for n in way.findall('nd')]
        if any(ref not in nodes for ref in refs):
            raise ValueError(f'Incomplete nodes for way {way.attrib["id"]}')
        if len(refs) < (4 if building else 2):
            skipped.append({'way_id': way.attrib['id'], 'reason': 'insufficient vertices'})
            continue
        points = [list(nodes[ref]) for ref in refs]
        obj: dict[str, Any] = {'osm_id': way.attrib['id'], 'points': points, 'node_ids': refs}
        if road:
            if tags.get('area') == 'yes':
                skipped.append({'way_id': way.attrib['id'], 'reason': 'area road not a centerline'})
                continue
            width = number(tags.get('width'))
            if width is not None and not 0.5 <= width <= 50:
                raise ValueError('Implausible explicit road width')
            obj.update(name=tags.get('name', 'Unnamed track'), highway=tags['highway'],
                       width_m=width if width is not None else (3.0 if tags['highway'] == 'track' else 6.0),
                       width_source='osm:width' if width is not None else 'assumed_not_surveyed',
                       maxspeed_mps=speed_mps(tags.get('maxspeed')) or 30/3.6,
                       maxspeed_source='osm:maxspeed' if speed_mps(tags.get('maxspeed')) else 'assumed_30_kmh',
                       oneway=tags.get('oneway', 'no'), length_m=LineString(points).length)
            roads.append(obj)
        if building:
            if refs[0] != refs[-1]:
                raise ValueError('Unclosed building footprint; no invented closing segment allowed')
            poly = Polygon(points)
            if not poly.is_valid or poly.area <= 0:
                raise ValueError(f'Invalid building footprint {way.attrib["id"]}; manual QA required')
            height = number(tags.get('height'))
            levels = number(tags.get('building:levels'))
            height_source = 'osm:height' if height else 'levels_times_assumed_3m' if levels else 'assumed_6m'
            height = height or (levels*3 if levels else 6)
            if not 1 <= height <= 500:
                raise ValueError('Invalid building height')
            obj.update(height_m=height, height_source=height_source,
                       footprint_source='osm_way', area_m2=poly.area,
                       appearance_source='procedural_not_photogrammetry')
            buildings.append(obj)
    if not roads:
        raise ValueError('No complete supported road ways')
    all_pts = np.array([p for obj in roads+buildings for p in obj['points']], dtype=float)
    if not np.isfinite(all_pts).all():
        raise ValueError('Projection produced non-finite coordinates')
    if any(r.find("tag[@k='building']") is not None for r in root.findall('relation')):
        raise ValueError('Building multipolygons require a relation-aware importer; do not silently omit')
    return {
        'schema':'jevdrive.world.v1', 'name':('Kirchberg an der Iller / real-data subset' if path.name=='kirchberg_subset.osm' else f'OSM / {path.stem}'),
        'projection':projection, 'axes':'x=east,y=north,z=up; metres; local transverse Mercator',
        'source_snapshot_utc':root.attrib.get('timestamp','unknown'),
        'input_sha256':hashlib.sha256(content).hexdigest(),
        'bounds':[float(all_pts[:,0].min()-15),float(all_pts[:,1].min()-15),
                  float(all_pts[:,0].max()+15),float(all_pts[:,1].max()+15)],
        'roads':roads, 'buildings':buildings, 'skipped_ways':skipped,
        'assumptions':{
            'terrain':'flat_z0; no surveyed elevation data included',
            'lane_topology':'not inferred as ground truth; centerlines only',
            'road_width':'OSM width where present; otherwise 6m / track 3m',
            'facades_roofs_windows':'procedural; not exact real appearances',
            'signals_pedestrians_obstacles':'scenario objects, not real map measurements',
            'subset':f'{len(roads)} selected road ways and {len(buildings)} buildings; coverage is not guaranteed complete'},
        'attribution':'© OpenStreetMap contributors', 'data_license':'ODbL-1.0'}


def polygons(geom):
    if isinstance(geom, Polygon):
        yield geom
    elif hasattr(geom, 'geoms'):
        for part in geom.geoms:
            yield from polygons(part)


def prism(poly: Polygon, z: float, height: float, color: list[int]) -> trimesh.Trimesh:
    """Extrude a polygon with holes, without an optional triangulation dependency."""
    poly = orient(poly, sign=1.0)
    verts, faces = [], []
    def add_triangle(points):
        idx = len(verts)
        verts.extend(points)
        faces.append([idx,idx+1,idx+2])
    for tri in triangulate(poly):
        if not poly.covers(tri):
            continue
        coords = list(orient(tri, sign=1).exterior.coords)[:3]
        add_triangle([(x,y,z+height) for x,y in coords])
        add_triangle([(x,y,z) for x,y in reversed(coords)])
    for ring in [poly.exterior, *poly.interiors]:
        coords = list(ring.coords)
        for (ax,ay),(bx,by) in zip(coords,coords[1:]):
            add_triangle([(ax,ay,z),(bx,by,z),(bx,by,z+height)])
            add_triangle([(ax,ay,z),(bx,by,z+height),(ax,ay,z+height)])
    mesh = trimesh.Trimesh(vertices=verts, faces=faces, process=True)
    mesh.visual.face_colors = color
    return mesh


def build_scene(world: dict[str, Any]) -> trimesh.Scene:
    scene = trimesh.Scene()
    def add(mesh, name):
        scene.add_geometry(mesh, node_name=name, geom_name=name)
    add(prism(box(*world['bounds']), -0.15, 0.14, [115,135,99,255]), 'assumed_flat_ground')
    roads = unary_union([LineString(r['points']).buffer(r['width_m']/2, cap_style=1, join_style=1)
                         for r in world['roads']])
    for i, p in enumerate(polygons(roads)):
        add(prism(p,0,0.04,[63,68,72,255]), f'osm_road_surface_{i}')
    # No fabricated sidewalks or lane markings are presented as map facts.
    wall_colors = [[210,204,187,255],[205,211,211,255],[212,195,168,255]]
    for i, b in enumerate(world['buildings']):
        poly = orient(Polygon(b['points']), sign=1)
        h = b['height_m']
        add(prism(poly,0.0,h,wall_colors[i%len(wall_colors)]),f'osm_building_{b["osm_id"]}')
        add(prism(poly,h,0.18,[96,74,64,255]),f'assumed_roof_{b["osm_id"]}')
        # Decorative windows are explicitly synthetic, not a reconstruction claim.
        coords = list(poly.exterior.coords)
        for j,(a,c) in enumerate(zip(coords,coords[1:])):
            a,c = np.array(a),np.array(c)
            length = np.linalg.norm(c-a)
            if length < 3:
                continue
            tangent=(c-a)/length
            outward=np.array([tangent[1],-tangent[0]])
            count=max(1,int(length/3.1))
            for level in range(max(1,int(h/3))):
                for w in range(count):
                    center=a+(c-a)*(w+1)/(count+1)+outward*0.035
                    lo=center-tangent*0.5; hi=center+tangent*0.5
                    window=Polygon([lo,hi,hi+outward*.025,lo+outward*.025])
                    add(prism(window,level*3+1.1,1.15,[60,88,103,255]),f'decor_window_{i}_{j}_{level}_{w}')
    scene.metadata.update(world_schema=world['schema'],projection=world['projection'],
                          source_snapshot_utc=world['source_snapshot_utc'],
                          attribution=world['attribution'], disclaimer=world['assumptions'])
    return scene


def export_world(osm: Path, out_dir: Path, projection: str = DEFAULT_PROJ) -> dict[str, Any]:
    out_dir.mkdir(parents=True,exist_ok=True)
    world = parse_osm(osm, projection)
    (out_dir/'world.json').write_text(json.dumps(world,ensure_ascii=False,indent=2),encoding='utf-8')
    scene = build_scene(world)
    # glTF convention is Y-up. Convert ENU(x,y,z) -> glTF(x,z,-y).
    # The Blender importer converts glTF back into Blender Z-up automatically.
    scene.apply_transform(np.array([[1,0,0,0],[0,0,1,0],[0,-1,0,0],[0,0,0,1]],dtype=float))
    glb=scene.export(file_type='glb')
    (out_dir/'kirchberg.glb').write_bytes(glb)
    report={'roads':len(world['roads']),'buildings':len(world['buildings']),
            'road_centerline_m':sum(r['length_m'] for r in world['roads']),
            'glb_bytes':len(glb),'geometry_count':len(scene.geometry),
            'triangles':sum(len(g.faces) for g in scene.geometry.values()),
            'sha256':hashlib.sha256(glb).hexdigest(),
            'runtime_verified':['OSM parsing','metric projection','GLB export'],
            'not_verified':['Blender runtime','Unreal runtime','CARLA map import','real-world geometric accuracy']}
    (out_dir/'BUILD_REPORT.json').write_text(json.dumps(report,indent=2),encoding='utf-8')
    return report


def enu_to_carla(x: float,y: float,z: float=0.0) -> tuple[float,float,float]:
    return x,-y,z


def enu_to_unreal_cm(x: float,y: float,z: float=0.0) -> tuple[float,float,float]:
    return x*100,-y*100,z*100
