"""PB-1.2 reachability, arithmetic, state provenance and PB-1.1 byte compatibility."""
import ast
from concurrent.futures import ProcessPoolExecutor
from dataclasses import FrozenInstanceError, replace
import hashlib
import json
import math
from pathlib import Path

import pytest

from inception.ms06_2b import check_expected, compatibility, load_fixture, prove, run_case, sha
from inception.pressure_bloom import Ball, Parameters, encoded
from inception.pressure_bloom_v12 import Parameters12, simulate

ROOT=Path(__file__).parents[1]


@pytest.fixture(scope='module')
def cases():
    fixtures=load_fixture()['scenarios']
    with ProcessPoolExecutor(max_workers=4) as pool:
        results=list(pool.map(run_case,fixtures))
    return {c['id'].split('.')[1]:(c,r) for c,r in zip(fixtures,results)}


def data(cases,name):return cases[name][1].to_dict()

def events(s,kind):return [e for e in s['events'] if e['kind']==kind]


def test_fixture_expectations_and_reachability(cases):
    records=[]
    for cfg,result in cases.values():
        simulation=check_expected(cfg,result)
        records.append({'configuration':cfg,'simulation':simulation})
    assert all(prove(records).values())


def test_version_identity_and_immutable_complete_logs(cases):
    for _,r in cases.values():
        s=r.to_dict()
        assert s['rules']==s['parameters']['rules_version']=='PB-1.2'
        assert [e['sequence'] for e in s['events']]==list(range(len(s['events'])))
        assert len({e['id'] for e in s['events']})==len(s['events'])
        assert [e['tick'] for e in s['events']]==sorted(e['tick'] for e in s['events'])
        for e in s['events']:
            assert e['rules']==e['before']['rules']==e['after']['rules']=='PB-1.2'
        for state in [s['initial'],*s['samples'],s['final']]:
            assert state['rules']=='PB-1.2'
        assert len(s['events'])<=r.parameters.max_events
        if r.samples:assert r.samples[-1]==r.final
    r=cases['rupture-escape'][1]
    with pytest.raises(FrozenInstanceError):r.seed=42
    with pytest.raises(TypeError):simulate((Ball('r000','cyan',.5,.3),),Parameters())


def test_debt_is_only_derived_from_current_anchored_positions(cases):
    for _,r in cases.values():
        for state in map(json.loads,r.samples):
            p=state['piston'];first=state['first_contact'];ramp=r.parameters.drive_ramp_distance
            achieved=max(0.,first['height']-p['achieved_position']) if first else 0.
            commanded=max(0.,first['command_height']-p['commanded_position']) if first else 0.
            assert p['achieved_travel']==achieved and p['commanded_travel']==commanded
            assert p['debt']==min(ramp,max(0.,commanded-achieved))
            assert p['D']==min(1.,max(0.,(achieved+p['debt'])/ramp))
            for a in state['loads'].values():
                assert a['L']==a['C']*a['D']*min(1.,a['weight']/4)
                assert a['C'] in (0,1)
            if not first:assert p['debt']==p['D']==0
    jam=data(cases,'jam-pressure');touch=events(jam,'piston_first_contact')[0]
    assert touch['after']['piston']['D']==touch['after']['piston']['debt']==0
    assert events(jam,'compression_debt_positive')
    history=[s for s in jam['samples'] if s['tick']>=touch['tick']]
    assert max(s['height'] for s in history)-min(s['height'] for s in history)<1e-5
    assert history[-1]['piston']['D']>history[0]['piston']['D']+.5
    # Once the command stops, waiting alone cannot accumulate extra pressure.
    held=[s['piston']['D'] for s in history if s['time']>=1.]
    assert max(held)-min(held)<1e-10


def test_crush_removes_resistance_and_bounded_catchup_reduces_debt(cases):
    s=data(cases,'crush-release');e=events(s,'ball_crushed')[0]
    assert e['payload']['qualification']['L']>=.9
    assert e['payload']['duration_ticks']==18
    assert e['after']['occupied_area']<e['before']['occupied_area']
    assert e['after']['live_count']==e['before']['live_count']-1
    assert events(s,'piston_unblocked') and events(s,'compression_debt_cleared')
    following=[x for x in s['samples'] if x['tick']>e['tick']]
    assert min(x['piston']['debt'] for x in following)==0
    assert following[-1]['piston']['achieved_travel']>.14
    last=s['initial']['height']
    for x in s['samples']:
        assert -1e-12<=last-x['height']<=.4/120+1e-12
        last=x['height']
    assert s['final']['outcome']=='containment'


