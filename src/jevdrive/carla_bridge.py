"""Experimental CARLA 0.9.16 / UE4 adapter. CARLA runtime is NOT author-verified.
No dependency on carla until explicit invocation. Never connects to a real vehicle.
The visual GLB is NOT automatically installed into the CARLA world by this module.
"""
from __future__ import annotations
import argparse
import json
import math
from pathlib import Path
import time
from typing import Any
from .world import DEFAULT_PROJ, enu_to_carla, parse_osm
from .control import Observation, baseline, guarded_control
from .jev import DecisionService


def conversion_settings(carla: Any, projection: str):
    if not hasattr(carla,'Osm2OdrSettings') or not hasattr(carla,'Osm2Odr'):
        raise RuntimeError('This CARLA build does not provide the documented Osm2Odr API')
    settings=carla.Osm2OdrSettings()
    for name,value in {'proj_string':projection,'use_offsets':False,'center_map':False,
                       'default_lane_width':3.0,'generate_traffic_lights':True,
                       'all_junctions_with_traffic_lights':False}.items():
        if not hasattr(settings,name):
            raise RuntimeError(f'Incompatible CARLA settings: {name} is unavailable')
        setattr(settings,name,value)
    settings.set_osm_way_types(['residential','living_street','service','unclassified','tertiary',
                                'secondary','primary','trunk','motorway','tertiary_link',
                                'secondary_link','primary_link','trunk_link','motorway_link'])
    return settings


def convert(carla: Any, osm: Path, output: Path, projection: str=DEFAULT_PROJ) -> None:
    if output.exists(): raise FileExistsError(f'{output} already exists; choose another output')
    meta=parse_osm(osm,projection)  # Validate locally before handing XML to native code.
    result=carla.Osm2Odr.convert(osm.read_text(encoding='utf-8'),conversion_settings(carla,projection))
    if not result or '<OpenDRIVE' not in result:
        raise RuntimeError('OSM conversion returned no OpenDRIVE document')
    output.parent.mkdir(parents=True,exist_ok=True)
    output.write_text(result,encoding='utf-8')
    output.with_suffix('.provenance.json').write_text(json.dumps({
        'input_sha256':meta['input_sha256'],'projection':projection,
        'source_snapshot_utc':meta['source_snapshot_utc'],'road_width':'assumed 3m per lane',
        'all_junctions_with_traffic_lights':False,
        'limitations':'Road conversion only. No GLB buildings, exact lane topology or surveyed elevation.'},indent=2))


def _speed(v):
    return math.sqrt(v.x*v.x+v.y*v.y+v.z*v.z)


def observe(world,ego,map_,frame: int,route_remaining: float) -> Observation:
    """Ground-truth debugging only. Corridor heuristic is NOT a perception stack."""
    snap=world.get_snapshot();tr=ego.get_transform();loc=tr.location
    vel=ego.get_velocity();speed=_speed(vel);fwd=tr.get_forward_vector()
    wp=map_.get_waypoint(loc)
    if wp is None: raise RuntimeError('Ego is off the generated road graph')
    gap=None;closing=0.0;ped=False
    for actor in world.get_actors():
        if actor.id==ego.id or not (actor.type_id.startswith('vehicle.') or actor.type_id.startswith('walker.')):
            continue
        other=actor.get_location();dx,dy,dz=other.x-loc.x,other.y-loc.y,other.z-loc.z
        longitudinal=dx*fwd.x+dy*fwd.y
        lateral=abs(-dx*fwd.y+dy*fwd.x)
        if abs(dz)>3 or not 0<longitudinal<70: continue
        if actor.type_id.startswith('walker.') and lateral<4:
            ped=True  # Conservative debug corridor, not trajectory prediction.
        if actor.type_id.startswith('vehicle.') and lateral<2.3:
            candidate=max(0,longitudinal-ego.bounding_box.extent.x-actor.bounding_box.extent.x)
            if gap is None or candidate<gap:
                gap=candidate;other_v=actor.get_velocity()
                closing=max(0,(vel.x-other_v.x)*fwd.x+(vel.y-other_v.y)*fwd.y)
    signal='NONE';signal_distance=None
    light=ego.get_traffic_light() if ego.is_at_traffic_light() else None
    if light is not None:
        raw=str(light.get_state()).split('.')[-1].upper()
        signal=raw if raw in {'RED','GREEN','YELLOW'} else 'UNKNOWN'
        if hasattr(light,'get_stop_waypoints'):
            stops=[s for s in light.get_stop_waypoints() if s.road_id==wp.road_id and s.lane_id==wp.lane_id]
            forward_distances=[]
            for stop in stops:
                p=stop.transform.location
                ahead=(p.x-loc.x)*fwd.x+(p.y-loc.y)*fwd.y
                if ahead>=-1: forward_distances.append(max(0,ahead-ego.bounding_box.extent.x))
            if forward_distances: signal_distance=min(forward_distances)
    limit=ego.get_speed_limit()/3.6
    if not math.isfinite(limit) or limit<=0: limit=30/3.6
    return Observation(frame=frame,sim_time=snap.timestamp.elapsed_seconds,
        speed_mps=speed,speed_limit_mps=min(limit,30/3.6),route_remaining_m=max(0,route_remaining),
        road_id=str(wp.road_id),lane_id=str(wp.lane_id),obstacle_gap_m=gap,closing_speed_mps=closing,
        signal=signal,signal_distance_m=signal_distance,pedestrian_conflict=ped,
        scene_notes='CARLA ground truth, corridor heuristic. No camera perception, no occlusion estimation.',
        source='ground_truth_debug')


