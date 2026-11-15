"""Capacity truth, cadences, terminal reachability and layout separation."""
import ast
import copy
import json
import math
from pathlib import Path

import pytest

from inception.capacity_bloom import RULES, ball_record, digest, simulate
from inception.capacity_layout import layout
from inception.ms06_pb2 import conformance, FIXTURE


@pytest.fixture(scope='module')
def proof():
    return conformance(historical=False)


def case(proof,name):
    return next(x for x in proof['scenarios'] if x['configuration']['id']==f'pb2.{name}.v1')


def test_conformance_all_gates(proof):
    assert proof['passed'] and all(proof['reachability_matrix'].values())
    assert json.loads((FIXTURE.parent/'pb2-rules-v1.json').read_text())==RULES


def test_seeded_resistance_is_color_neutral_and_children_derive_their_own(proof):
    cfg=case(proof,'split')['configuration'];b=cfg['balls'][0]
    a=ball_record(b,cfg['seed']);b2={**b,'lineage':'different'}
    other=ball_record(b2,cfg['seed'])
    assert a['resistance']==other['resistance'] and a['affinity']==other['affinity']
    e=next(e for e in case(proof,'split')['simulation']['events'] if e['kind']=='ball_split')
    for child in e['payload']['children']:
        assert child==ball_record(child,cfg['seed'])
        assert child['resistance']!=e['payload']['parent']['resistance']
        assert child['generation']==e['payload']['parent']['generation']+1


def test_split_cadence_area_and_immutable_records(proof):
    s=case(proof,'split')['simulation'];events=[e for e in s['events'] if e['kind']=='ball_split']
    assert len(events)==4
    assert all(b['tick']-a['tick']>=34 for a,b in zip(events,events[1:]))
    for e in events:
        p=e['payload']['parent'];children=e['payload']['children']
        assert all(c['lineage']==p['lineage'] and c['radius']==p['radius']*.75 for c in children)
        assert math.isclose(e['after']['capacity']['occupied_area']-e['before']['capacity']['occupied_area'],math.pi*p['radius']**2*.125,rel_tol=1e-12)
    r=simulate(case(proof,'split')['configuration'])
    mutated=r.to_dict();mutated['events'].clear()
    assert len(r.events)==len(s['events'])


def test_crush_is_real_area_release_and_reversal_is_not_color_targeting(proof):
    s=case(proof,'reversal')['simulation']
    crushes=[e for e in s['events'] if e['kind']=='ball_crushed']
    assert len(crushes)==2 and s['final']['balls'][0]['lineage']=='orange'
    for e in crushes:
        assert e['payload']['R_after']<e['payload']['R_before']
        assert e['payload']['ball']['id'] not in {b['id'] for b in e['after']['balls']}
    cfg=copy.deepcopy(case(proof,'reversal')['configuration'])
    for b in cfg['balls']:b['lineage']='orange' if b['lineage']=='cyan' else 'cyan'
    swapped=simulate(cfg).to_dict()
    assert [e['payload']['ball']['id'] for e in swapped['events'] if e['kind']=='ball_crushed']==[e['payload']['ball']['id'] for e in crushes]


def test_wall_arithmetic_and_sustained_rupture(proof):
    s=case(proof,'rupture')['simulation'];e=next(e for e in s['events'] if e['kind']=='wall_ruptured')
    wall=e['payload']['qualified_capacity']['walls'][e['payload']['section']]
    assert math.isclose(wall['assigned_area'],sum(c['assigned_area'] for c in wall['contributions']))
    assert wall['W']>=.8 and e['tick']>=48
    for state in s['states'][e['tick']-48:e['tick']-1]:
        assert state['capacity']['walls'][e['payload']['section']]['W']>=.8
    assert not any(x['kind'] in ('ball_split','ball_crushed','wall_strained') for x in s['events'] if x['tick']>e['tick'])
    actual={b['id'] for b in e['after']['balls']}
    assert all(x['payload']['ball']['id'] in actual for x in s['events'] if x['kind']=='ball_escaped')


def test_terminal_outcomes_limits_and_event_sequence(proof):
    assert {r['simulation']['final']['outcome'] for r in proof['scenarios']}=={'rupture','containment','extinction','draw','invalid'}
    for r in proof['scenarios']:
        s=r['simulation'];assert [e['sequence'] for e in s['events']]==list(range(len(s['events'])))
        assert all(e['time']==e['tick']/120 for e in s['events'])
        assert all(len(x['balls'])<=96 and all(b['generation']<=3 for b in x['balls']) for x in s['states'])
    cfg=copy.deepcopy(case(proof,'contain')['configuration']);cfg['balls'][0]['radius']=float('nan')
    assert json.loads(simulate(cfg).final)['outcome']=='invalid'


def test_layout_success_failure_and_layout_seed_leave_truth_unchanged(proof):
    cfg=case(proof,'rupture')['configuration'];r=simulate(cfg);s=r.to_dict();h=digest(s)
    a=layout(s,4);b=layout(s,4)
    assert a==b and a['status']=='passed'
    assert layout(s,force_failure=True)['status']=='failed'
    assert digest(s)==h and simulate(cfg)==r
    for frame in a['frames']:
        k=min(frame['tick'],len(s['states']))
        logical=s['initial'] if k==0 else s['states'][k-1]
        assert [(b['id'],b['radius'],b['status']) for b in frame['balls']]==[(b['id'],b['radius'],b['status']) for b in logical['balls']]


def test_rule_engine_imports_no_layout_media_or_frame_clock():
    p=FIXTURE.parents[1].parent/'src/inception/capacity_bloom.py'
    tree=ast.parse(p.read_text())
    imports={n.module for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)}
    imports|={x.name for n in ast.walk(tree) if isinstance(n,ast.Import) for x in n.names}
    assert imports <= {'__future__','dataclasses','hashlib','json','math'}
    assert 'fps' not in p.read_text().lower()
