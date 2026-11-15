"""Whole-bed measurements and fixed audit for one directed PB-1.1 rupture cut."""
from __future__ import annotations

from concurrent.futures import ProcessPoolExecutor
from dataclasses import asdict
import hashlib
import json
import math
from pathlib import Path

from .pressure_bloom import Ball, Parameters, Result, simulate
from .ms06_3_scenario import digest, finite_tree, nearby_probes, summarize

MEANINGFUL_LOAD = .5


def run(cfg, label='base'):
    return simulate(tuple(Ball(**b) for b in cfg['balls']), Parameters(**cfg['parameters']),
                    seed=cfg['seed'], run_id=f"{cfg['id']}.{label}")


def whole_bed(result: Result) -> dict:
    """Measure original identities before retirement; births are not displacement.

    Thirds are fixed in initial usable height (floor..initial piston). Spatial
    load reach and original-cohort activity are separate to avoid crediting a
    descending top fragment as activation of an unchanged lower founder.
    """
    initial=json.loads(result.initial)
    founders={b['id']:b for b in initial['balls']}
    height=initial['height']
    names=('lower','middle','upper')
    def third(y):
        return names[max(0,min(2,math.floor(3*y/height)))]
    cohort={k:third(b['y']) for k,b in founders.items()}
    moved_at={};connected_at={};loaded_at={};first_spatial={n:None for n in names}
    founder_activity={n:set() for n in names}
    spatial_activity={n:set() for n in names}
    max_depth=0.
    rupture=min((e.tick for e in result.events if e.kind=='wall_ruptured'),default=None)
    end_tick=rupture if rupture is not None else json.loads(result.final)['tick']
    # Event pre-states include a parent removed on that tick, absent from its
    # committed sample. Inspect the actual pre-transition pose, never a child.
    stream=[(0,initial)]
    stream.extend((json.loads(s)['tick'],json.loads(s)) for s in result.samples)
    stream.extend((e.tick,json.loads(e.before)) for e in result.events
                  if e.kind in ('ball_split','ball_crushed','wall_ruptured'))
    stream.sort(key=lambda item:item[0])
    for tick,state in stream:
        if tick>end_tick:
            continue
        for b in state['balls']:
            k=b['id'];a=state['loads'].get(k,{})
            if k in founders:
                start=founders[k]
                if math.hypot(b['x']-start['x'],b['y']-start['y'])>=.25*start['radius']-1e-12:
                    moved_at.setdefault(k,tick/120)
                if a.get('C',0):
                    connected_at.setdefault(k,tick/120)
            if a.get('L',0)>=MEANINGFUL_LOAD-1e-12:
                band=third(b['y'])
                if first_spatial[band] is None:
                    first_spatial[band]=tick/120
                spatial_activity[band].add(k)
                max_depth=max(max_depth,min(1.,max(0.,(height-b['y'])/height)))
                if k in founders:
                    loaded_at.setdefault(k,tick/120)
                    founder_activity[cohort[k]].add(k)
    count=len(founders)
    before=end_tick/120
    displaced_3=sum(t<=3 for t in moved_at.values())/count
    displaced_before=sum(t<before for t in moved_at.values())/count
    connected=len(connected_at)/count
    return {'schema':'ms06.3b.whole-bed.v1','meaningful_load':MEANINGFUL_LOAD,
            'displacement_threshold_starting_radius_fraction':.25,
            'thirds_basis':'fixed floor..initial actual piston height; lower/middle/upper',
            'initial_count':count,'initial_usable_height':height,
            'displaced_fraction_by_3s':displaced_3,
            'displaced_fraction_before_rupture':displaced_before if rupture is not None else None,
            'displaced_fraction_before_resolution':displaced_before,
            'measurement_end_time':before,
            'measurement_end':'wall_rupture' if rupture is not None else 'terminal_without_rupture',
            'ever_piston_connected_initial_fraction':connected,'meaningful_vertical_depth_fraction':max_depth,
            'first_meaningful_load_by_third':first_spatial,
            'initial_cohorts':{n:{'count':sum(c==n for c in cohort.values()),
                                 'loaded_count':len(founder_activity[n]),
                                 'displaced_count':sum(k in moved_at for k,c in cohort.items() if c==n),
                                 'connected_count':sum(k in connected_at for k,c in cohort.items() if c==n),
                                 'first_meaningful_load':min((loaded_at[k] for k in founder_activity[n]),default=None)}
                               for n in names},
            'spatial_loaded_identity_counts':{n:len(spatial_activity[n]) for n in names},
            'initial_displacement_times':dict(sorted(moved_at.items())),
            'initial_connection_times':dict(sorted(connected_at.items())),
            'initial_meaningful_load_times':dict(sorted(loaded_at.items()))}


