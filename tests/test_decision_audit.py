"""All network responses in these tests are synthetic contract fixtures."""
from concurrent.futures import Future
from copy import deepcopy
from dataclasses import asdict, replace
import json
from pathlib import Path
import pytest
from jevdrive import jev
from jevdrive.control import Observation, baseline
from jevdrive.decision_audit import audit_control_trace, digest
from jevdrive.simulation import simulate
from jevdrive.world import parse_osm
from test_contracts import valid_response

ROOT=Path(__file__).resolve().parents[1]


def run_baseline():
    return simulate(parse_osm(ROOT/'data/raw/kirchberg_subset.osm'), duration=2)


def test_baseline_is_not_promoted_to_api_driving():
    result=audit_control_trace(run_baseline())
    assert result['trace_consistent'] and result['traveled_m']>1
    assert result['api_applied_steps']==0 and not result['live_control_evidence_present']


@pytest.mark.parametrize('damage',['position','control','source','order','speed','time','nan','camera'])
def test_inconsistent_trace_rejected(damage):
    r=run_baseline()
    if damage=='position':r['steps'][4]['after'][0]+=1
    elif damage=='control':r['steps'][4]['control']['acceleration_mps2']=0
    elif damage=='source':r['steps'][4]['control']['proposal_source']='jev_api'
    elif damage=='order':r['steps'].pop(3)
    elif damage=='speed':r['steps'][4]['observation']['speed_mps']+=1
    elif damage=='time':r['steps'][4]['observation']['sim_time']+=1
    elif damage=='nan':r['steps'][4]['before'][0]=float('nan')
    elif damage=='camera':r['schema']='jevdrive.ego-inspection.v1'
    with pytest.raises(ValueError):audit_control_trace(r)


def fixture_api_run():
    r=run_baseline();r['mode']='jev-live';r['jev_calls']=len(r['steps']);r['jev_evidence']=[]
    # Explicit synthetic API fixture producing the identical baseline action.
    for step in r['steps']:
        obs=Observation(**step['observation']);data=valid_response()
        data['answers']['maneuver'].update(confidence=1.,probabilities={'proceed':1.,'slow':0.,'yield':0.,'stop':0.})
        data['answers']['pedestrian_yield']['noul']=0.
        requested=step['wall_monotonic']-.001
        proposal=jev.parse_response(data,obs,requested)
        body=jev.payload(obs)
        r['jev_evidence'].append({'snapshot_frame':obs.frame,'snapshot_sim_time':obs.sim_time,
            'request':body,'response':data,'request_sha256':digest(body),'response_sha256':digest(data),
            'requested_wall':requested,'received_wall':step['wall_monotonic'],
            'latency_ms':(step['wall_monotonic']-requested)*1000,
            'transport':'SYNTHETIC_TEST_FIXTURE','collected_after_control_loop':False})
        step['proposal']=asdict(proposal);step['control']['proposal_source']='jev_api'
    return r


def test_matching_response_trace_is_consistent_not_model_superiority():
    a=audit_control_trace(fixture_api_run())
    assert a['api_applied_steps']==40 and a['responses_used_in_control']==40
    assert a['control_differs_from_baseline_steps']==0
    assert not a['live_control_evidence_present']
    assert a['fixture_response_records']==40 and a['recorded_official_api_responses_used']==0
    assert not a['model_improvement_demonstrated']
    assert not a['external_api_authenticity_independently_verified']


@pytest.mark.parametrize('damage',['no_response','hash','changed_proposal','late','shutdown','computed','duplicate'])
def test_response_to_motion_binding(damage):
    r=fixture_api_run()
    if damage=='no_response':r['jev_evidence'].pop(3)
    elif damage=='hash':r['jev_evidence'][3]['response_sha256']='wrong'
    elif damage=='changed_proposal':r['steps'][3]['proposal']['confidence']=.9
    elif damage=='late':
        rec=r['jev_evidence'][3];rec['received_wall']+=1;rec['latency_ms']+=1000
    elif damage=='shutdown':r['jev_evidence'][3]['collected_after_control_loop']=True
    elif damage=='computed':
        rec=r['jev_evidence'][3];rec['request']['state']['computed']['stopping_distance_m']=1e8
        rec['request_sha256']=digest(rec['request'])
    elif damage=='duplicate':r['jev_evidence'].append(deepcopy(r['jev_evidence'][3]))
    with pytest.raises(ValueError):audit_control_trace(r)


def test_completed_final_request_is_recorded_but_not_actuated():
    obs=Observation(1,.05,0,8.3,100);service=jev.DecisionService(key='synthetic-unused')
    f=Future();f.set_result((baseline(obs,1),{'test_fixture':True}))
    service.future=f;service.pending_observation=obs
    service.close();service.close()
    assert len(service.evidence)==1 and service.evidence[0]['collected_after_control_loop']
    assert service.latest is None and service.key==''
    with pytest.raises(jev.JevError,match='closed'):service.poll(obs)


def test_shutdown_failure_is_recorded_sanitized():
    service=jev.DecisionService(key='synthetic-unused');f=Future()
    f.set_exception(RuntimeError('secret must not be included'));service.future=f
    service.close()
    assert service.evidence[0]['error']=='RuntimeError'
    assert 'secret must not' not in str(service.evidence)


def test_key_echo_is_rejected_before_logging(monkeypatch):
    async def fake(*args):
        data=valid_response();data['accidental']='synthetic-private-key';return data
    monkeypatch.setattr(jev,'_request_async',fake)
    with pytest.raises(jev.JevError,match='credential_echo'):
        jev.request_once(Observation(1,.05,0,8.3,100),'synthetic-private-key',1)


def test_changed_question_contract_is_not_equivalent_inference():
    r=fixture_api_run();rec=r['jev_evidence'][3]
    rec['request']=deepcopy(rec['request'])
    rec['request']['questions']['maneuver']['instructions']='different request'
    rec['request_sha256']=digest(rec['request'])
    with pytest.raises(ValueError,match='question contract'):audit_control_trace(r)


def test_inference_must_describe_actual_observed_snapshot():
    r=fixture_api_run();rec=r['jev_evidence'][3]
    obs=Observation(**r['steps'][3]['observation']);obs=replace(obs,scene_notes='unrelated scene')
    rec['request']=jev.payload(obs);rec['request_sha256']=digest(rec['request'])
    with pytest.raises(ValueError,match='original control snapshot'):audit_control_trace(r)


def test_recorder_cli_keeps_baseline_and_missing_key_distinct(tmp_path):
    import os,subprocess,sys
    env={**os.environ,'PYTHONPATH':str(ROOT/'src')}
    env.pop('TYPESAFE_API_KEY',None)
    for mode,expected in [('baseline',0),('jev-live',2)]:
        out=tmp_path/mode
        proc=subprocess.run([sys.executable,str(ROOT/'tools/record_jev_evidence.py'),
            '--mode',mode,'--seconds','1','--out',str(out)],cwd=ROOT,env=env,
            input='',capture_output=True,text=True,timeout=10)
        assert proc.returncode==expected
        report=json.loads((out/'execution.json').read_text())
        assert not report['live_control_evidence_present']
        assert report['completed'] is (mode=='baseline')
        if mode=='jev-live': assert not (out/'run.json').exists()