def run(carla: Any, args) -> None:
    from shapely.geometry import LineString
    try:
        from agents.navigation.basic_agent import BasicAgent
    except ImportError as exc:
        raise RuntimeError('Add the matching CARLA PythonAPI/carla directory to PYTHONPATH for agents') from exc
    if not args.replace_world:
        raise RuntimeError('This command replaces the simulator world. Pass --replace-world explicitly.')
    service=DecisionService(max_calls=args.max_calls) if args.mode!='baseline' else None
    owned=[];world=None;old_settings=None;collision_events=[];frames=[];completed=False
    try:
        client=carla.Client(args.host,args.port);client.set_timeout(30)
        cv,sv=client.get_client_version(),client.get_server_version()
        if cv!=sv or not cv.startswith('0.9.16'):
            raise RuntimeError(f'Target is matching CARLA 0.9.16 client/server; found client={cv}, server={sv}')
        xodr=args.xodr.read_text(encoding='utf-8')
        world=client.generate_opendrive_world(xodr,carla.OpendriveGenerationParameters(
            vertex_distance=1.0,max_road_length=500.0,wall_height=0.0,additional_width=0.6,
            smooth_junctions=True,enable_mesh_visibility=True))
        old_settings=world.get_settings()
        settings=world.get_settings();settings.synchronous_mode=True;settings.fixed_delta_seconds=.05
        world.apply_settings(settings)
        map_=world.get_map()
        meta=json.loads(args.world.read_text(encoding='utf-8'))
        road=next((r for r in meta['roads'] if r['osm_id']=='25216931'),None)
        if road is None: raise RuntimeError('This pilot route is defined only for the bundled Kirchberg subset')
        route=LineString(road['points']).offset_curve(-1.5)
        route_points=[route.interpolate(2),route.interpolate(max(3,route.length-8))]
        wps=[]
        for point in route_points:
            expected=carla.Location(*enu_to_carla(point.x,point.y,.3))
            wp=map_.get_waypoint(expected,project_to_road=True,lane_type=carla.LaneType.Driving)
            if wp is None or wp.transform.location.distance(expected)>6:
                raise RuntimeError('OSM / OpenDRIVE projection-alignment check failed; do not spawn')
            wps.append(wp)
        spawn=wps[0].transform;spawn.location.z+=.6
        bp=world.get_blueprint_library().find('vehicle.tesla.model3')
        bp.set_attribute('role_name','jevdrive_simulation_only')
        ego=world.try_spawn_actor(bp,spawn)
        if ego is None: raise RuntimeError('Could not spawn ego at the pilot route start')
        owned.append(ego)
        collision_bp=world.get_blueprint_library().find('sensor.other.collision')
        collision_sensor=world.spawn_actor(collision_bp,carla.Transform(),attach_to=ego)
        owned.append(collision_sensor)
        collision_sensor.listen(lambda e:collision_events.append({'frame':e.frame,'other_actor_type':e.other_actor.type_id}))
        agent=BasicAgent(ego,target_speed=30)
        start=ego.get_location();goal=wps[1].transform.location
        plan=agent.trace_route(wps[0],wps[1])
        if len(plan)<2: raise RuntimeError('CARLA could not create a connected pilot route')
        agent.set_global_plan(plan)
        # Arc length on CARLA's actual planned route, not an invented remaining-distance constant.
        drive_line=LineString([(w.transform.location.x,w.transform.location.y) for w,_ in plan])
        wall_start=time.monotonic()
        from shapely.geometry import Point
        for i in range(round(args.seconds/.05)):
            pause=wall_start+i*.05-time.monotonic()
            if pause>0: time.sleep(pause)
            frame=world.tick()
            loc=ego.get_location()
            remaining=max(0,drive_line.length-drive_line.project(Point(loc.x,loc.y))-ego.bounding_box.extent.x)
            obs=observe(world,ego,map_,frame,remaining)
            now=time.monotonic();proposal=baseline(obs,now)
            jev_proposal=service.poll(obs) if service else None
            if args.mode=='jev-live': proposal=jev_proposal
            controlled=guarded_control(obs,proposal,now=now)
            agent.set_target_speed(controlled.target_speed_mps*3.6)
            command=agent.run_step()
            if controlled.target_speed_mps<.1 or 'emergency_brake_request' in controlled.reasons:
                command.throttle=0.0;command.brake=1.0
            ego.apply_control(command)
            frames.append({'frame':frame,'sim_time':obs.sim_time,'speed_mps':obs.speed_mps,
                           'target_mps':controlled.target_speed_mps,'reasons':controlled.reasons,
                           'proposal_source':controlled.proposal_source,
                           'shadow_action':jev_proposal.action if jev_proposal else None,
                           'jev_error':service.last_error if service else None})
            if agent.done() and obs.speed_mps<.1: break
        completed=True
    finally:
        if service: service.close()
        for actor in reversed(owned):
            try:
                if hasattr(actor,'stop'): actor.stop()
                actor.destroy()
            except RuntimeError: pass
        if world is not None and old_settings is not None:
            world.apply_settings(old_settings)
        # A partial log is retained on failure; it is never labeled as a successful run.
        args.out.parent.mkdir(parents=True,exist_ok=True)
        args.out.write_text(json.dumps({'schema':'jevdrive.carla_debug_run.v1','mode':args.mode,'completed_without_exception':completed,
            'observation_source':'ground_truth_debug','frames':frames,'collisions':collision_events,
            'jev_calls':service.calls if service else 0,'jev_evidence':service.evidence if service else [],
            'limitations':'Unvalidated CARLA adapter. No GLB scenery import, perception or driving-safety claim.'},indent=2))


