"""Offline, stdlib-only choreography contracts; not traffic-safety claims."""
import math
import pytest
from urban_district.runtime import RuntimeRoad, time_state, instance_transform, light_state

ANCHOR={'coordinates_enu_m':[[0,0],[0,50],[0,100]]}
CONFIG={'camera':{'start_s_m':10},'cross_streets_s_m':[90]}

@pytest.mark.parametrize('distance',[0,5,50,75,100])
def test_metric_straight_path(distance):
    r=RuntimeRoad(ANCHOR)
    assert r.point(distance,-1.8,1.55)==pytest.approx([-1.8,distance,1.55])
    assert r.length==100

@pytest.mark.parametrize('t',[-1,float('nan'),float('inf')])
def test_time_must_be_finite_and_nonnegative(t):
    with pytest.raises(ValueError):time_state(t,CONFIG)

def test_no_inference_or_physics_claim():
    state=time_state(10,CONFIG)
    assert state['jev_calls']==0 and state['physics_simulated'] is False
    assert state['speed_mps']==0
    assert state['ego_s_m']==40

def test_duplicate_path_segment_fails():
    with pytest.raises(ValueError):RuntimeRoad({'coordinates_enu_m':[[0,0],[0,0],[0,1]]})

def test_stationary_object_preserved():
    matrix=[[1,0,0,3],[0,1,0,4],[0,0,1,5],[0,0,0,1]]
    obj={'id':'bench','matrix':matrix,'motion':None}
    assert instance_transform(obj,8,{'route_anchor':ANCHOR})==matrix

def test_choreography_light_states():
    assert light_state('signal_green','signal',1,CONFIG)=='signal_green'
    assert light_state('signal_green','signal',8,CONFIG)=='signal_off'
    assert light_state('ped_green_off','ped_signal',8,CONFIG)=='signal_green'

def test_unknown_motion_fails():
    obj={'id':'a','matrix':None,'motion':{'kind':'unknown','route_s_m':2,'lateral_m':0}}
    with pytest.raises(ValueError):instance_transform(obj,1,{'route_anchor':ANCHOR,'config':CONFIG})
