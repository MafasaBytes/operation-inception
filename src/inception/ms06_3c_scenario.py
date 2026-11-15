"""One directed PB-1.2 scene: observational integrity and pre-render gates only."""
from __future__ import annotations

from collections import Counter
from concurrent.futures import ProcessPoolExecutor
import hashlib
import json
import math
from pathlib import Path

import numpy as np

from .pressure_bloom import Ball, EPS, encoded
from .pressure_bloom_v12 import Parameters12, _Engine12, simulate
from .ms06_3_scenario import digest, finite_tree, nearby_probes, summarize
from .ms06_3b_scenario import whole_bed, activity_gate


class ObservedEngine(_Engine12):
    """Return the original solver result unchanged; collect attempts separately."""
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.trial_counts=Counter()
        self.failed_trial_counts=Counter()
        self.failed_trial_peak=0.
        self.integrity_samples=[]

    def project(self,balls,height):
        result,valid=super().project(balls,height)
        self.trial_counts[self.mode]+=1
        if not valid:
            self.failed_trial_counts[self.mode]+=1
            self.failed_trial_peak=max(self.failed_trial_peak,self.penetration(result,height))
        return result,valid

    def observe(self):
        bs=self.inside();audit=self.audit
        connected=[b for b in bs if audit.get(b.id,{}).get('C',0)]
        height=self.p.schedule[0][1]
        self.integrity_samples.append({'rules':'PB-1.2','tick':self.tick,'time':self.tick/120,
            'mode':self.mode,'max_penetration':self.penetration(self.balls,self.height),
            'max_speed':max((math.hypot(b.vx,b.vy) for b in self.balls.values()),default=0.),
            'minimum_radius':min((b.radius for b in bs),default=self.p.reference_radius),
            'nonprogress_counter':self.idle,'piston':self.drive_metrics(),
            'contact_network_size':len(connected),
            'contact_network_depth':max((max(0.,height-b.y)/height for b in connected),default=0.)})

    def checks(self):
        super().checks()
        self.observe()

    def run(self):
        result=super().run()
        if result.samples and (not self.integrity_samples or self.integrity_samples[-1]['tick']!=self.tick):
            self.observe()
        return result


def resistance_certificate(state):
    """Independent nonnegative, frictionless contact-equilibrium diagnostic.

    No forces feed back into PB-1.2. A feasible unit downward piston reaction
    balanced by real disk/floor/wall contacts supports a local resistance claim;
    it does not prove global packing optimality or physical material behavior.
    """
    balls=sorted((b for b in state['balls'] if b['status']=='inside'),key=lambda b:b['id'])
    ids={b['id']:i for i,b in enumerate(balls)};n=len(balls)
    columns=[];piston_columns=0
    for b in balls:
        i=ids[b['id']];a=state['loads'].get(b['id'],{})
        for k in a.get('neighbors',[]):
            if k not in ids or k<=b['id']:continue
            j=ids[k];c=balls[j];dx=b['x']-c['x'];dy=b['y']-c['y'];d=math.hypot(dx,dy)
            if not d:continue
            v=np.zeros(2*n+1);v[2*i:2*i+2]=(dx/d,dy/d);v[2*j:2*j+2]=(-dx/d,-dy/d);columns.append(v)
        normals=[]
        if a.get('floor'):normals.append((0.,1.,0.))
        if b['x']-b['radius']<=EPS:normals.append((1.,0.,0.))
        # Right contact is derived from the stored side-wall contribution normal.
        for key,w in state['walls'].items():
            if key.startswith('R') and b['id'] in w['contacts']:normals.append((-1.,0.,0.))
        if a.get('piston'):normals.append((0.,-1.,1.));piston_columns+=1
        for x,y,p in normals:
            v=np.zeros(2*n+1);v[2*i:2*i+2]=(x,y);v[-1]=p;columns.append(v)
    if not columns or not piston_columns:
        return {'applicable':False,'passed':False,'reason':'no_piston_reaction_path'}
    A=np.column_stack(columns);target=np.zeros(2*n+1);target[-1]=1.
    step=1/max(float(np.linalg.norm(A,2)**2),1e-12);forces=np.zeros(A.shape[1])
    residual=1.
    for iteration in range(30000):
        forces=np.maximum(0.,forces-step*(A.T@(A@forces-target)))
        if iteration%50==0:
            residual=float(np.linalg.norm(A@forces-target))
            if residual<=1e-4:break
    residual=float(np.linalg.norm(A@forces-target))
    return {'applicable':True,'passed':bool(np.isfinite(forces).all() and residual<=1e-3),
            'normalized_residual':residual,'iterations':iteration+1,'tolerance':1e-3,
            'contact_force_count':len(forces),'piston_contact_count':piston_columns,
            'meaning':'local nonnegative contact equilibrium; observational only'}


def run(cfg,label='base',observed=True):
    args=(tuple(Ball(**b) for b in cfg['balls']),Parameters12(**cfg['parameters']))
    if observed:
        e=ObservedEngine(*args,cfg['seed'],f"{cfg['id']}.{label}");r=e.run()
        extra={'samples':e.integrity_samples,'constraint_trials':dict(e.trial_counts),
               'failed_constraint_trials':dict(e.failed_trial_counts),
               'failed_trial_max_penetration':e.failed_trial_peak}
        return r,extra
    return simulate(*args,seed=cfg['seed'],run_id=f"{cfg['id']}.{label}")


