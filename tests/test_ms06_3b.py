"""MS06.3B measurement honesty and fail-closed scenario acceptance."""
from dataclasses import replace
import json
from pathlib import Path

from inception.pressure_bloom import Event, Parameters, Result, encoded
from inception.ms06_2 import load_fixture, run_scenario
from inception.ms06_3b_scenario import activity_gate, evaluate, whole_bed
from inception.ms06_3_scenario import nearby_probes

ROOT=Path(__file__).resolve().parents[1]


def ball(k,x,y,r=.08):
    return {'id':k,'x':x,'y':y,'radius':r}


def state(tick,balls,loads=None,height=1.):
    return {'tick':tick,'height':height,'balls':balls,'loads':loads or {}}


def result(initial,samples,events=()):
    return Result('measurement-unit',6302,Parameters(),encoded(initial),tuple(events),
                  tuple(encoded(s) for s in samples),encoded(samples[-1]))


def test_children_do_not_inflate_initial_displacement_or_connection():
    initial=state(0,[ball('parent',.5,.6)])
    pre=state(12,[ball('parent',.519,.6)],{'parent':{'C':0,'L':0}})
    post=state(12,[ball('parent.0',.1,.2),ball('parent.1',.9,.2)],
               {'parent.0':{'C':1,'L':.75},'parent.1':{'C':1,'L':.75}})
    end={**post,'tick':360,'outcome':'containment'}
    birth=Event(0,'unit:0',12,'ball_split','{}',encoded(pre),encoded(post))
    a=whole_bed(result(initial,[post,end],[birth]))
    assert a['displaced_fraction_by_3s']==0
    assert a['ever_piston_connected_initial_fraction']==0
    assert a['initial_cohorts']['middle']['loaded_count']==0
    assert a['displaced_fraction_before_rupture'] is None
    assert a['measurement_end']=='terminal_without_rupture'


def test_retired_parent_pre_event_pose_counts_at_exact_threshold():
    initial=state(0,[ball('parent',.5,.6)])
    pre=state(36,[ball('parent',.52,.6)],{'parent':{'C':1,'L':.5}})
    post=state(36,[ball('parent.0',.46,.6),ball('parent.1',.58,.6)])
    end={**post,'tick':360,'outcome':'containment'}
    e=Event(0,'unit:0',36,'ball_split','{}',encoded(pre),encoded(post))
    a=whole_bed(result(initial,[post,end],[e]))
    assert a['displaced_fraction_by_3s']==1
    assert a['initial_displacement_times']=={'parent':.3}
    assert a['ever_piston_connected_initial_fraction']==1


def test_thirds_are_fixed_and_connected_is_not_loaded():
    balls=[ball('low',.2,.1),ball('mid',.5,.5),ball('high',.8,.9)]
    initial=state(0,balls)
    sample=state(240,balls,{'low':{'C':1,'L':.49},'mid':{'C':1,'L':.5},
                            'high':{'C':1,'L':0}},height=.5)
    end={**sample,'tick':360,'outcome':'draw'}
    a=whole_bed(result(initial,[sample,end]))
    assert a['first_meaningful_load_by_third']=={'lower':None,'middle':2.,'upper':None}
    assert a['ever_piston_connected_initial_fraction']==1
    assert a['meaningful_vertical_depth_fraction']==.5
    assert a['initial_cohorts']['lower']['loaded_count']==0
    gate=activity_gate(a,3.)
    assert gate['middle_load_by_2_5s'] and not gate['lower_load_before_terminal']
    assert not all(gate.values())


def test_release_motion_cannot_rescue_pre_rupture_activity():
    initial=state(0,[ball('a',.5,.1)])
    pre=state(120,[ball('a',.5,.1)],{'a':{'C':1,'L':.75}})
    end=state(192,[ball('a',-.2,.1)],height=1.)
    end['outcome']='rupture'
    e=Event(0,'unit:0',120,'wall_ruptured','{}',encoded(pre),encoded(pre))
    a=whole_bed(result(initial,[pre,end],[e]))
    assert a['displaced_fraction_before_rupture']==0
    assert a['displaced_fraction_by_3s']==0
    assert a['measurement_end_time']==1.


def test_existing_fast_rupture_cannot_be_relabeled_as_qualifying_prototype():
    fixture=load_fixture(ROOT/'fixtures/ms06.2/conformance-v1.json')['scenarios'][2]
    r=run_scenario(fixture)
    s=evaluate(r)
    assert s['outcome']=='rupture' and s['event_counts']['ball_escaped']==4
    assert s['base_gate']['genuine_rupture']
    assert not s['base_gate']['rupture_9_to_12s']
    assert not s['base_gate']['duration_11_to_14']
    assert not s['passed']
    assert run_scenario(fixture)==r


def test_nearby_probe_definitions_are_repeatable_and_do_not_change_rules():
    cfg={'balls':[{'x':.2,'y':.2},{'x':.4,'y':.5}],
         'parameters':{'schedule':[[0,1],[10,.5]],'drive_ramp_distance':.16}}
    a,b=nearby_probes(cfg),nearby_probes(cfg)
    assert a==b and len(a)==8
    for _,p in a:
        assert p['parameters']['drive_ramp_distance']==.16
        assert len(p['balls'])==2
