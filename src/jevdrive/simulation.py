"""CPU-only kinematic smoke simulation on a real OSM polyline.
This is not CARLA physics, a driving benchmark, or a perception evaluation.
"""
from __future__ import annotations
from dataclasses import asdict, replace
import json
import math
from pathlib import Path
import time
from typing import Any
from shapely.geometry import LineString, Point
from .control import Observation, baseline, guarded_control, pure_pursuit
from .jev import DecisionService

SCENARIOS=('clear','red_light','pedestrian','obstacle','occlusion','disconnect','stale_reply','adversarial_fixture')


def simulate(world: dict[str,Any],scenario: str='clear',mode: str='baseline',
             duration: float=40,dt: float=0.05,realtime: bool=False,
             max_calls: int=120) -> dict[str,Any]:
    if scenario not in SCENARIOS:
        raise ValueError('Unknown scenario')
    if mode not in {'baseline','jev-live','jev-shadow'}:
        raise ValueError('Explicitly select baseline, jev-live or jev-shadow')
    if not math.isfinite(duration) or not 0<duration<=600 or not 0<dt<=0.1:
        raise ValueError('Duration must be (0,600], time step (0,0.1]')
    if mode!='baseline' and not realtime:
        raise ValueError('Jev modes require --realtime; do not freeze simulated time around network calls')
    road=next((r for r in world['roads'] if r['osm_id']=='25216931'), None)
    if road is None:
        drive_roads=[r for r in world['roads'] if r['highway']!='track']
        if not drive_roads: raise ValueError('No supported drive route')
        road=max(drive_roads,key=lambda r:r['length_m'])
    # Right-lane geometry is an explicit 1.5m offset assumption, not HD ground truth.
    path=LineString(road['points']).offset_curve(-1.5,join_style=1)
    if path.geom_type!='LineString':
        raise ValueError('Offset route is disconnected')
    p,q=path.interpolate(0),path.interpolate(1)
    x,y=p.x,p.y
    yaw=math.atan2(q.y-p.y,q.x-p.x)
    speed=0.0; acceleration_previous=0.0; last_s=0.0
    service=DecisionService(max_calls=max_calls) if mode!='baseline' else None
    steps=[]
    frames=[]; max_cte=0.0; max_jerk=0.0; collision_proxy=False
    red_line_crossing_proxy=False; max_speed=0.0
    monotonic_start=time.monotonic()
    try:
        for frame in range(round(duration/dt)):
            now=time.monotonic()
            t=frame*dt
            if realtime:
                pause=monotonic_start+t-now
                if pause>0: time.sleep(pause)
                now=time.monotonic()
            s=path.project(Point(x,y))
            cte=path.distance(Point(x,y)); max_cte=max(max_cte,cte)
            signal='RED' if scenario=='red_light' and t<18 else 'NONE'
            signal_distance=max(0.0,65-s-2.2) if signal=='RED' else None
            gap=max(0.0,75-s-2.2) if scenario=='obstacle' and t>=4 else None
            ped=scenario in {'pedestrian','adversarial_fixture'} and 3<=t<12
            occluded=scenario=='occlusion' and 4<=t<14
            obs=Observation(frame,t,speed,road['maxspeed_mps'],max(0.0,path.length-s-2.2),
                            road_id=road['osm_id'],obstacle_gap_m=gap,closing_speed_mps=speed if gap is not None else 0,
                            signal=signal,signal_distance_m=signal_distance,
                            pedestrian_conflict=ped,occluded=occluded,
                            scene_notes='Synthetic crossing pedestrian in route corridor.' if ped else '')
            proposal=baseline(obs,now)
            shadow=None
            if service:
                shadow=service.poll(obs)
                if mode=='jev-live': proposal=shadow
            if scenario=='disconnect' and 4<=t<7:
                proposal=None
            if scenario=='stale_reply' and 4<=t<7 and proposal is not None:
                proposal=replace(proposal,sim_time=max(0,t-2),requested_wall=now-2)
            if scenario=='adversarial_fixture' and ped:
                proposal=replace(baseline(obs,now),action='proceed',probabilities={a:float(a=='proceed') for a in ('proceed','slow','yield','stop')},
                                 yield_noul=0.0,caution_score=0.0,source='test_fixture',model='deliberately_wrong_fixture')
            # Timestamp control after polling: a reply may finish during poll().
            now=time.monotonic()
            control=guarded_control(obs,proposal,now=now)
            target=path.interpolate(min(path.length,s+max(3.5,speed*.65)))
            steer=pure_pursuit(x,y,yaw,target.x,target.y)
            jerk=(control.acceleration_mps2-acceleration_previous)/dt
            max_jerk=max(max_jerk,abs(jerk)); acceleration_previous=control.acceleration_mps2
            if gap is not None and s+2.2>=75:
                collision_proxy=True
            if signal=='RED' and s+2.2>=65:
                red_line_crossing_proxy=True
            if ped and abs(s-55)<3:
                collision_proxy=True
            if frame%2==0:
                frames.append({'frame':frame,'time_s':round(t,3),'x':x,'y':y,'yaw':yaw,'speed_mps':speed,
                               'progress_m':s,'cross_track_error_m':cte,'steer_rad':steer,
                               'target_mps':control.target_speed_mps,'reasons':list(control.reasons),
                               'source':control.proposal_source,'signal':signal,'pedestrian':ped,
                               'obstacle':gap is not None,'occluded':occluded,
                               'proposal_action':proposal.action if proposal else 'none',
                               'proposal_confidence':proposal.confidence if proposal else None,
                               'jev_error':service.last_error if service else None,
                               'shadow_action':shadow.action if shadow else None})
            before=[x,y,yaw,speed]
            counterfactual=guarded_control(obs,baseline(obs,now),now=now)
            new_speed=max(0.0,speed+control.acceleration_mps2*dt)
            mid_speed=(speed+new_speed)/2
            yaw_delta=mid_speed/2.7*math.tan(steer)*dt
            x+=mid_speed*math.cos(yaw+yaw_delta/2)*dt
            y+=mid_speed*math.sin(yaw+yaw_delta/2)*dt
            yaw+=yaw_delta
            speed=new_speed
            steps.append({'frame':frame,'dt':dt,'wall_monotonic':now,
                'wall_elapsed_s':now-monotonic_start,'observation':asdict(obs),
                'proposal':asdict(proposal) if proposal else None,'control':asdict(control),
                'baseline_counterfactual':asdict(counterfactual),'steer_rad':steer,
                'before':before,'after':[x,y,yaw,speed]})
            max_speed=max(max_speed,speed)
            last_s=s
    finally:
        if service: service.close()
    return {'schema':'jevdrive.run.v1','mode':mode,'scenario':scenario,
            'observation_source':'ground_truth_debug',
            'simulator':'CPU kinematic bicycle smoke harness, NOT CARLA',
            'map_source_snapshot':world['source_snapshot_utc'],
            'route_assumption':f"OSM way {road['osm_id']} with assumed 1.5m right offset",
            'route':[list(p) for p in path.coords], 'route_length_m':path.length,
            'frames':frames,'control_trace_schema':'jevdrive.control-trace.v1','steps':steps,
            'metrics':{'max_cross_track_error_m':max_cte,'max_speed_mps':max_speed,
                       'max_jerk_mps3':max_jerk,'route_progress_fraction':last_s/path.length,
                       'collision_proxy':collision_proxy,'red_line_crossing_proxy':red_line_crossing_proxy,
                       'metric_scope':'synthetic/kinematic contract smoke only; not driving-safety evidence'},
            'jev_calls':service.calls if service else 0,
            'jev_evidence':service.evidence if service else [],
            'jevs_real_driving_performance_evaluated':False}


def write_run(run: dict[str,Any],path: Path) -> None:
    path.parent.mkdir(parents=True,exist_ok=True)
    # Atomic replacement makes local viewer polling safe.
    tmp=path.with_suffix('.tmp')
    tmp.write_text(json.dumps(run,ensure_ascii=False),encoding='utf-8')
    tmp.replace(path)
