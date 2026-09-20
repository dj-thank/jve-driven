"""Calibrated ego-camera inspection, not a controller or an HD-map certificate."""
from __future__ import annotations
from dataclasses import dataclass, asdict
import math
import numpy as np
from shapely.geometry import LineString, box
from .publicworld.geo import Frame, Area


@dataclass(frozen=True)
class CameraSpec:
    width: int = 1280
    height: int = 720
    horizontal_fov_deg: float = 80.0
    height_above_surface_m: float = 1.55
    fps: int = 12
    seconds: int = 8
    speed_mps: float = 3.0

    def __post_init__(self):
        for k in ('width', 'height', 'fps', 'seconds'):
            v = getattr(self, k)
            if isinstance(v, bool) or not isinstance(v, int):
                raise ValueError('Camera integer fields must be integers')
        if not (320 <= self.width <= 3840 and 180 <= self.height <= 2160):
            raise ValueError('Camera image size outside limits')
        if self.width % 2 or self.height % 2 or not 1 <= self.fps <= 60 or not 1 <= self.seconds <= 30:
            raise ValueError('Invalid video settings')
        for v in (self.horizontal_fov_deg, self.height_above_surface_m, self.speed_mps):
            if isinstance(v, bool) or not math.isfinite(v):
                raise ValueError('Non-finite camera parameter')
        if not 40 <= self.horizontal_fov_deg <= 110 or not 1 <= self.height_above_surface_m <= 2.5:
            raise ValueError('Invalid lens or camera height')
        if not 0 < self.speed_mps <= 10:
            raise ValueError('Inspection speed outside limits')

    @property
    def intrinsic(self):
        focal = self.width / (2 * math.tan(math.radians(self.horizontal_fov_deg) / 2))
        return [[focal, 0, self.width / 2], [0, focal, self.height / 2], [0, 0, 1]]

    def record(self):
        return {**asdict(self), 'K': self.intrinsic, 'calibration_source': 'configured_virtual_sensor_not_measured_camera',
                'distortion': [0, 0, 0, 0, 0], 'projection': 'pinhole', 'image_origin': 'top_left'}


def camera_to_enu(position, yaw: float, pitch: float = 0.0):
    """Optical x=right,y=down,z=forward; ENU x=east,y=north,z=up."""
    position = np.asarray(position, dtype=float)
    if position.shape != (3,) or not np.isfinite(position).all() or not np.isfinite([yaw, pitch]).all():
        raise ValueError('Invalid camera pose')
    right = np.array([math.sin(yaw), -math.cos(yaw), 0.0])
    forward = np.array([math.cos(pitch)*math.cos(yaw), math.cos(pitch)*math.sin(yaw), math.sin(pitch)])
    up = np.cross(right, forward)
    matrix = np.eye(4)
    matrix[:3, :3] = np.column_stack([right, -up, forward])
    matrix[:3, 3] = position
    return matrix


def sample_heights(triangles, xy):
    """Vertical interpolation on the supplied surface, never fill an absent height."""
    triangles = np.asarray(triangles, dtype=float)
    xy = np.asarray(xy, dtype=float)
    if triangles.ndim != 3 or triangles.shape[1:] != (3, 3) or xy.ndim != 2 or xy.shape[1] != 2:
        raise ValueError('Wrong surface/query shape')
    if not np.isfinite(triangles).all() or not np.isfinite(xy).all():
        raise ValueError('Non-finite surface')
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    v, w = b[:, :2]-a[:, :2], c[:, :2]-a[:, :2]
    den = v[:, 0]*w[:, 1]-v[:, 1]*w[:, 0]
    valid = np.abs(den) > 1e-9
    result = np.full(len(xy), np.nan)
    for i, p in enumerate(xy):
        q = p-a[:, :2]
        u = np.divide(q[:, 0]*w[:, 1]-q[:, 1]*w[:, 0], den, out=np.zeros_like(den), where=valid)
        t = np.divide(v[:, 0]*q[:, 1]-v[:, 1]*q[:, 0], den, out=np.zeros_like(den), where=valid)
        hit = valid & (u >= -1e-7) & (t >= -1e-7) & (u+t <= 1+1e-7)
        heights = a[:, 2] + u*(b[:, 2]-a[:, 2]) + t*(c[:, 2]-a[:, 2])
        if hit.any():
            h = heights[hit]
            if np.ptp(h) > .5:
                raise ValueError('Multiple road levels at a camera point; manual selection required')
            result[i] = np.mean(h)
    return result