def activity_gate(activity, terminal_time):
    first=activity['first_meaningful_load_by_third']
    return {'sixty_percent_displaced_by_3s':activity['displaced_fraction_by_3s']>=.6,
            'seventy_five_percent_before_resolution':activity['displaced_fraction_before_resolution']>=.75,
            'middle_load_by_2_5s':first['middle'] is not None and first['middle']<=2.5,
            'lower_load_before_terminal':first['lower'] is not None and first['lower']<terminal_time,
            'original_lower_cohort_active':activity['initial_cohorts']['lower']['loaded_count']>0}


def evaluate(result):
    summary=summarize(result)
    activity=whole_bed(result)
    summary['whole_bed']=activity
    t=summary['event_times'];split=t.get('ball_split',[]);crush=t.get('ball_crushed',[])
    rupture=t.get('wall_ruptured',[]);wall=t.get('wall_strained',[])
    # An isolated teaching split has >=.15s until another split or crush.
    isolated=any(.8<=s<=1.4 and not any(abs(other-s)<.15-1e-12
                 for other in split if other!=s) and split.count(s)==1
                 and not any(0<=c-s<.15-1e-12 for c in crush) for s in split)
    ag=activity_gate(activity,summary['terminal_time'])
    gate={**ag,'genuine_rupture':summary['outcome']=='rupture',
          'contact_by_0_35':bool(summary['first_contact'] and summary['first_contact']['time']<=.35),
          'early_readable_split':bool(split and .8<=split[0]<=1.4 and isolated),
          'split_count_15_to_30':15<=len(split)<=30,'crush_count_6_to_14':6<=len(crush)<=14,
          'crush_by_8s':bool(crush and any(s<c<=8 for s in split for c in crush)),
          'sustained_strain_before_rupture':bool(rupture and wall and min(wall)<rupture[0]-.39),
          'rupture_9_to_12s':bool(rupture and 9<=rupture[0]<=12),
          'multiple_genuine_escapes':summary['event_counts'].get('ball_escaped',0)>=2,
          'duration_11_to_14':11<=math.ceil((summary['terminal_time']+.5)*30)/30<=14}
    summary['activity_passed']=all(ag.values())
    summary['base_gate']=gate
    summary['passed']=all(gate.values())
    return summary


def _case(item):
    name,cfg=item
    print(f'PB3B {name}: simulation',flush=True)
    result=run(cfg,name);summary=evaluate(result)
    print(f"PB3B {name}: replay {summary['outcome']} at {summary['terminal_time']:.3f}s",flush=True)
    replay=run(cfg,name)
    record={'probe':name,'configuration':cfg,'parameters':asdict(result.parameters),
            'deterministic':result==replay,**summary,
            'semantic_events':[{'sequence':e.sequence,'id':e.id,'tick':e.tick,'kind':e.kind,
                                'payload':json.loads(e.payload)} for e in result.events]}
    return record,result if name=='base' else None


def audit(cfg):
    with ProcessPoolExecutor(max_workers=4) as pool:
        checked=list(pool.map(_case,(('base',cfg),*nearby_probes(cfg))))
    records=[r for r,_ in checked];probes=records[1:]
    valid={'rupture','containment','extinction'}
    gate={'base_scenario':records[0]['passed'],'all_replay':all(r['deterministic'] for r in records),
          'all_finite':all(r['finite'] for r in records),
          'six_valid_probes':sum(p['outcome'] in valid for p in probes)>=6,
          'four_rupture_probes':sum(p['outcome']=='rupture' for p in probes)>=4,
          'at_most_two_failed_probes':sum(p['outcome'] not in valid for p in probes)<=2,
          'five_whole_bed_split_later_crush':sum(p['activity_passed'] and p['split_then_crush'] for p in probes)>=5}
    return {'schema':'ms06.3b.robustness.v1','rules':'PB-1.1','scenario_sha256':digest(cfg),
            'engine_sha256':hashlib.sha256(Path(__file__).with_name('pressure_bloom.py').read_bytes()).hexdigest(),
            'status':'directed rupture prototype; not an automatically generated candidate',
            'passed':all(gate.values()),'gate':gate,'results':records},checked[0][1]