def test_settling_has_its_own_clock_hash_and_unchanged_identities(cases):
    cfg,r=cases['settling'];s=r.to_dict();p=s['settlement']
    assert p['summary']['status']=='completed' and 0<p['summary']['elapsed']<=20
    assert p['summary']['settled_state_sha256']==sha(p['frozen_state'])
    stable=p['samples'][-31:]
    assert len(stable)==31 and stable[-1]['stable_intervals']==30
    assert all(x['max_speed']<=r.parameters.settling_speed_tolerance
               and x['max_penetration']<=r.parameters.settling_penetration_tolerance for x in stable)
    keys=('id','lineage','generation','parent','parent_generation','radius')
    assert sorted(tuple(b[k] for k in keys) for b in cfg['balls'])==sorted(
        tuple(b[k] for k in keys) for b in p['frozen_state']['balls'])
    assert s['initial']['time']==s['initial']['tick']==0
    assert s['events'][0]['kind']=='settling_started'
    complete=events(s,'settling_completed')[0]
    assert complete['tick']==0 and complete['phase']=='settling'
    assert complete['after']['clocks']==complete['after']['wall_clocks']=={}
    assert run_case(cfg)==r
    failed=data(cases,'settling-failure')
    assert failed['final']['outcome']=='invalid' and failed['samples']==[]
    assert failed['final']['reason']=='settling_time_limit'
    assert not events(failed,'press_engaged')


def test_wall_contributions_are_actual_directional_contacts(cases):
    for name in ('sub-strain','wall-strain','rupture-escape'):
        s=data(cases,name);p=s['parameters']
        for state in s['samples']:
            balls={b['id']:b for b in state['balls']}
            for section,w in state['walls'].items():
                assert w['W']==min(1.,max(0.,sum(c['contribution'] for c in w['contributions'])/2.5))
                for c in w['contributions']:
                    b=balls[c['ball']]
                    assert c['contribution']==state['loads'][b['id']]['L']*b['radius']/p['reference_radius']
                    assert c['normal']==([1.,0.] if section[0]=='L' else [-1.,0.])
                    assert c['contact_point']==[0. if section[0]=='L' else p['width'],b['y']]
                    assert min(3,math.floor(c['contact_point'][1]/(p['height']/4)))==int(section[1])
                    distance=b['x'] if section[0]=='L' else p['width']-b['x']
                    assert distance<=b['radius']+1e-6
    wall=data(cases,'wall-strain')
    assert events(wall,'wall_strained') and not events(wall,'wall_ruptured')
    assert .6<=max(s['walls']['L0']['W'] for s in wall['samples'])<.8


def test_rupture_is_latched_and_release_records_real_crossings(cases):
    s=data(cases,'rupture-escape');r=events(s,'wall_ruptured')[0]
    assert r['payload']['section']=='L0' and r['payload']['qualification']['W']>=.8
    assert r['before']['wall_clocks']['L0']==48
    assert events(s,'wall_rupture_qualified')[0]['tick']==r['tick']
    escaped=events(s,'ball_escaped')
    assert len(escaped)==8
    for e in escaped:
        b=next(b for b in e['after']['balls'] if b['id']==e['payload']['ball'])
        assert b['status']=='escaped' and b['x']+b['radius']<=0
        assert e['payload']['previous_position'][0]+b['radius']>0
    assert s['final']['tick']-r['tick']==72 and s['final']['escaped_count']==8
    for x in s['samples']:
        if x['tick']>=r['tick']:
            assert x['height']==r['after']['height']
            assert x['piston']['commanded_position']==r['after']['piston']['commanded_position']
            assert x['clocks']==x['wall_clocks']=={}
            assert all(a['L']==0 for a in x['loads'].values())
    assert {e['kind'] for e in s['events'] if e['sequence']>r['sequence']}<= {'ball_escaped','rupture_resolved'}