def select_camera_path(roads, area: Area, frame: Frame, terrain, spec: CameraSpec, road_surface=None):
    """Inspect an actual centerline segment; never infer lanes or traffic permissions."""
    clip = box(*area.values)
    candidates = []
    allowed = {'primary', 'secondary', 'tertiary', 'residential', 'unclassified', 'service'}
    n = spec.fps * spec.seconds
    desired = spec.speed_mps * (n-1) / spec.fps
    rejected = []
    for feature in roads.get('features', []):
        tags = feature.get('properties', {}).get('osm_tags', {})
        if tags.get('highway') not in allowed or tags.get('tunnel', 'no') != 'no' or tags.get('bridge', 'no') != 'no':
            continue
        coordinates = feature.get('geometry', {}).get('coordinates', [])
        if feature.get('geometry', {}).get('type') != 'LineString' or len(coordinates) < 2:
            continue
        pieces = LineString(coordinates).intersection(clip)
        pieces = list(pieces.geoms) if hasattr(pieces, 'geoms') else [pieces]
        for piece in pieces:
            if piece.geom_type != 'LineString':
                continue
            coords = np.array(piece.coords)
            enu = frame.points(coords[:, 0], coords[:, 1], np.zeros(len(coords)))
            route = LineString(enu[:, :2])
            if route.length < desired + 4:
                continue
            if tags.get('oneway') == '-1':
                route = LineString(list(route.coords)[::-1])
            start = (route.length-desired)/2
            distances = start + np.arange(n)*spec.speed_mps/spec.fps
            points = np.array([route.interpolate(s).coords[0] for s in distances])
            heights = sample_heights(terrain, points)
            role = 'terrain_not_verified_road_surface'
            if not np.isfinite(heights).all():
                rejected.append({'osm_id': feature['id'], 'reason': 'missing_terrain'})
                continue
            if road_surface is not None and len(road_surface):
                rh = sample_heights(road_surface, points)
                if np.isfinite(rh).all() and np.max(np.abs(rh-heights)) < 3:
                    heights = rh; role = 'public_road_mesh_not_topology_certification'
            if np.max(np.abs(np.diff(heights))) > .5:
                rejected.append({'osm_id': feature['id'], 'reason': 'surface_discontinuity'})
                continue
            # Central differences of a one-metre heading probe avoid abrupt yaw flips.
            yaws = []
            for s in distances:
                a = route.interpolate(max(0, s-1)); b = route.interpolate(min(route.length, s+1))
                yaws.append(math.atan2(b.y-a.y, b.x-a.x))
            record = []
            for i, (p, h, yaw) in enumerate(zip(points, heights, yaws)):
                xyz = [float(p[0]), float(p[1]), float(h+spec.height_above_surface_m)]
                pose = camera_to_enu(xyz, yaw, math.radians(-1.5))
                record.append({'frame': i, 'time_s': i/spec.fps, 'position_enu_m': xyz,
                               'surface_height_enu_m': float(h), 'yaw_rad': yaw,
                               'camera_to_enu': pose.tolist(), 'world_to_camera': np.linalg.inv(pose).tolist()})
            candidates.append((route.distance(LineString([(0, 0), (.001, .001)])), str(feature['id']),
                               {'osm_way_id': str(feature['id']), 'osm_tags': tags, 'surface_source': role,
                                'travel_m': desired, 'frames': record, 'path': list(route.coords)}))
    if not candidates:
        raise ValueError('No continuous public-data camera corridor; no synthetic route fallback')
    chosen = sorted(candidates, key=lambda c: (c[0], c[1]))[0][2]
    return {'schema': 'jevdrive.ego-inspection.v1', 'mode': 'camera_inspection_not_driving',
            'camera': spec.record(), 'route': chosen, 'rejected_candidates': rejected,
            'route_source': 'OSM_centerline_not_surveyed_lane', 'controller_executed': False,
            'live_jev_calls': 0, 'live_jev_successes': 0, 'driveable': False,
            'geometric_accuracy_verified': False, 'photorealism_verified': False}
