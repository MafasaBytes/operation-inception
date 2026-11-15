"""One PB-2.0 prototype: frozen truth, review gates and exported media."""
from dataclasses import replace
import ast
import copy
import hashlib
import json
import wave
from pathlib import Path

import numpy as np
import pytest

from inception.capacity_bloom import RULES,digest,simulate
from inception.capacity_layout import layout
from inception.capacity_presentation import Tape,Renderer
from inception.capacity_audio import map_events,synthesize
from inception.ms06_3d_scenario import base_gate,nearby,summary
from inception.ms06_3d import file_hash,inspect_media

ROOT=Path(__file__).parents[1];OUT=ROOT/'outputs/ms06.3d'


@pytest.fixture(scope='module')
def frozen():
    path=OUT/'ms06.3d-timeline.json'
    if not path.exists():pytest.skip('No gate-passing frozen prototype')
    record=json.loads(path.read_text());return record,Tape.from_record(record)


def test_directed_scenario_replays_complete_truth_and_frozen_constants(frozen):
    r,t=frozen;cfg=json.loads((ROOT/'configs/ms06.3d.json').read_text())
    assert simulate(cfg).to_dict()==r['simulation']
    assert r['constants']==RULES and digest(RULES)==r['rules_sha256']
    assert all(base_gate(summary(r['simulation'])).values())
    bad=copy.deepcopy(r);bad['simulation']['final']['outcome']='containment'
    with pytest.raises(ValueError,match='hash'):Tape.from_record(bad)


def test_robustness_eight_exact_probes_and_layout_independence(frozen):
    r,t=frozen;report=json.loads((OUT/'ms06.3d-robustness.json').read_text())
    assert report['passed'] and all(report['gate'].values()) and len(report['probes'])==8
    assert report['base_replay_identical']
    assert all(p['deterministic'] and p['finite'] and p['layout_status']=='passed' for p in report['probes'])
    assert [name for name,_ in nearby(r['configuration'])]==[p['probe'] for p in report['probes']]
    offset=next(p for p in report['probes'] if p['probe']=='initial-layout-offset')
    assert offset['events_sha256']==report['base']['events_sha256']
    before=digest(r['simulation']);assert layout(r['simulation'],force_failure=True)['status']=='failed'
    assert digest(r['simulation'])==before


def test_frozen_frames_deterministic_and_never_call_engine(frozen,monkeypatch):
    import inception.capacity_bloom as engine
    r,t=frozen
    def forbidden(*a,**k):raise AssertionError('Renderer advanced rules')
    monkeypatch.setattr(engine,'simulate',forbidden)
    a=Renderer(t,1);b=Renderer(t,1)
    for seconds in (0.,1.1,5.4,10.6,11.4):
        assert a.render(seconds).tobytes()==b.render(seconds).tobytes()
    assert a.render(11.4).tobytes()==a.render(t.duration-.001).tobytes()


def test_split_crush_and_wall_visual_facts_come_from_real_log(frozen):
    r,t=frozen;renderer=Renderer(t,1)
    assert len(renderer.splits)==24 and len(renderer.crushes)==9
    first=renderer.splits[0];assert first['time']==1.05
    filtered=replace(t,events=tuple(e for e in t.events if json.loads(e)['kind']!='ball_split'))
    assert renderer.render(1.08).tobytes()!=Renderer(filtered,1).render(1.08).tobytes()
    rupture=next(e for e in r['simulation']['events'] if e['kind']=='wall_ruptured')
    assert rupture['payload']['section']=='L0' and rupture['payload']['qualified_capacity']['walls']['L0']['W']>=.8
    assert sum(e['kind']=='ball_escaped' for e in r['simulation']['events'])==11


def test_sparse_audio_deterministic_absolute_clock_and_dominant_rupture(frozen):
    r,t=frozen;pcm,a=synthesize(t.events,t.duration);again,b=synthesize(t.events,t.duration)
    assert np.array_equal(pcm,again) and a==b
    assert a['sample_rate']==48000 and a['channels']==2 and a['cue_count']<60
    assert np.isfinite(pcm).all() and a['peak']<1 and a['mono_rms']>0
    R=next(e['time'] for e in r['simulation']['events'] if e['kind']=='wall_ruptured')
    peak=lambda data:float(np.max(np.abs(data.astype(float))))
    assert peak(pcm[round(R*48000):round((R+.4)*48000)])>peak(pcm[:round(R*48000)])
    source={e['id'] for e in r['simulation']['events']}
    assert all(json.loads(e)['id'].split(':motion')[0] in source for e in map_events(t.events))
    assert sum(c['kind']=='split' and c['time']==1.05 for c in a['cues'])==1
    rise=next(c for c in a['cues'] if c['kind']=='pressure_rise')
    assert rise['frequency_end']>rise['frequency_start'] and rise['time']<R-.4


def test_media_full_decode_shared_stream_and_hashes(frozen):
    path=OUT/'ms06.3d-manifest.json'
    if not path.exists():pytest.skip('Render stage not yet completed')
    m=json.loads(path.read_text());a=inspect_media(OUT/'ms06.3d-review.mp4');b=inspect_media(OUT/'ms06.3d-muted.mp4')
    assert a['video_stream_sha256']==b['video_stream_sha256']
    for n,record in m['files'].items():assert file_hash(OUT/n)==record['sha256']
    for p,h in m['freeze']['source_sha256'].items():assert file_hash(ROOT/p)==h
    with wave.open(str(OUT/'ms06.3d-audio.wav'),'rb') as wav:
        assert wav.getframerate()==48000 and wav.getnchannels()==2
        assert hashlib.sha256(wav.readframes(wav.getnframes())).hexdigest()==m['audio']['pcm_sha256']
    renderer=Renderer(frozen[1])
    for seconds,h in m['frame_sha256'].items():
        assert hashlib.sha256(renderer.render(float(seconds)).tobytes()).hexdigest()==h
    video=next(s for s in a['probe']['streams'] if s['codec_type']=='video')
    audio=next(s for s in a['probe']['streams'] if s['codec_type']=='audio')
    assert (video['width'],video['height'],video['r_frame_rate'],video['pix_fmt'])==(720,1280,'30/1','yuv420p')
    assert video['color_space']==video['color_transfer']==video['color_primaries']=='bt709'
    assert audio['codec_name']=='aac' and audio['sample_rate']=='48000' and audio['channels']==2
    assert all(s['codec_type']!='audio' for s in b['probe']['streams'])
    assert int(video['nb_frames'])==frozen[1].frame_count==349


def test_presentation_and_audio_modules_import_no_engine():
    for name in ('capacity_presentation.py','capacity_audio.py'):
        tree=ast.parse((ROOT/'src/inception'/name).read_text())
        modules=[n.module or '' for n in ast.walk(tree) if isinstance(n,ast.ImportFrom)]
        assert not any('bloom' in m or 'scenario' in m or 'layout' in m for m in modules)