def test_numeric_invalid_and_terminal_paths_are_honest(cases):
    for name,(_,r) in cases.items():
        s=r.to_dict();f=s['final']
        assert f['outcome'] in ('rupture','containment','draw','invalid','extinction')
        if f['outcome'] in ('draw','invalid'):
            assert f['reason'] and not f['presentation_eligible']
            assert not any(e['kind'] in ('rupture_resolved','chamber_contained') for e in s['events'])
        for x in s['samples']:
            assert len(x['balls'])<=96 and all(b['generation']<=3 for b in x['balls'])
            assert all(math.isfinite(v) for b in x['balls'] for v in (b['x'],b['y'],b['radius'],b['vx'],b['vy']))
    invalid=data(cases,'invalid-nonfinite')
    assert invalid['final']['balls'][0]['x']=='nan'
    p=Parameters12(max_events=2)
    r=simulate((Ball('r000','cyan',.5,.3),),p)
    assert json.loads(r.final)['outcome']=='invalid'
    assert json.loads(r.final)['reason']=='settling_event_limit'
    assert len(r.events)<=2
    invalid=simulate((Ball('r000','cyan',.5,.3),),Parameters12(drive_ramp_distance=0))
    assert json.loads(invalid.final)['outcome']=='invalid'


def test_same_tick_crush_cannot_cancel_qualified_wall(cases):
    s=data(cases,'same-tick-crush-rupture')
    crush=events(s,'ball_crushed')[0]
    rupture=events(s,'wall_ruptured')[0]
    assert crush['tick']==rupture['tick']==160
    assert crush['sequence']<rupture['sequence']
    assert crush['after']['walls']['L0']['W']<.8
    assert rupture['payload']['qualification']['W']>=.8
    assert s['final']['escaped_count']==7 and s['final']['outcome']=='rupture'


def test_pb11_compatibility_without_regenerating_its_output():
    p=ROOT/'outputs/ms06.2/ms06.2-conformance-v1.json'
    before=p.read_bytes()
    assert compatibility()['byte_identical']
    assert p.read_bytes()==before
    manifest=json.loads((ROOT/'outputs/ms06.3/ms06.3-manifest.json').read_text())
    old_source=ROOT/'src/inception/pressure_bloom.py'
    assert hashlib.sha256(old_source.read_bytes()).hexdigest()==manifest['source_sha256']['pressure_bloom.py']


def test_pure_engine_has_no_renderer_audio_fps_or_services():
    import inception.pressure_bloom_v12 as module
    tree=ast.parse(Path(module.__file__).read_text())
    imports={n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)}
    imports|={p.name for n in ast.walk(tree) if isinstance(n,ast.Import) for p in n.names}
    assert imports<= {'__future__','dataclasses','hashlib','json','math','pressure_bloom'}
    with pytest.raises(TypeError):Parameters12(fps=30)


def test_actuator_limit_cannot_create_false_free_motion_pressure():
    params=Parameters12(schedule=((0.,.6),(.1,.3)))
    r=simulate((Ball('r000','cyan',.5,.3),),params)
    assert json.loads(r.final)['outcome']=='invalid'
    assert json.loads(r.final)['reason']=='command_exceeds_bounded_free_speed'
    assert not r.samples


def test_pb12_multiplication_retains_lineage_area_and_generation_limit(cases):
    s=data(cases,'split-generation-control')
    splits=events(s,'ball_split')
    assert len(splits)==7 and len(s['final']['balls'])==8
    assert all(b['generation']==3 for b in s['final']['balls'])
    for e in splits:
        p=e['payload'];parent=p['parent'];children=p['birth_children']
        assert e['before']['clocks'][parent['id']+':split']==36
        assert all(b['lineage']==parent['lineage']=='cyan' and b['generation']==parent['generation']+1 for b in children)
        assert sum(b['radius']**2 for b in children)/parent['radius']**2==pytest.approx(1.125)
        assert math.dist((children[0]['x'],children[0]['y']),(children[1]['x'],children[1]['y']))==pytest.approx(1.3*parent['radius'])
    assert s['final']['outcome']=='draw' and s['final']['reason']=='duration_limit'
