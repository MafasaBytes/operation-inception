from dataclasses import FrozenInstanceError, replace
import hashlib
import json
from pathlib import Path
import wave

import numpy as np
import pytest

from inception.audio.events import AudioEvent, EVENT_KINDS, Team, load_event_log, parse_event_log
from inception.audio.synthesis import cue_parameters, sample_index, synthesize, synthesize_cue, write_wav

FIXTURE = Path(__file__).resolve().parents[1]/"fixtures/ms05/two-team-v1.json"


@pytest.fixture(scope="module")
def event_log():
    return load_event_log(FIXTURE)


def test_fixture_contract_and_immutable_log(event_log):
    assert event_log.synthetic
    assert {e.kind for e in event_log.events} == EVENT_KINDS
    steps = [e.cascade_depth for e in event_log.events if e.kind == "cell_exploded" and e.team_id == "orange"]
    assert steps == [0, 1, 2, 3, 4]
    reversal = [e for e in event_log.events if e.kind == "neighbor_captured" and e.cell == (0, 1)]
    assert [(e.previous_team_id, e.team_id) for e in reversal] == [("orange", "cyan"), ("cyan", "orange")]
    with pytest.raises(FrozenInstanceError):
        event_log.events[0].team_id = "orange"
    assert isinstance(event_log.events, tuple) and isinstance(event_log.teams, tuple)


def test_same_events_seed_reproduce_exact_pcm_and_wav(event_log, tmp_path):
    first = synthesize(event_log, seed=505)
    second = synthesize(event_log, seed=505)
    np.testing.assert_array_equal(first.samples, second.samples)
    assert not np.array_equal(first.samples, synthesize(event_log, seed=506).samples)
    a, b = tmp_path/"a.wav", tmp_path/"b.wav"
    write_wav(first, a)
    write_wav(second, b)
    assert hashlib.sha256(a.read_bytes()).digest() == hashlib.sha256(b.read_bytes()).digest()
    with wave.open(str(a)) as file:
        assert (file.getnframes(), file.getframerate(), file.getnchannels(), file.getsampwidth()) == (576000, 48000, 2, 2)
    with pytest.raises(FileExistsError):
        write_wav(first, a)


def test_audio_timing_is_sample_based_and_independent_of_fps(event_log):
    raw = json.loads(FIXTURE.read_text())
    raw["metadata"]["preview_fps"] = 24
    at24 = synthesize(parse_event_log(raw))
    raw["metadata"]["preview_fps"] = 60
    at60 = synthesize(parse_event_log(raw))
    np.testing.assert_array_equal(at24.samples, at60.samples)
    event = AudioEvent("off-frame-time", 0, .13725, "orb_placed", "cyan")
    isolated = replace(event_log, duration_seconds=1., events=(event,))
    for rate in (24000, 48000):
        result = synthesize(isolated, sample_rate=rate)
        start = sample_index(.13725, rate)
        assert result.cues[0].start_sample == start
        assert not result.samples[:start].any()
        assert result.samples[start:start+48].any()
        assert all(abs(.13725*fps-round(.13725*fps)) > .01 for fps in (24, 30, 60))


def test_finite_headroom_and_phase_safe_mono(event_log):
    stereo = synthesize(event_log)
    mono = synthesize(event_log, channels=1)
    assert np.isfinite(stereo.samples).all()
    assert 0 < stereo.peak <= .861 and mono.peak <= .861
    assert not np.any(np.abs(stereo.samples.astype(float)) >= 32767)
    downmix = stereo.samples.astype(float).mean(axis=1)
    np.testing.assert_allclose(mono.samples[:, 0], downmix, atol=1)
    stereo_rms = np.sqrt(np.mean(stereo.samples.astype(float)**2))
    mono_rms = np.sqrt(np.mean(mono.samples.astype(float)**2))
    assert mono_rms/stereo_rms > .9
    assert not stereo.samples.flags.writeable


def test_related_voices_are_distinct_for_two_to_eight_teams(event_log):
    event = AudioEvent("identity", 0, .1, "orb_placed", "t0")
    cues, dominant = [], []
    for voice in range(8):
        cue, params = synthesize_cue(event, Team("t0", voice), 505, 48000)
        cues.append(cue)
        spectrum = abs(np.fft.rfft(cue))
        frequency = np.fft.rfftfreq(len(cue), 1/48000)[spectrum.argmax()]
        dominant.append(frequency)
        assert frequency == pytest.approx(params.frequency_hz, abs=10)
    assert len(set(dominant)) == 8
    assert dominant[0] > 1.9*dominant[1]
    assert all(not np.array_equal(a, b) for i, a in enumerate(cues) for b in cues[i+1:])
    for count in range(2, 9):
        teams = tuple(Team(f"t{i}", i) for i in range(count))
        events = tuple(replace(event, id=f"voice-{i}", sequence=i, time_seconds=.1+i*.18, team_id=f"t{i}") for i in range(count))
        output = synthesize(replace(event_log, duration_seconds=2., teams=teams, events=events))
        assert output.peak <= .861


def test_charge_and_cascade_parameters_increase_event_energy(event_log):
    team = Team("orange", 1)
    explosions = [e for e in event_log.events if e.kind == "cell_exploded" and e.team_id == "orange"]
    cues = [synthesize_cue(event, team, 505, 48000) for event in explosions]
    rms = [float(np.sqrt(np.mean(signal**2))) for signal, _ in cues]
    assert all(b > a*1.08 for a, b in zip(rms, rms[1:]))
    assert [p.grain_count for _, p in cues] == [1, 2, 3, 4, 5]
    assert all(b.frequency_hz > a.frequency_hz for (_, a), (_, b) in zip(cues, cues[1:]))
    base = AudioEvent("charge", 0, .1, "cell_charged", "orange", orb_count=1, critical_mass=4)
    levels = [cue_parameters(replace(base, orb_count=n), team).rms_level for n in (1, 2, 3)]
    assert levels[0] < levels[1] < levels[2]


@pytest.mark.parametrize("change", [
    lambda d: d.update(schema_version="unknown"),
    lambda d: d["events"][1].update(id=d["events"][0]["id"]),
    lambda d: d["events"][1].update(time_seconds=-1),
    lambda d: d["events"][1].update(team_id="missing"),
    lambda d: d["events"][1].update(kind="voiceover"),
    lambda d: d["teams"][1].update(voice=0),
])
def test_rejects_invalid_contract(change):
    data = json.loads(FIXTURE.read_text())
    change(data)
    with pytest.raises(ValueError):
        parse_event_log(data)


def test_does_not_silently_truncate_resolution(event_log):
    with pytest.raises(ValueError, match="truncate"):
        synthesize(replace(event_log, duration_seconds=10.7))
