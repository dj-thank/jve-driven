from dataclasses import replace
import json
import math
from pathlib import Path
import pytest
from jevdrive.control import Observation,Proposal,baseline,guarded_control,pure_pursuit,speed_for_distance,GuardConfig
from jevdrive.jev import MODEL,QUESTIONS,JevError,payload,parse_response,DecisionService


def observation(**kw):
    return replace(Observation(frame=100,sim_time=5,speed_mps=4,speed_limit_mps=8.333,route_remaining_m=100),**kw)


def valid_response():
    return {'model':MODEL,'answers':{
      'maneuver':{'type':'choice','choice':'proceed','probabilities':{'proceed':.97,'slow':.01,'yield':.01,'stop':.01},'confidence':.9},
      'pedestrian_yield':{'type':'noul','noul':.01},
      'visibility_caution':{'type':'score','score':.0,'probabilities':{'0':1.0,'1':0.0,'2':0.0},
        'confidence':1.0,'legend':{'0':'clear','1':'partial','2':'severe'}}},'usage':{'input_tokens':250,'output_tokens':30}}


@pytest.mark.parametrize('field,value', [('speed_mps',math.nan),('speed_mps',math.inf),('speed_mps',-1),
    ('speed_limit_mps',True),('sim_time',-1),('route_remaining_m',-2),('signal','blue'),
    ('observation_age_s',-1),('obstacle_gap_m',-1),('frame',True),('pedestrian_conflict',1)])
def test_bad_observations_rejected(field,value):
    with pytest.raises(ValueError): observation(**{field:value})


def test_no_key_no_fake_jev(monkeypatch):
    monkeypatch.delenv('TYPESAFE_API_KEY',raising=False)
    with pytest.raises(JevError,match='no mock'): DecisionService()


def test_request_shape_and_pinning():
    p=payload(observation())
    assert p['model']=='jev-1.13.0'
    assert set(p)=={'model','state','questions'}
    assert set(p['questions'])==set(QUESTIONS)
    assert 'computed' in p['state']
    with pytest.raises(ValueError): payload(observation(),'jev-latest')


def test_response_contract():
    p=parse_response(valid_response(),observation(),100)
    assert p.source=='jev_api' and p.model==MODEL and p.action=='proceed'


@pytest.mark.parametrize('damage', ['missing','type','nan','sum','vocabulary','choice_argmax','confidence','model','score','score_sum'])
def test_malformed_answers_rejected(damage):
    data=valid_response(); a=data['answers']['maneuver']
    if damage=='missing': del data['answers']['pedestrian_yield']
    elif damage=='type': a['type']='score'
    elif damage=='nan': a['probabilities']['proceed']=math.nan
    elif damage=='sum': a['probabilities']['proceed']=.7
    elif damage=='vocabulary': a['probabilities']['accelerate']=a['probabilities'].pop('stop')
    elif damage=='choice_argmax': a['choice']='stop'
    elif damage=='confidence': a['confidence']=2
    elif damage=='model': data['model']='jev-latest'
    elif damage=='score': data['answers']['visibility_caution']['score']=2
    elif damage=='score_sum': data['answers']['visibility_caution']['probabilities']['0']=.5
    with pytest.raises(JevError): parse_response(data,observation(),100)


def test_baseline_is_honestly_labelled():
    assert baseline(observation(),100).source=='rule_baseline'


@pytest.mark.parametrize('case', ['missing','expired_sim','expired_wall','road_change','lane_change','low_confidence','future_frame','future_time','stale_observation'])
def test_invalid_decisions_brake(case):
    o=observation(); p=baseline(o,100)
    if case=='missing': p=None
    elif case=='expired_sim': p=replace(p,sim_time=2)
    elif case=='expired_wall': p=replace(p,requested_wall=98)
    elif case=='road_change': p=replace(p,road_id='other')
    elif case=='lane_change': p=replace(p,lane_id='other')
    elif case=='low_confidence': p=replace(p,confidence=.2)
    elif case=='future_frame': p=replace(p,frame=101)
    elif case=='future_time': p=replace(p,sim_time=6)
    elif case=='stale_observation': o=replace(o,observation_age_s=.3)
    c=guarded_control(o,p,now=100)
    assert c.target_speed_mps==0 and c.acceleration_mps2<0


@pytest.mark.parametrize('signal', ['RED','YELLOW','UNKNOWN'])
def test_current_signal_overrides_old_proceed(signal):
    o=observation(signal=signal,signal_distance_m=1)
    p=baseline(observation(),100)
    c=guarded_control(o,p,now=100)
    assert c.target_speed_mps==0 and 'signal_stop' in c.reasons


def test_no_stopline_stops():
    o=observation(signal='RED'); c=guarded_control(o,baseline(o,100),now=100)
    assert c.target_speed_mps==0 and 'unknown_stopline' in c.reasons


def test_pedestrian_guard_independent_of_proposal():
    o=observation(pedestrian_conflict=True)
    p=baseline(observation(),100)
    assert p.action=='proceed'
    c=guarded_control(o,p,now=100)
    assert c.target_speed_mps==0 and 'pedestrian_guard' in c.reasons


def test_obstacle_guard():
    o=observation(obstacle_gap_m=1)
    c=guarded_control(o,baseline(o,100),now=100)
    assert c.target_speed_mps==0


def test_occlusion_cap():
    o=observation(occluded=True)
    assert guarded_control(o,baseline(observation(),100),now=100).target_speed_mps<=2


@pytest.mark.parametrize('gap',[0,1,2,5,10,20,100])
def test_braking_equation(gap):
    cfg=GuardConfig(); v=speed_for_distance(gap,cfg)
    assert v*cfg.reaction_s+v*v/(2*cfg.braking_mps2)<=max(0,gap-cfg.stop_margin_m)+1e-8


def test_probability_not_confidence():
    data=valid_response()
    a=data['answers']['maneuver']; a['confidence']=.99
    a['probabilities']={'proceed':.4,'slow':.3,'yield':.2,'stop':.1}
    p=parse_response(data,observation(),100)
    c=guarded_control(observation(),p,now=100)
    assert c.target_speed_mps==0


def test_pure_pursuit_limits():
    assert pure_pursuit(0,0,0,10,0)==0
    assert 0<pure_pursuit(0,0,0,1,10)<=.55
    assert -.55<=pure_pursuit(0,0,0,1,-10)<0
