"""Narrow MS06.3 procedural sound from immutable absolute-time PB events only."""
from __future__ import annotations

from dataclasses import asdict, dataclass
import hashlib
import json
import math
from pathlib import Path
import wave

import numpy as np

RATE = 48000


@dataclass(frozen=True)
class Cue:
    event_id: str
    kind: str
    time: float
    duration: float
    frequency: float
    amplitude: float
    pan: float


def map_events(events: tuple[str, ...]) -> tuple[Cue, ...]:
    cues = []
    strain_bins = set()
    last_motion_time, last_height = 0., None
    for raw in events:
        e = json.loads(raw)
        kind, p, t = e["kind"], e["payload"], e["time"]
        lineage = p.get("parent", p.get("ball", {}))
        lineage = lineage.get("lineage", "cyan") if isinstance(lineage, dict) else "cyan"
        frequency = {"cyan": 760., "orange": 520., "magenta": 630.}[lineage]
        pan = {"cyan": -.2, "orange": .2, "magenta": 0.}[lineage]
        if kind == "press_engaged":
            cues.append(Cue(e["id"],"engage",t,.26,110.,.26,0.))
            last_height = e["after"]["height"]
        elif kind == "compression_advanced":
            height = e["after"]["height"]
            duration = t-last_motion_time
            if last_height is not None and duration > 0 and height < last_height:
                speed = (last_height-height)/duration
                cues.append(Cue(e["id"],"movement",last_motion_time,duration,
                                140.+min(80.,speed*180),min(.065,.012+speed*.12),0.))
            last_motion_time, last_height = t, height
        elif kind == "ball_split":
            cues.append(Cue(e["id"],"split",t,.075,frequency,.22,pan))
        elif kind == "ball_crushed":
            cues.append(Cue(e["id"],"crush",t,.14,frequency*.26,.36,pan))
        elif kind == "ball_strained" and p["new"] != "normal":
            # Coalesce low-priority strain chatter into fixed absolute-time bins;
            # every split/crush/rupture remains distinct and unfiltered.
            bucket = math.floor(t/.18)
            if bucket not in strain_bins:
                strain_bins.add(bucket)
                cues.append(Cue(e["id"],"strain",t,.13,
                                240. if p["new"]=="extreme" else 200.,.025,0.))
        elif kind == "wall_strained" and p["strained"]:
            cues.append(Cue(e["id"],"creak",t,.35,280.,.16,0.))
        elif kind == "wall_ruptured":
            cues.append(Cue(e["id"],"rupture",t,.28,150.,.68,0.))
            cues.append(Cue(e["id"],"release",t,.60,600.,.18,0.))
        elif kind == "chamber_contained":
            cues.append(Cue(e["id"],"containment",t,.30,320.,.22,0.))
    return tuple(sorted(cues,key=lambda c:(c.time,c.event_id,c.kind)))


def synthesize(events: tuple[str, ...], duration: float, seed: int = 6305):
    cues = map_events(events)
    mixed = np.zeros((round(duration*RATE),2),dtype=np.float64)
    for c in cues:
        start = math.floor(c.time*RATE+.5)
        count = min(round(c.duration*RATE),len(mixed)-start)
        if count <= 0:
            continue
        t = np.arange(count)/RATE
        u = t/c.duration
        noise_seed = int.from_bytes(hashlib.sha256(f"{seed}:{c.event_id}:{c.kind}".encode()).digest()[:8],"little")
        rng = np.random.default_rng(noise_seed)
        noise = rng.standard_normal(count)
        attack = np.minimum(1.,t/.003)
        fade = np.minimum(1.,(c.duration-t)/.025)
        if c.kind == "movement":
            tone = np.sin(2*np.pi*c.frequency*t)+.3*np.sin(2*np.pi*c.frequency*2*t)
            env = np.minimum(1.,t/.04)*np.minimum(1.,(c.duration-t)/.04)
        elif c.kind == "split":
            phase = 2*np.pi*c.frequency*(t-.32*t*t/c.duration)
            tone = np.sin(phase)+.18*np.sin(phase*2)+.10*noise
            env = attack*np.exp(-5*u)*fade
        elif c.kind in ("crush","rupture","engage"):
            phase = 2*np.pi*c.frequency*(t-.35*t*t/c.duration)
            tone = np.sin(phase)+.45*np.sin(phase*2.4)+.32*noise*np.exp(-10*u)
            env = attack*np.exp(-4*u)*fade
        elif c.kind == "release":
            tone = np.convolve(noise,np.ones(5)/5,mode="same")
            env = attack*np.exp(-3*u)*fade
        elif c.kind == "containment":
            tone = np.sin(2*np.pi*c.frequency*t)+.35*np.sin(2*np.pi*c.frequency*1.5*t)
            env = attack*np.exp(-3*u)*fade
        else:
            tone = np.sin(2*np.pi*c.frequency*t)*(1+.25*np.sin(2*np.pi*23*t))+.08*noise
            env = attack*np.sin(np.pi*np.minimum(u,1.))**2*fade
        signal = tone*env*c.amplitude
        gains = np.array([math.sqrt((1-c.pan)/2),math.sqrt((1+c.pan)/2)])
        mixed[start:start+count] += signal[:,None]*gains[None,:]
    if not np.isfinite(mixed).all():
        raise ValueError("Nonfinite Pressure Bloom audio")
    pre_peak = float(np.max(np.abs(mixed)))
    gain = min(1.,.86/max(pre_peak,1e-12))
    mixed *= gain
    pcm = np.rint(mixed*32767).astype('<i2')
    peak = float(np.max(np.abs(pcm.astype(float)))/32768)
    report = {"sample_rate":RATE,"channels":2,"sample_count":len(pcm),"duration":len(pcm)/RATE,
              "peak":peak,"peak_dbfs":20*math.log10(max(peak,1e-12)),"pre_mix_peak":pre_peak,
              "master_gain":gain,"finite":True,"unclipped":bool(peak<1),
              "rms_by_channel":np.sqrt(np.mean((pcm.astype(float)/32768)**2,axis=0)).tolist(),
              "mono_rms":float(np.sqrt(np.mean(np.mean(pcm.astype(float)/32768,axis=1)**2))),
              "pcm_sha256":hashlib.sha256(pcm.tobytes()).hexdigest(),
              "cue_count":len(cues),"cues":[asdict(c) for c in cues],"seed":seed}
    return pcm,report


def write_wav(path: Path, pcm) -> None:
    with wave.open(str(path),"wb") as stream:
        stream.setnchannels(2)
        stream.setsampwidth(2)
        stream.setframerate(RATE)
        stream.writeframes(pcm.astype('<i2').tobytes())
