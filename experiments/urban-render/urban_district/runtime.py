"""Standard-library-only animation math for Blender's bundled Python.

No shapely, trimesh, VTK, model API or network calls are imported here.
The motions are authored visual choreography, not vehicle dynamics.
"""
from __future__ import annotations
import bisect
import math


class RuntimeRoad:
    def __init__(self,anchor):
        pts=anchor['coordinates_enu_m'];dx=pts[-1][0]-pts[0][0];dy=pts[-1][1]-pts[0][1];length=math.hypot(dx,dy)
        if length==0:raise ValueError('Invalid reference endpoints')
        self.origin=pts[0];self.forward=(dx/length,dy/length);self.right=(dy/length,-dx/length)
        self.local=[((p[0]-pts[0][0])*self.right[0]+(p[1]-pts[0][1])*self.right[1],(p[0]-pts[0][0])*self.forward[0]+(p[1]-pts[0][1])*self.forward[1]) for p in pts]
        self.distances=[0.]
        for a,b in zip(self.local,self.local[1:]):
            step=math.dist(a,b)
            if step<=0:raise ValueError('Zero-length reference segment')
            self.distances.append(self.distances[-1]+step)
        self.length=self.distances[-1]
    def xy(self,s):
        if not math.isfinite(s):raise ValueError('Invalid distance')
        i=max(0,min(len(self.local)-2,bisect.bisect_right(self.distances,s)-1))
        q=(s-self.distances[i])/(self.distances[i+1]-self.distances[i]);a,b=self.local[i:i+2]
        return (a[0]+q*(b[0]-a[0]),a[1]+q*(b[1]-a[1]))
    def direction(self,s):
        a,b=self.xy(s-.05),self.xy(s+.05);dx,dy=b[0]-a[0],b[1]-a[1];norm=math.hypot(dx,dy)
        return dx/norm,dy/norm
    def point(self,s,lateral=0.,z=0.):
        x,y=self.xy(s);dx,dy=self.direction(s);return [x+dy*lateral,y-dx*lateral,z]
    def angle(self,s):
        dx,dy=self.direction(s);return math.atan2(-dx,dy)
    def matrix(self,s,lateral=0.,z=0.,yaw=0.):
        x,y,z=self.point(s,lateral,z);a=self.angle(s)+yaw;c,sn=math.cos(a),math.sin(a)
        return [[c,-sn,0.,x],[sn,c,0.,y],[0.,0.,1.,z],[0.,0.,0.,1.]]


def time_state(t,config):
    if not math.isfinite(t) or t<0:raise ValueError('Invalid time')
    u=max(0,min(t-5,5));distance=4*min(t,5)+4*u-.4*u*u
    return {'time_s':t,'ego_s_m':config['camera']['start_s_m']+distance,'speed_mps':max(0,4-.8*max(0,t-5)),
            'main_signal':'green' if t<6 else 'red','pedestrian_signal':'red' if t<7 else 'green',
            'jev_calls':0,'motion_source':'authored_keyframed_choreography','physics_simulated':False}


def instance_transform(instance,t,meta,road=None):
    if not math.isfinite(t) or t<0:raise ValueError('Invalid time')
    road=road or RuntimeRoad(meta['route_anchor']);m=instance.get('motion')
    if not m or m['kind'] in {'signal','ped_signal'}:return instance['matrix']
    kind=m['kind'];s=m['route_s_m'];lat=m['lateral_m'];yaw=0.;z=.02 if kind=='vehicle' else .15
    if kind=='vehicle':
        u=max(0,min(t-4,3));dist=(3*min(t,4)+3*u-.5*u*u) if m.get('lead') else m['speed_mps']*t
        s+=dist;stops=[x-14 for x in meta['config']['cross_streets_s_m'] if x-14>=m['route_s_m']]
        if t>=6 and stops:s=min(s,min(stops))
    elif kind=='walker':s+=m['speed_mps']*t;yaw=m['heading'];z+=.013*math.sin(t*6+len(instance['id']))
    elif kind=='crossing':lat+=max(0,t-m['start_s'])*m['speed_mps'];yaw=-math.pi/2;z=.02 if abs(lat)<3.6 else .15
    else:raise ValueError('Unknown animation kind')
    return road.matrix(s,lat,z,yaw)


def light_state(material,kind,t,config):
    state=time_state(t,config)
    if kind=='signal':
        if material=='signal_green':return 'signal_green' if state['main_signal']=='green' else 'signal_off'
        if material=='signal_red_off':return 'signal_red' if state['main_signal']=='red' else 'signal_off'
    if kind=='ped_signal':
        if material=='signal_red':return 'signal_red' if state['pedestrian_signal']=='red' else 'signal_off'
        if material=='ped_green_off':return 'signal_green' if state['pedestrian_signal']=='green' else 'signal_off'
    return material
