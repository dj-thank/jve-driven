"""Check request -> proposal -> constrained control -> motion trace consistency.

This is self-recorded simulation evidence, NOT a publisher signature, a measure
of model intelligence, a perception benchmark or a real-vehicle safety approval.
"""
from __future__ import annotations
from dataclasses import asdict, fields
import hashlib
import json
import math
import numpy as np
from .control import Observation, Proposal, baseline, guarded_control
from .jev import parse_response, payload

INVALID_REASONS = {'missing_decision', 'future_decision', 'expired_decision',
                   'road_lane_changed', 'uncertain_decision', 'stale_observation'}


def digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, allow_nan=False).encode()).hexdigest()


def require_close(actual, expected, name):
    a, b = np.asarray(actual, float), np.asarray(expected, float)
    if a.shape != b.shape or not np.isfinite(a).all() or not np.allclose(a, b, rtol=0, atol=1e-8):
        raise ValueError(name + ' does not match recorded dynamics')


def audit_control_trace(run):
    if run.get('schema') != 'jevdrive.run.v1' or run.get('control_trace_schema') != 'jevdrive.control-trace.v1':
        raise ValueError('A complete control trace is required; a camera replay is not driving evidence')
    steps = run.get('steps')
    if not isinstance(steps, list) or not 1 <= len(steps) <= 12000:
        raise ValueError('Empty or oversized trace')
    records = {}; latencies = []; errors = 0
    obs_fields = {f.name for f in fields(Observation)}
    for record in run.get('jev_evidence', []):
        if 'error' in record:
            errors += 1; continue
        if digest(record['request']) != record['request_sha256'] or digest(record['response']) != record['response_sha256']:
            raise ValueError('Request/response hash mismatch')
        obs = Observation(**{k:v for k,v in record['request']['state'].items() if k in obs_fields})
        if record['request'] != payload(obs, record['request']['model']):
            raise ValueError('Request computed state or question contract changed')
        if obs.frame >= len(steps) or asdict(obs) != steps[obs.frame]['observation']:
            raise ValueError('Inference observation differs from the original control snapshot')
        parsed = parse_response(record['response'], obs, record['requested_wall'], record['request']['model'])
        if record['snapshot_frame'] != obs.frame or record['snapshot_sim_time'] != obs.sim_time:
            raise ValueError('Response snapshot identity mismatch')
        if not (math.isfinite(record['received_wall']) and record['received_wall'] >= parsed.requested_wall):
            raise ValueError('Invalid response timing')
        require_close(record['latency_ms'], (record['received_wall']-parsed.requested_wall)*1000, 'API latency')
        key = (parsed.frame, parsed.requested_wall)
        if key in records: raise ValueError('Duplicate inference snapshot')
        records[key] = (parsed, record)
        latencies.append(record['latency_ms'])
    if run.get('jev_calls', 0) < len(records)+errors:
        raise ValueError('Response count exceeds attempted requests')
    used = set(); applied = changed = invalid = 0; traveled = 0.0
    prior = None; last_wall = -math.inf
    for index, step in enumerate(steps):
        if step['frame'] != index: raise ValueError('Trace frame missing or reordered')
        dt = step['dt']; now = step['wall_monotonic']
        if not math.isfinite(dt) or not 0 < dt <= .1 or not math.isfinite(now) or now < last_wall:
            raise ValueError('Invalid step clock')
        last_wall = now
        obs = Observation(**step['observation'])
        if obs.frame != index: raise ValueError('Observation identity mismatch')
        require_close(obs.sim_time, index*dt, 'Simulation time')
        p = Proposal(**step['proposal']) if step['proposal'] is not None else None
        control = guarded_control(obs, p, now=now)
        recorded = step['control']
        require_close([recorded['target_speed_mps'], recorded['acceleration_mps2']],
                      [control.target_speed_mps, control.acceleration_mps2], 'Applied control')
        if recorded['proposal_source'] != control.proposal_source or tuple(recorded['reasons']) != control.reasons:
            raise ValueError('Control reason/source mismatch')
        comparison = guarded_control(obs, baseline(obs, now), now=now)
        require_close([step['baseline_counterfactual'][k] for k in ('target_speed_mps','acceleration_mps2')],
                      [comparison.target_speed_mps, comparison.acceleration_mps2], 'Baseline counterfactual')
        before, after = step['before'], step['after']
        if prior is not None: require_close(before, prior, 'Trace continuity')
        require_close(before[3], obs.speed_mps, 'Observed speed')
        x,y,yaw,v = before; steer = step['steer_rad']
        if not math.isfinite(steer) or abs(steer) > .55: raise ValueError('Invalid steering')
        nv = max(0.0, v+control.acceleration_mps2*dt); mid = (v+nv)/2
        dyaw = mid/2.7*math.tan(steer)*dt
        expected = [x+mid*math.cos(yaw+dyaw/2)*dt, y+mid*math.sin(yaw+dyaw/2)*dt, yaw+dyaw, nv]
        require_close(after, expected, 'Next vehicle state')
        traveled += math.hypot(after[0]-x, after[1]-y); prior = after
        if p is not None and p.source == 'jev_api':
            key = (p.frame,p.requested_wall)
            if key not in records: raise ValueError('Applied Jev proposal has no matching API response')
            parsed, evidence = records[key]
            if asdict(parsed) != asdict(p): raise ValueError('Proposal differs from API response')
            if evidence['received_wall'] > now or evidence.get('collected_after_control_loop'):
                raise ValueError('Response applied before receipt or after the control loop')
            if INVALID_REASONS.intersection(control.reasons):
                invalid += 1
            else:
                if run['mode'] != 'jev-live': raise ValueError('Only live mode can apply an API proposal')
                used.add(key); applied += 1
                if abs(control.target_speed_mps-comparison.target_speed_mps)>1e-8 or abs(control.acceleration_mps2-comparison.acceleration_mps2)>1e-8:
                    changed += 1
    real_used = {key for key in used if records[key][1].get('transport') == 'official_https_api'}
    fixture_records = sum(r.get('transport') != 'official_https_api' for _, r in records.values())
    return {'schema':'jevdrive.decision-audit.v1','mode':run['mode'], 'trace_steps':len(steps),
        'trace_consistent':True,'api_attempts':run.get('jev_calls',0),'validated_responses':len(records),
        'api_errors':errors,'fixture_response_records':fixture_records,
        'recorded_official_api_responses_used':len(real_used),'responses_used_in_control':len(used),'api_applied_steps':applied,
        'rejected_api_steps':invalid,'control_differs_from_baseline_steps':changed,
        'traveled_m':traveled,'latency_ms_percentiles':dict(zip(('p50','p95','p99'),
             np.percentile(latencies,[50,95,99]).tolist())) if latencies else None,
        'live_control_evidence_present':run['mode']=='jev-live' and bool(real_used) and fixture_records==0 and traveled>1,
        'model_improvement_demonstrated':False,'camera_perception_evaluated':False,
        'external_api_authenticity_independently_verified':False,
        'scope':'Self-recorded kinematic simulation consistency; not a driving-safety certificate'}
