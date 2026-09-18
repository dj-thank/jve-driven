"""Simulation controller. These guards are not a certified real-vehicle safety system."""
from __future__ import annotations
from dataclasses import asdict, dataclass
import math
import time
from typing import Any, Literal

ACTIONS = ('proceed','slow','yield','stop')


def finite_number(value: Any, label: str, low: float=0.0, high: float=1e9) -> float:
    if isinstance(value,bool) or not isinstance(value,(int,float)) or not math.isfinite(value):
        raise ValueError(f'{label} must be finite numeric')
    if not low <= value <= high:
        raise ValueError(f'{label} outside [{low},{high}]')
    return float(value)


@dataclass(frozen=True)
class Observation:
    frame: int
    sim_time: float
    speed_mps: float
    speed_limit_mps: float
    route_remaining_m: float
    road_id: str='25216931'
    lane_id: str='assumed_right_lane'
    obstacle_gap_m: float | None=None  # bumper-to-bumper, latest observation
    closing_speed_mps: float=0.0
    signal: str='NONE'
    signal_distance_m: float | None=None  # bumper-to-stop-line distance
    pedestrian_conflict: bool=False
    occluded: bool=False
    observation_age_s: float=0.0
    source: str='ground_truth_debug'
    scene_notes: str=''

    def __post_init__(self):
        if isinstance(self.frame,bool) or not isinstance(self.frame,int) or self.frame<0:
            raise ValueError('Invalid frame')
        for k in ['sim_time','speed_mps','speed_limit_mps','route_remaining_m','observation_age_s']:
            finite_number(getattr(self,k),k)
        finite_number(self.closing_speed_mps,'closing_speed_mps',-100,100)
        for k in ['obstacle_gap_m','signal_distance_m']:
            value=getattr(self,k)
            if value is not None:
                finite_number(value,k)
        if self.signal not in {'NONE','GREEN','YELLOW','RED','UNKNOWN'}:
            raise ValueError('Unknown signal enum')
        if not isinstance(self.pedestrian_conflict,bool) or not isinstance(self.occluded,bool):
            raise ValueError('Conflict/occlusion must be bool')
        if not self.road_id or not self.lane_id or self.source not in {'ground_truth_debug','perception'}:
            raise ValueError('Missing road/lane or invalid observation source')
        if len(self.scene_notes)>2000:
            raise ValueError('Filter scene notes before inference')

    def as_state(self) -> dict[str, Any]:
        state=asdict(self)
        # All numerical operations happen here, not in Jev.
        state['computed']={
            'stopping_distance_m':self.speed_mps**2/(2*4.0)+self.speed_mps*0.25+2.0,
            'obstacle_in_stopping_envelope':self.obstacle_gap_m is not None and
                self.obstacle_gap_m < self.speed_mps**2/(2*4.0)+self.speed_mps*.25+2.0,
            'signal_requires_stop':self.signal in {'RED','YELLOW','UNKNOWN'},
            'short_remaining_route':self.route_remaining_m<15,
        }
        return state


@dataclass(frozen=True)
class Proposal:
    action: str
    confidence: float
    probabilities: dict[str,float]
    yield_noul: float
    caution_score: float
    frame: int
    sim_time: float
    road_id: str
    lane_id: str
    requested_wall: float
    model: str
    source: Literal['rule_baseline','jev_api','test_fixture']

    def __post_init__(self):
        if self.action not in ACTIONS or set(self.probabilities)!=set(ACTIONS):
            raise ValueError('Action vocabulary mismatch')
        for v in self.probabilities.values(): finite_number(v,'probability',0,1)
        if abs(sum(self.probabilities.values())-1)>1e-4:
            raise ValueError('Probabilities must sum to one')
        if self.probabilities[self.action] + 1e-8 < max(self.probabilities.values()):
            raise ValueError('Choice must be an argmax')
        finite_number(self.confidence,'confidence',0,1)
        finite_number(self.yield_noul,'yield_noul',0,1)
        finite_number(self.caution_score,'caution_score',0,2)
        finite_number(self.sim_time,'sim_time')
        finite_number(self.requested_wall,'requested_wall')
        if self.source not in {'rule_baseline','jev_api','test_fixture'}:
            raise ValueError('Unlabelled decision source')


@dataclass(frozen=True)
class Control:
    target_speed_mps: float
    acceleration_mps2: float
    reasons: tuple[str,...]
    proposal_source: str


@dataclass(frozen=True)
class GuardConfig:
    max_decision_age_s: float=1.0
    max_wall_age_s: float=1.0
    max_observation_age_s: float=0.2
    min_confidence: float=0.75  # tuning parameter, NOT a probability of safety
    min_action_probability: float=0.70
    braking_mps2: float=4.0
    reaction_s: float=0.25
    stop_margin_m: float=2.0
    caution_speed_mps: float=2.0


