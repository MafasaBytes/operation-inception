"""Pre-render PB-1.2 scene gates; no media is made by these tests."""
from dataclasses import asdict
import hashlib
import json
from pathlib import Path

import pytest

from inception.ms06_3c_scenario import audit, evaluate, resistance_certificate, run
from inception.ms06_3_scenario import nearby_probes
from inception.ms06_2b import load_fixture, run_case

ROOT=Path(__file__).parents[1]


def micro_configuration():
    case=next(c for c in load_fixture()['scenarios'] if c['id']=='pb12.crush-release.v1')
    return {'id':'ms06.3c-unit','rules':'PB-1.2','seed':case['seed'],
            'balls':case['balls'],'parameters':case['parameters']}


def test_observation_does_not_change_any_simulation_byte():
    cfg=micro_configuration()
    observed,extra=run(cfg,'unit')
    vanilla=run(cfg,'unit',observed=False)
    assert observed==vanilla
    assert extra['samples'] and extra['constraint_trials']
    assert max(x['max_penetration'] for x in extra['samples'])<=1e-6
    assert all(x['nonprogress_counter']>=0 for x in extra['samples'])


def test_contact_resistance_certificate_uses_real_support():
    record=json.loads((ROOT/'outputs/ms06.2b/ms06.2b-conformance-v1.json').read_text())
    sim=next(c['simulation'] for c in record['scenarios'] if c['configuration']['id']=='pb12.rupture-escape.v1')
    rupture=next(e for e in sim['events'] if e['kind']=='wall_ruptured')
    result=resistance_certificate(rupture['before'])
    assert result['applicable'] and result['passed']
    assert result['normalized_residual']<=result['tolerance']
    unsupported={'balls':[{'id':'floating','status':'inside','x':.5,'y':.9,'radius':.1}],
                 'loads':{'floating':{'neighbors':[],'piston':1,'floor':0}},'walls':{}}
    assert not resistance_certificate(unsupported)['passed']


def test_too_short_containment_is_never_accepted_as_rupture_scene():
    cfg=micro_configuration();result,extra=run(cfg,'gate-unit')
    s=evaluate(result,extra)
    assert s['outcome']=='containment' and not s['passed']
    assert not s['base_gate']['genuine_rupture']
    assert not s['base_gate']['split_count_15_to_30']
    assert s['numerical_integrity']['gate']['no_command_policy_rejection']
    assert s['whole_bed']['displaced_fraction_before_rupture'] is None
    extra['samples'][0]['max_penetration']=.51*extra['samples'][0]['minimum_radius']
    failed=evaluate(result,extra)
    assert not failed['numerical_integrity']['gate']['valid_committed_geometry']


def test_failed_base_blocks_freeze_and_all_probes():
    report,result=audit(micro_configuration())
    assert not report['passed'] and not report['base_frozen']
    assert report['probe_status']=='not_run_base_gate_failed' and report['probes']==[]
    assert report['base']['replay_identical']
    assert json.loads(result.final)['outcome']=='containment'


def test_nearby_probes_are_eight_deterministic_input_perturbations():
    cfg=micro_configuration();a=nearby_probes(cfg);b=nearby_probes(cfg)
    assert a==b and len(a)==8
    assert len({name for name,_ in a})==8
    for name,p in a:
        assert p['parameters']['rules_version']=='PB-1.2'
        assert p['parameters']['wall_capacity']==2.5
        assert p['parameters']['drive_ramp_distance']==cfg['parameters']['drive_ramp_distance']
        assert all(x['lineage']==y['lineage'] and x['generation']==y['generation'] and x['radius']==y['radius']
                   for x,y in zip(p['balls'],cfg['balls']))
