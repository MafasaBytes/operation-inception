"""MS06.3 truth boundary and one directed-prototype review contract."""
import ast
from dataclasses import FrozenInstanceError
import hashlib
import json
from pathlib import Path

import numpy as np
import pytest

from inception.ms06_2 import load_fixture, run_scenario
from inception.ms06_3 import file_hash, freeze_audited, inspect_media
from inception.ms06_3_scenario import _check_case, digest, load_scenario, nearby_probes
from inception.pressure_audio import RATE, map_events, synthesize
from inception.pressure_presentation import FrozenTape, PressureRenderer, canonical, sha

ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT/'outputs/ms06.3'


@pytest.fixture(scope='module')
def synthetic_record():
    # Unit-only short engine trace with an extended display window. This is not
    # the directed prototype, a content candidate, or an exported media fixture.
    case = load_fixture(ROOT/'fixtures/ms06.2/conformance-v1.json')['scenarios'][1]
    result = run_scenario(case)
    sim = result.to_dict()
    return {'schema':'ms06.3.frozen-timeline.v1','rules':'PB-1.1','simulation':sim,
            'simulation_sha256':sha(sim),'event_sha256':sha(sim['events']),
            'presentation':{'width':720,'height':1280,'fps':30,'duration':14.,'frame_count':420}}


def test_frozen_truth_rejects_mutations_and_missing_ticks(synthetic_record):
    tape = FrozenTape.from_record(synthetic_record)
    with pytest.raises(FrozenInstanceError):
        tape.duration = 15
    changed = json.loads(canonical(synthetic_record))
    changed['simulation']['final']['balls'][0]['x'] += .1
    with pytest.raises(ValueError,match='hash mismatch'):
        FrozenTape.from_record(changed)
    changed = json.loads(canonical(synthetic_record))
    changed['simulation']['samples'].pop(10)
    changed['simulation_sha256'] = sha(changed['simulation'])
    with pytest.raises(ValueError,match='Missing committed'):
        FrozenTape.from_record(changed)


def test_live_identities_follow_events_without_render_invention(synthetic_record):
    tape = FrozenTape.from_record(synthetic_record)
    assert {b['id'] for b in tape.state_at(.699)['balls']} == {'r000','r001'}
    assert {b['id'] for b in tape.state_at(.7)['balls']} == {'r000.0','r000.1','r001'}
    assert {b['id'] for b in tape.state_at(1.05)['balls']} == {'r001'}
    assert tape.state_at(1.05)['retired']['r000.0']['status'] == 'crushed'
    assert tape.state_at(10)['balls'] == json.loads(tape.final)['balls']


def test_renderer_never_imports_or_calls_simulation(synthetic_record, monkeypatch):
    from inception import pressure_bloom, pressure_presentation
    tree = ast.parse(Path(pressure_presentation.__file__).read_text())
    imports = [n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
    assert not any('pressure_bloom' in n or 'audio' in n for n in imports)
    assert not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and n.func.attr=='text'
                   for n in ast.walk(tree))
    tape = FrozenTape.from_record(synthetic_record)
    monkeypatch.setattr(pressure_bloom,'simulate',lambda *a,**k:pytest.fail('Renderer advanced rules'))
    renderer = PressureRenderer(tape)
    for t in (0,.7,1.,1.5):
        a,b=renderer.render(t),renderer.render(t)
        assert a.size == (720,1280) and a.mode == 'RGB'
        assert a.tobytes() == b.tobytes()
    assert renderer.render(2).tobytes() == renderer.render(8).tobytes()
    assert renderer.render(0).tobytes() != renderer.render(.8).tobytes()


def test_audio_tracks_genuine_absolute_events_and_repeats(synthetic_record):
    tape = FrozenTape.from_record(synthetic_record)
    cues = map_events(tape.events)
    event_by_id={e['id']:e for e in synthetic_record['simulation']['events']}
    for cue in cues:
        assert cue.event_id in event_by_id
        if cue.kind in ('split','crush','containment'):
            assert cue.time == event_by_id[cue.event_id]['time']
    assert sum(c.kind=='split' for c in cues)==1
    assert sum(c.kind=='crush' for c in cues)==2
    a,report = synthesize(tape.events,tape.duration,6305)
    b,again = synthesize(tape.events,tape.duration,6305)
    assert np.array_equal(a,b) and report==again
    assert a.shape==(14*RATE,2) and a.dtype==np.dtype('<i2')
    assert np.isfinite(a).all() and 0<report['peak']<1
    assert 0<report['master_gain']<=1 and report['mono_rms']>0
    assert {c.frequency for c in cues if c.kind=='split'} != {c.frequency for c in cues if c.kind=='crush'}