def main():
    parser=argparse.ArgumentParser(description='Experimental CARLA adapter — simulator use only')
    sub=parser.add_subparsers(dest='command',required=True)
    c=sub.add_parser('convert');c.add_argument('--osm',type=Path,default=Path('data/raw/kirchberg_subset.osm'))
    c.add_argument('--out',type=Path,default=Path('world/kirchberg.xodr'))
    r=sub.add_parser('run');r.add_argument('--xodr',type=Path,default=Path('world/kirchberg.xodr'))
    r.add_argument('--world',type=Path,default=Path('world/world.json'))
    r.add_argument('--host',default='127.0.0.1');r.add_argument('--port',type=int,default=2000)
    r.add_argument('--replace-world',action='store_true')
    r.add_argument('--mode',choices=['baseline','jev-shadow','jev-live'],default='baseline')
    r.add_argument('--seconds',type=float,default=40);r.add_argument('--max-calls',type=int,default=120)
    r.add_argument('--out',type=Path,default=Path('runs/carla-debug.json'))
    args=parser.parse_args()
    try:
        import carla
        if args.command=='convert': convert(carla,args.osm,args.out)
        else:
            if not math.isfinite(args.seconds) or not 0<args.seconds<=600:
                raise ValueError('--seconds must be in (0,600]')
            run(carla,args)
    except (ImportError,ValueError,RuntimeError,OSError) as exc:
        parser.exit(2,f'CARLA adapter error: {exc}\n')

if __name__=='__main__': main()