def speed_for_distance(gap: float, cfg: GuardConfig) -> float:
    d=max(0.0,gap-cfg.stop_margin_m)
    # v*t + v^2/(2*b) <= d
    return max(0.0,-cfg.braking_mps2*cfg.reaction_s + math.sqrt(
        (cfg.braking_mps2*cfg.reaction_s)**2+2*cfg.braking_mps2*d))


def baseline(obs: Observation, now: float | None=None) -> Proposal:
    now=time.monotonic() if now is None else now
    action='slow' if obs.occluded else 'proceed'
    if obs.pedestrian_conflict:
        action='stop'
    return Proposal(action,1.0,{a:float(a==action) for a in ACTIONS},
                    float(obs.pedestrian_conflict),float(obs.occluded),
                    obs.frame,obs.sim_time,obs.road_id,obs.lane_id,now,
                    'deterministic-baseline-v1','rule_baseline')


def guarded_control(obs: Observation, proposal: Proposal | None,
                    cfg: GuardConfig=GuardConfig(), now: float | None=None) -> Control:
    now=time.monotonic() if now is None else now
    target=obs.speed_limit_mps
    reasons=[]
    valid=True
    if proposal is None:
        valid=False; reasons.append('missing_decision')
    else:
        if proposal.frame>obs.frame or proposal.sim_time>obs.sim_time+1e-9:
            valid=False; reasons.append('future_decision')
        if obs.sim_time-proposal.sim_time>cfg.max_decision_age_s or not 0<=now-proposal.requested_wall<=cfg.max_wall_age_s:
            valid=False; reasons.append('expired_decision')
        if proposal.road_id!=obs.road_id or proposal.lane_id!=obs.lane_id:
            valid=False; reasons.append('road_lane_changed')
        if proposal.confidence<cfg.min_confidence or proposal.probabilities[proposal.action]<cfg.min_action_probability:
            valid=False; reasons.append('uncertain_decision')
    if obs.observation_age_s>cfg.max_observation_age_s:
        valid=False; reasons.append('stale_observation')
    if not valid:
        target=0.0
    elif proposal is not None:
        if proposal.action in {'stop','yield'} or proposal.yield_noul>=0.5:
            target=0; reasons.append('proposal_stop_or_yield')
        elif proposal.action=='slow' or proposal.caution_score>=1.0:
            target=min(target,cfg.caution_speed_mps); reasons.append('proposal_caution')
    # Guards always consume current scene state, never only the inference snapshot.
    target=min(target,speed_for_distance(obs.route_remaining_m,cfg))
    if obs.route_remaining_m<20:
        reasons.append('route_end_envelope')
    gaps=[obs.route_remaining_m]
    if obs.obstacle_gap_m is not None:
        target=min(target,speed_for_distance(obs.obstacle_gap_m,cfg))
        gaps.append(obs.obstacle_gap_m)
        reasons.append('obstacle_envelope')
        if obs.closing_speed_mps>0 and obs.obstacle_gap_m/max(obs.closing_speed_mps,0.01)<1.5:
            target=0; reasons.append('low_ttc')
    if obs.signal in {'RED','YELLOW','UNKNOWN'}:
        if obs.signal_distance_m is None:
            target=0; reasons.append('unknown_stopline')
        else:
            target=min(target,speed_for_distance(obs.signal_distance_m,cfg))
            gaps.append(obs.signal_distance_m)
        reasons.append('signal_stop')
    if obs.occluded:
        target=min(target,cfg.caution_speed_mps); reasons.append('occlusion_cap')
    if obs.pedestrian_conflict:
        target=0; reasons.append('pedestrian_guard')
    target=max(0.0,min(target,obs.speed_limit_mps))
    acceleration=max(-cfg.braking_mps2,min(2.0,(target-obs.speed_mps)*1.4))
    stopping=obs.speed_mps**2/(2*cfg.braking_mps2)+obs.speed_mps*cfg.reaction_s+cfg.stop_margin_m
    if min(gaps)<=stopping or obs.pedestrian_conflict or not valid:
        if obs.speed_mps>target:
            acceleration=-cfg.braking_mps2
            reasons.append('emergency_brake_request')
    return Control(target,acceleration,tuple(dict.fromkeys(reasons)),proposal.source if proposal else 'none')


def pure_pursuit(x: float,y: float,yaw: float,target_x: float,target_y: float,
                 wheelbase: float=2.7,max_steer_rad: float=0.55) -> float:
    dx,dy=target_x-x,target_y-y
    length=math.hypot(dx,dy)
    if length<0.01:
        return 0.0
    alpha=math.atan2(dy,dx)-yaw
    return max(-max_steer_rad,min(max_steer_rad,math.atan2(2*wheelbase*math.sin(alpha),length)))