def test_eight_local_probes_are_explicit_and_repeatable():
    cfg = load_scenario(ROOT/'configs/ms06.3.json')
    first,second = nearby_probes(cfg),nearby_probes(cfg)
    assert first==second and len(first)==8
    assert len({name for name,_ in first})==8
    for name,p in first:
        assert p['seed']==cfg['seed'] and p['rules']==cfg['rules']
        assert len(p['balls'])==len(cfg['balls'])==36
        for b,original in zip(p['balls'],cfg['balls']):
            assert {k:v for k,v in b.items() if k not in ('x','y')} == {k:v for k,v in original.items() if k not in ('x','y')}
        assert p['parameters']['drive_ramp_distance']==.16
    assert digest(cfg)==digest(load_scenario(ROOT/'configs/ms06.3.json'))


def test_audit_replays_actual_engine_and_blocks_failed_gate():
    fixture=load_fixture(ROOT/'fixtures/ms06.2/conformance-v1.json')['scenarios'][0]
    cfg={'id':'unit-audit','seed':fixture['seed'],'balls':fixture['balls'],'parameters':fixture['parameters']}
    record,_=_check_case(('unit',cfg))
    assert record['deterministic'] and record['finite'] and record['outcome']=='containment'
    with pytest.raises(ValueError,match='gate failed'):
        freeze_audited(cfg,{'passed':False},None,'irrelevant')


def review_manifest():
    path=OUTPUT/'ms06.3-manifest.json'
    if not path.exists():
        pytest.skip('Review integration requires a locally generated gate-passing package')
    return json.loads(path.read_text())


def test_real_frozen_review_and_robustness_records_agree():
    m=review_manifest()
    report=json.loads((OUTPUT/'ms06.3-robustness.json').read_text())
    record=json.loads((OUTPUT/'ms06.3-timeline.json').read_text())
    tape=FrozenTape.from_record(record)
    assert report['passed'] and all(report['gate'].values())
    assert all(r['deterministic'] and r['finite'] for r in report['results'])
    probes=report['results'][1:]
    assert len(probes)==8
    assert sum(p['outcome'] in ('rupture','containment','extinction') for p in probes)>=6
    assert sum(p['split_then_crush'] for p in probes)>=5
    assert file_hash(ROOT/'configs/ms06.3.json')==m['configuration_file_sha256']
    assert tape.simulation_sha256==m['simulation_sha256']==report['results'][0]['simulation_sha256']
    assert tape.event_sha256==m['event_sha256']
    assert m['status']=='owner-and-wife normal-speed phone review pending'
    renderer=PressureRenderer(tape)
    for time,expected in m['frame_sha256'].items():
        assert hashlib.sha256(renderer.render(float(time)).tobytes()).hexdigest()==expected
    for name,expected in m['files'].items():
        assert file_hash(OUTPUT/name)==expected['sha256']
        assert (OUTPUT/name).stat().st_size==expected['bytes']


def test_actual_media_fully_decodes_and_shares_encoded_video():
    m=review_manifest()
    sound=inspect_media(OUTPUT/'ms06.3-review.mp4')
    muted=inspect_media(OUTPUT/'ms06.3-muted.mp4')
    assert sound['video_stream_sha256']==muted['video_stream_sha256']
    assert any(s['codec_type']=='audio' and s['sample_rate']=='48000' and s['channels']==2
               for s in sound['probe']['streams'])
    assert not any(s['codec_type']=='audio' for s in muted['probe']['streams'])
    for result in (sound,muted):
        video=next(s for s in result['probe']['streams'] if s['codec_type']=='video')
        assert int(video['nb_frames'])==m['frame_count']
        assert float(video['duration'])==pytest.approx(m['duration'],abs=.0001)
