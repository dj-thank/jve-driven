"""Explicit geodetic/ENU conversions. All heights here MUST be ellipsoidal metres."""
from __future__ import annotations
from dataclasses import dataclass
import math
import numpy as np
from pyproj import Transformer

GLTF_TO_ZUP = np.array([[1,0,0,0],[0,0,-1,0],[0,1,0,0],[0,0,0,1]], float)
ENU_TO_GLTF = GLTF_TO_ZUP.T

@dataclass(frozen=True)
class Area:
    west: float
    south: float
    east: float
    north: float

    def __post_init__(self):
        if not all(math.isfinite(v) for v in (self.west,self.south,self.east,self.north)):
            raise ValueError('Non-finite bounds')
        if not -180 <= self.west < self.east <= 180 or not -85 < self.south < self.north < 85:
            raise ValueError('Invalid bounds; antimeridian regions are not supported')
        if self.east-self.west > .1 or self.north-self.south > .1:
            raise ValueError('AOI must be <=0.1 degrees per axis; use separate jobs for large cities')

    @property
    def values(self): return [self.west,self.south,self.east,self.north]

    def intersects_region(self, region):
        west,south,east,north = np.degrees(np.asarray(region[:4],float))
        if east < west:
            raise ValueError('Antimeridian tile region is unsupported')
        return east >= self.west and west <= self.east and north >= self.south and south <= self.north

@dataclass(frozen=True)
class Frame:
    longitude: float
    latitude: float
    ellipsoid_height_m: float = 0.0

    def __post_init__(self):
        if not all(math.isfinite(v) for v in (self.longitude,self.latitude,self.ellipsoid_height_m)):
            raise ValueError('Invalid origin')
        if not -180 <= self.longitude <=180 or not -90 <= self.latitude <=90:
            raise ValueError('Origin outside geographic range')

    @property
    def ecef_to_enu(self):
        lon,lat=math.radians(self.longitude),math.radians(self.latitude)
        sl,cl,sf,cf=math.sin(lon),math.cos(lon),math.sin(lat),math.cos(lat)
        r=np.array([[-sl,cl,0],[-sf*cl,-sf*sl,cf],[cf*cl,cf*sl,sf]])
        origin=np.array(Transformer.from_crs(4979,4978,always_xy=True).transform(self.longitude,self.latitude,self.ellipsoid_height_m))
        t=np.eye(4);t[:3,:3]=r;t[:3,3]=-r@origin
        return t

    def points(self, longitudes, latitudes, ellipsoid_heights):
        x,y,z=Transformer.from_crs(4979,4978,always_xy=True).transform(longitudes,latitudes,ellipsoid_heights)
        a=np.column_stack([np.atleast_1d(x),np.atleast_1d(y),np.atleast_1d(z)])
        t=self.ecef_to_enu
        return a@t[:3,:3].T+t[:3,3]

    def as_dict(self):
        return dict(longitude=self.longitude,latitude=self.latitude,
                    ellipsoid_height_m=self.ellipsoid_height_m,
                    axes='ENU: x=east,y=north,z=up',units='metres',height_reference='ellipsoid',
                    ecef_to_enu_column_major=self.ecef_to_enu.flatten(order='F').tolist())


def xyz_pixel(lon,lat,z):
    n=256*2**z
    lat=np.clip(np.asarray(lat,float),-85.05112878,85.05112878)
    return (np.asarray(lon,float)+180)/360*n,(1-np.arcsinh(np.tan(np.radians(lat)))/np.pi)/2*n


def xyz_tiles(area:Area,z:int):
    if not 0<=z<=20: raise ValueError('Unsupported image zoom')
    x0,y1=xyz_pixel(area.west,area.south,z);x1,y0=xyz_pixel(area.east,area.north,z)
    return [(z,x,y) for y in range(int(y0//256),int(np.nextafter(y1,-np.inf)//256)+1)
            for x in range(int(x0//256),int(np.nextafter(x1,-np.inf)//256)+1)]


def geodetic_tiles(area:Area,z:int):
    """Cesium quantized-mesh uses geographic TMS, NOT Web Mercator XYZ."""
    if not 0<=z<=20: raise ValueError('Unsupported terrain zoom')
    nx,ny=2**(z+1),2**z
    x0=int((area.west+180)/360*nx);x1=int(np.nextafter((area.east+180)/360*nx,-np.inf))
    y0=int((area.south+90)/180*ny);y1=int(np.nextafter((area.north+90)/180*ny,-np.inf))
    return [(z,x,y) for y in range(y0,y1+1) for x in range(x0,x1+1)]


def geodetic_bounds(z,x,y):
    nx,ny=2**(z+1),2**z
    if not (0<=x<nx and 0<=y<ny): raise ValueError('Terrain tile out of range')
    return [-180+360*x/nx,-90+180*y/ny,-180+360*(x+1)/nx,-90+180*(y+1)/ny]
