"""Opt-in appearance only. Never infer measured trees or change driving gates."""
from __future__ import annotations
import hashlib
import math
from typing import Callable


def authored_tree_layer(plan: dict, route: LineString, height: Callable,
                        *, plan_sha256: str, spacing_m=12.0, offset_m=6.3):
    from shapely.geometry import Point
    if not 8 <= spacing_m <= 30 or not 4 <= offset_m <= 12:
        raise ValueError('Unbounded visual placement parameters')
    if plan.get('driveable') is not False or plan.get('jev_calls') != 0:
        raise ValueError('Appearance layer only accepts visual inspection plans')
    if len(plan_sha256) != 64 or route.length < 1:
        raise ValueError('Missing input identity or route')
    start = route.project(Point(plan['frames'][0]['xyz'][:2]))
    end = route.project(Point(plan['frames'][-1]['xyz'][:2]))
    if end < start:
        raise ValueError('Reversed inspection direction')
    records, rejected = [], []
    s = max(1., start - spacing_m)
    while s <= min(route.length - 1, end + 48):
        p = route.interpolate(s)
        a = route.interpolate(max(0, s - .5))
        b = route.interpolate(min(route.length, s + .5))
        yaw = math.atan2(b.y - a.y, b.x - a.x)
        for side in (-1, 1):
            x = p.x - math.sin(yaw) * offset_m * side
            y = p.y + math.cos(yaw) * offset_m * side
            try:
                z = float(height(x, y))
                if not math.isfinite(z):
                    raise ValueError('Non-finite surface')
            except ValueError:
                rejected.append({'xyz_query': [x, y], 'reason': 'no_unambiguous_surface'})
                continue
            identifier = f'authored-{len(records):03d}'
            rotation = int(hashlib.sha256(identifier.encode()).hexdigest()[:8], 16) % 360
            records.append({'id': identifier, 'xyz': [x, y, z],
                            'rotation_degrees': rotation, 'height_m': 6.5,
                            'osm_node_id': None, 'placement_source': 'AUTHORED_NOT_SURVEYED',
                            'shape_source': 'Poly Haven tree_small_02',
                            'species_verified': False, 'height_verified': False})
        s += spacing_m
    if not records or len(records) > 100:
        raise ValueError('No usable or too many visual tree placements')
    return {'schema': 'jevdrive.visual-tree-layer.v1', 'plan_sha256': plan_sha256,
            'source_glb_sha256': plan['source_glb_sha256'], 'trees': records,
            'rejected': rejected, 'spacing_m': spacing_m, 'offset_m': offset_m,
            'placement_source': 'AUTHORED_NOT_SURVEYED', 'driveable': False,
            'traffic_actor': False, 'changes_source_geometry': False,
            'notice': 'Optional scenery only. Not evidence of actual local tree positions/species.'}


def validate_tree_layer(layer: dict, plan: dict, plan_sha256: str):
    if (layer.get('schema') != 'jevdrive.visual-tree-layer.v1' or
            layer.get('plan_sha256') != plan_sha256 or
            layer.get('source_glb_sha256') != plan['source_glb_sha256']):
        raise ValueError('Appearance layer input identity mismatch')
    if layer.get('driveable') is not False or layer.get('traffic_actor') is not False:
        raise ValueError('Appearance is not a driving/traffic layer')
    if layer.get('placement_source') != 'AUTHORED_NOT_SURVEYED':
        raise ValueError('Authored appearance cannot claim measured placement')
    records = layer.get('trees', [])
    if not 1 <= len(records) <= 100:
        raise ValueError('Invalid placement count')
    seen = set()
    for item in records:
        if (not isinstance(item.get('id'), str) or item['id'] in seen or
                item.get('osm_node_id') is not None or
                item.get('placement_source') != 'AUTHORED_NOT_SURVEYED'):
            raise ValueError('Invalid or falsely attributed tree identity')
        values = item.get('xyz', [])
        if len(values) != 3 or not all(type(x) in (int, float) and math.isfinite(x) for x in values):
            raise ValueError('Invalid tree coordinates')
        if not 2 <= item.get('height_m', 0) <= 12 or not 0 <= item.get('rotation_degrees', -1) < 360:
            raise ValueError('Invalid tree size or rotation')
        seen.add(item['id'])
    return records
