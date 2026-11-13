"""Sample-based, deterministic event cues. No FPS, rendering, or game engine."""

from dataclasses import dataclass
import hashlib
import math
from pathlib import Path
import wave

import numpy as np

from .events import AudioEvent, EventLog, SCHEMA_VERSION, Team

# Eight related voices: octave pairs in four registers, with different partials.
VOICE_HZ = (659.255, 329.628, 523.251, 261.626, 783.991, 391.995, 587.330, 293.665)
VOICE_PARTIALS = ((1., .15, .11), (1., .42, .06), (1., .12, .25), (1., .32, .12),
                  (1., .08, .34), (1., .50, .04), (1., .22, .23), (1., .28, .07))
VOICE_PAN = (-.28, .28, -.14, .14, -.36, .36, 0., 0.)


@dataclass(frozen=True)
class CueParameters:
    voice: int
    frequency_hz: float
    rms_level: float
    duration_seconds: float
    decay_seconds: float
    grain_count: int
    noise_level: float
    pan: float
    pitch_sweep: float
    cascade_depth: int


def cue_parameters(event: AudioEvent, team: Team) -> CueParameters:
    depth = min(event.cascade_depth, 8)  # A sonic ceiling, not a game-rule limit.
    ratio = min(1., event.orb_count/event.critical_mass) if event.critical_mass and event.orb_count is not None else 0.
    # duration, isolated mono RMS, decay, grains, noise, pitch ratio, sweep
    recipes = {
        "turn_started": (.075, .018, .022, 1, .01, 1., 0.),
        "orb_placed": (.12, .060, .035, 1, .035, 1., 0.),
        "cell_charged": (.16, .020+.045*ratio, .045, 1+int(ratio*3), .015, 2**(ratio*3/12), .04),
        "cell_became_critical": (.14, .070, .028, 2, .04, 1.4, .07),
        "cell_exploded": (.24, .085*(1+.20*depth), .035+.004*depth, 1+min(depth, 6), .15+.02*depth, 2**((depth-5)/12), -.08),
        "neighbor_captured": (.14, .065, .030, 1, .06, 1.25, .04),
        "cascade_depth_increased": (.09, .025*(1+.10*depth), .020, 1, .02, 2**(depth/12), 0.),
        "player_endangered": (.25, .048, .045, 3, .025, 1.12, .10),
        "player_eliminated": (.32, .075, .070, 2, .06, .80, -.42),
        "winner_declared": (.65, .095, .140, 2, .015, 1., 0.),
    }
    duration, level, decay, grains, noise, pitch, sweep = recipes[event.kind]
    return CueParameters(team.voice, VOICE_HZ[team.voice]*pitch, level, duration,
                         decay, grains, noise, VOICE_PAN[team.voice], sweep, event.cascade_depth)


def sample_index(time_seconds: float, sample_rate: int) -> int:
    """Absolute seconds to the nearest sample; positive half samples round up."""
    return math.floor(time_seconds*sample_rate+.5)


def synthesize_cue(event: AudioEvent, team: Team, seed: int, sample_rate: int):
    params = cue_parameters(event, team)
    identity = f"{SCHEMA_VERSION}:{seed}:{event.id}".encode()
    event_seed = int.from_bytes(hashlib.sha256(identity).digest()[:8], "little")
    rng = np.random.Generator(np.random.PCG64(event_seed))
    count = sample_index(params.duration_seconds, sample_rate)
    t = np.arange(count)/sample_rate
    envelope = np.zeros(count)
    spacing = .090 if event.kind == "winner_declared" else .045 if event.kind in {"player_endangered", "player_eliminated"} else .012
    for grain in range(params.grain_count):
        local = t-grain*spacing
        pulse = np.exp(-np.maximum(local, 0)/params.decay_seconds)*np.clip(local/.0015, 0, 1)
        envelope += pulse
    phase = 2*np.pi*params.frequency_hz*(t+.5*params.pitch_sweep*t*t/params.duration_seconds)
    weights = VOICE_PARTIALS[params.voice]
    carrier = sum(weight*np.sin((harmonic+1)*phase) for harmonic, weight in enumerate(weights))
    noise = rng.normal(0, 1, count)
    unit = carrier*envelope + params.noise_level*noise*envelope*np.exp(-t/.020)
    fade = min(128, count//4)
    unit[-fade:] *= np.linspace(1, 0, fade)
    # Fix isolated cue energy before panning. Depth/charge controls therefore have
    # a measurable level progression despite different noise and pitch content.
    unit *= params.rms_level/max(1e-12, float(np.sqrt(np.mean(unit**2))))
    return unit, params


@dataclass(frozen=True)
class CueRecord:
    event_id: str
    kind: str
    team_id: str
    time_seconds: float
    start_sample: int
    sample_count: int
    parameters: CueParameters


@dataclass(frozen=True)
class AudioRender:
    samples: np.ndarray
    sample_rate: int
    channels: int
    master_gain: float
    peak: float
    cues: tuple[CueRecord, ...]


def synthesize(log: EventLog, seed=505, sample_rate=48000, channels=2) -> AudioRender:
    if type(seed) is not int or seed < 0:
        raise ValueError("audio seed must be a nonnegative integer")
    if type(sample_rate) is not int or not 16000 <= sample_rate <= 96000:
        raise ValueError("sample_rate must be an integer in 16000..96000")
    if type(channels) is not int or channels not in (1, 2):
        raise ValueError("channels must be one or two")
    mix = np.zeros((sample_index(log.duration_seconds, sample_rate), 2), dtype=np.float64)
    teams = {team.id: team for team in log.teams}
    records = []
    for event in log.events:
        mono, params = synthesize_cue(event, teams[event.team_id], seed, sample_rate)
        start = sample_index(event.time_seconds, sample_rate)
        if start+len(mono) > len(mix):
            raise ValueError(f"output window would truncate cue {event.id}; reserve a tail")
        gains = np.sqrt([(1-params.pan)/2, (1+params.pan)/2])
        mix[start:start+len(mono)] += mono[:, None]*gains
        records.append(CueRecord(event.id, event.kind, event.team_id, event.time_seconds,
                                 start, len(mono), params))
    if not np.isfinite(mix).all():
        raise ValueError("non-finite samples in mix")
    gain = min(1., .86/max(1e-12, float(np.abs(mix).max())))
    mix *= gain  # One constant attenuation; no hidden clipping or dynamic pumping.
    if channels == 1:
        mix = mix.mean(axis=1, keepdims=True)
    pcm = np.rint(mix*32767).astype("<i2")
    pcm.setflags(write=False)
    return AudioRender(pcm, sample_rate, channels, gain,
                       float(np.abs(pcm.astype(np.float64)).max()/32768), tuple(records))


def write_wav(render: AudioRender, path: str | Path):
    """Never replace a prior generated artifact; use another output filename."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("xb") as raw:
        with wave.open(raw, "wb") as file:
            file.setnchannels(render.channels)
            file.setsampwidth(2)
            file.setframerate(render.sample_rate)
            file.writeframes(render.samples.tobytes())