def evaluate(result,extra):
    s=summarize(result);prep=json.loads(result.settlement)
    started=prep['summary']['status']=='completed' and bool(result.samples)
    s['settlement']=prep['summary'];s['whole_bed']=whole_bed(result) if started else None
    if s['whole_bed'] is not None:
        s['whole_bed'].update(schema='ms06.3c.whole-bed.v1',rules='PB-1.2')
    active=extra['samples'];finite=s['finite'] and finite_tree(prep) and finite_tree(extra)
    maximum=max([x['max_penetration'] for x in active]+[x['max_penetration'] for x in prep['samples']]+[0.])
    speed=max([x['max_speed'] for x in active]+[x['max_speed'] for x in prep['samples']]+[0.])
    previous={b['id']:b for b in json.loads(result.initial)['balls']}
    observed_speed=0.
    for raw in result.samples:
        current={b['id']:b for b in json.loads(raw)['balls']}
        for k,b in current.items():
            if k in previous:
                a=previous[k]
                observed_speed=max(observed_speed,120*math.hypot(b['x']-a['x'],b['y']-a['y']))
        previous=current
    overlap_run=maximum_overlap_run=0
    for x in active:
        overlap_run=overlap_run+1 if x['max_penetration']>EPS else 0
        maximum_overlap_run=max(maximum_overlap_run,overlap_run)
    reasons=s['reason'] or ''
    numerical={'finite':finite,'no_invalid_or_draw':s['outcome'] in ('rupture','containment','extinction'),
               'no_command_policy_rejection':'command_exceeds' not in reasons,
               'valid_committed_geometry':all(x['max_penetration']<=.5*x['minimum_radius']+EPS for x in active)
                                          and max(0,maximum_overlap_run-1)<result.parameters.overlap_ticks,
               'no_irrecoverable_state':s['outcome']!='invalid'}
    meaningful=[]
    for event in result.events:
        if event.kind in ('compression_debt_positive','ball_crushed','wall_ruptured'):
            state=json.loads(event.before if event.kind in ('wall_ruptured','ball_crushed') else event.after)
            if any(a['L']>0 for a in state['loads'].values()):
                meaningful.append({'event_id':event.id,'tick':event.tick,**resistance_certificate(state)})
    numerical['supported_pressure_constraints']=bool(meaningful) and all(x['passed'] for x in meaningful)
    s['numerical_integrity']={'gate':numerical,'passed':all(numerical.values()),
        'maximum_unresolved_penetration':maximum,'maximum_speed':speed,
        'maximum_persistent_identity_displacement_speed':observed_speed,
        'maximum_active_overlap_run_samples':maximum_overlap_run,
        'maximum_active_overlap_duration_ticks':max(0,maximum_overlap_run-1),
        'constraint_resistance_checks':meaningful,**extra}
    a=activity_gate(s['whole_bed'],s['terminal_time']) if started else {'settling_completed':False}
    times=s['event_times'];splits=times.get('ball_split',[]);crush=times.get('ball_crushed',[])
    rupture=times.get('wall_ruptured',[])
    early=any(.8<=t<=1.4 and splits.count(t)==1 and all(abs(other-t)>=.15-1e-12 for other in splits if other!=t)
              and all(abs(c-t)>=.15-1e-12 for c in crush) for t in splits)
    base={**a,**numerical,'genuine_rupture':s['outcome']=='rupture',
          'engagement_by_0_35':bool(s['first_contact'] and s['first_contact']['time']<=.35),
          'isolated_early_split':early,'split_count_15_to_30':15<=len(splits)<=30,
          'crush_count_6_to_14':6<=len(crush)<=14,'crush_reversal_5_to_8':any(5<=c<=8 for c in crush),
          'rupture_9_to_12':bool(rupture and 9<=rupture[0]<=12),
          'multiple_escapes':s['event_counts'].get('ball_escaped',0)>=2,
          'duration_11_to_14':11<=math.ceil((s['terminal_time']+.5)*30)/30<=14,
          'peak_phone_population':s['peak_live_count']<=64}
    s['base_gate']=base;s['passed']=all(base.values())
    return s


def _probe(item):
    name,cfg=item
    r,extra=run(cfg,name);s=evaluate(r,extra);replay=run(cfg,name,observed=False)
    return {'probe':name,'configuration':cfg,**s,'replay_identical':r==replay}


def audit(cfg):
    r,extra=run(cfg);base=evaluate(r,extra);replay=run(cfg,observed=False)
    base_record={'probe':'base','configuration':cfg,**base,'replay_identical':r==replay}
    if not base['passed']:
        return {'rules':'PB-1.2','passed':False,'base_frozen':False,'base':base_record,
                'probe_status':'not_run_base_gate_failed','probes':[]},r
    with ProcessPoolExecutor(max_workers=4) as pool:
        probes=list(pool.map(_probe,nearby_probes(cfg)))
    valid={'rupture','containment','extinction'}
    gate={'base':base['passed'],'all_replay':base_record['replay_identical'] and all(x['replay_identical'] for x in probes),
          'all_finite':all(x['finite'] for x in probes),'six_valid':sum(x['outcome'] in valid for x in probes)>=6,
          'four_ruptures':sum(x['outcome']=='rupture' for x in probes)>=4,
          'at_most_two_failed':sum(x['outcome'] not in valid for x in probes)<=2,
          'five_split_later_crush':sum(x['split_then_crush'] for x in probes)>=5,
          'no_rejected_commands':all(x['numerical_integrity']['gate']['no_command_policy_rejection'] for x in probes),
          'valid_penetration':all(x['numerical_integrity']['gate']['valid_committed_geometry'] for x in probes)}
    return {'schema':'ms06.3c.robustness.v1','rules':'PB-1.2','scenario_sha256':digest(cfg),
            'passed':all(gate.values()),'base_frozen':True,'base':base_record,'gate':gate,
            'probe_status':'completed','probes':probes},r
