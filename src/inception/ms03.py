"""MS03 rough cut: directed bead-tag choreography with actual pictured contacts.

This standalone scene uses the existing NumPy/Pillow/FFmpeg toolchain. It does
not change the assembly models, add an editor, or support final-master export.
"""

import argparse
from dataclasses import dataclass
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import tomllib
import wave

import numpy as np
from PIL import Image, ImageDraw, ImageFont


@dataclass(frozen=True)
class Settings:
    seed: int = 303
    width: int = 360
    height: int = 640
    fps: int = 30
    duration_seconds: float = 24
    ivory_count: int = 42
    bead_radius: float = 9.5
    arena_radius: float = 185
    first_hit_seconds: float = .9
    near_miss_seconds: tuple = (21.4, 22.3)
    final_hit_seconds: float = 23 + 1/6
    reset_seconds: float = 23.9
    audio_sample_rate: int = 48000

    def __post_init__(self):
        if (self.width, self.height, self.fps) != (360, 640, 30):
            raise ValueError("MS03 is restricted to the 360x640, 30 FPS creative-review cut")
        if self.ivory_count != 42 or self.duration_seconds != 24:
            raise ValueError("This treatment has 42 ivory beads and a 24-second story")
        if self.bead_radius != 9.5 or self.arena_radius != 185:
            raise ValueError("Keep the rough-cut composition fixed until creative review")
        if list(self.near_miss_seconds) != [21.4, 22.3]:
            raise ValueError("The two focus passes are authored for 21.4 and 22.3 seconds")


def hermite(a, va, b, vb, u, duration):
    return ((2*u**3-3*u*u+1)*a + (u**3-2*u*u+u)*va*duration
            + (-2*u**3+3*u*u)*b + (u**3-u*u)*vb*duration)


def event_times(settings):
    return [settings.first_hit_seconds, 3.4, 6.1,
            7.20, 7.95, 8.62, 9.22, 9.77, 10.28, 10.75, 11.19, 11.60,
            11.98, 12.34, 12.68, 13.00, 13.30, 13.58, 13.85, 14.10,
            14.34, 14.57, 14.79, 15.00, 15.21, 15.42, 15.63, 15.84,
            16.15, 16.40, 16.67, 16.96, 17.28, 17.63, 18.01, 18.43,
            18.90, 19.41, 19.96, 20.41, 20.82, settings.final_hit_seconds]


class LastBeadStanding:
    """Precompute one deterministic clip, keeping rendering out of the scene model."""

    def __init__(self, settings):
        self.cfg = settings
        self.rng = np.random.Generator(np.random.PCG64(settings.seed))
        self.center = np.array([180., 334.])
        angles = np.deg2rad(np.arange(6)*60-90)
        self.vertices = self.center + settings.arena_radius*np.column_stack((np.cos(angles), np.sin(angles)))
        angles = np.deg2rad(np.arange(6)*60)
        self.normals = np.column_stack((np.cos(angles), np.sin(angles)))
        self.apothem = settings.arena_radius*np.sqrt(3)/2
        self.positions = self._initial_positions()
        self.initial = self.positions.copy()
        self.velocity = np.zeros((43, 2))
        self.velocity[0] = [38, 0]
        self.wake = np.full(43, np.inf)
        self.wake[0] = 0
        self.events = []
        self.wall_taps = []
        self.near_misses = []
        self.tracks = {}
        self.assigned = set()
        self.heading = self.rng.uniform(0, 2*np.pi, 43)
        self.history = []
        self.wake_history = []
        self.dt = 1/120
        self._simulate()

    def _initial_positions(self):
        points = {0: np.array([90., 230.]), 1: np.array([140., 230.]),
                  40: np.array([95., 302.]), 41: np.array([139., 442.]),
                  42: np.array([252., 410.])}
        for i in range(2, 40):
            for _ in range(10000):
                p = self.rng.uniform([35, 175], [325, 495])
                if np.any((p-self.center)@self.normals.T > self.apothem-self.cfg.bead_radius-6):
                    continue
                if min(np.linalg.norm(p-other) for other in points.values()) < 29:
                    continue
                if np.linalg.norm(p-np.array([105, 230])) < 55:
                    continue
                points[i] = p
                break
            else:
                raise ValueError("Unable to place MS03 ivory population")
        return np.array([points[i] for i in range(43)])

    def _plan_hit(self, due, time, forced=None):
        active = [i for i in np.flatnonzero(self.wake <= time) if i not in self.tracks]
        targets = [i for i in range(1, 40) if not np.isfinite(self.wake[i]) and i not in self.assigned]
        if forced is not None:
            targets = [forced]
        pairs = sorted((np.linalg.norm(self.positions[i]-self.positions[j]), i, j)
                       for i in active for j in targets)
        for _, source, target in pairs:
            a, target_pos = self.positions[source].copy(), self.positions[target]
            normal = (a-target_pos) / np.linalg.norm(a-target_pos)
            b = target_pos + normal*(2*self.cfg.bead_radius)
            duration = due-time
            va = self.velocity[source]*.5
            vb = -normal*(48 if time < 7 else 115)
            us = np.linspace(0, 1, 81)
            path = np.array([hermite(a, va, b, vb, u, duration) for u in us])
            others = [j for j in range(1, 43) if not np.isfinite(self.wake[j]) and j != target]
            if others and np.min(np.linalg.norm(path[:, None]-self.positions[others][None], axis=2)) < 2*self.cfg.bead_radius+3:
                continue
            if np.any((path-self.center)@self.normals.T > self.apothem-self.cfg.bead_radius-1):
                continue
            if np.min(np.linalg.norm(path[:-1]-target_pos, axis=1)) < 2*self.cfg.bead_radius-.01:
                continue
            self.tracks[source] = dict(kind="hit", start=time, end=due, a=a, va=va,
                                       b=b, vb=vb, target=target)
            self.assigned.add(target)
            return
        raise ValueError(f"No clear collision route for event at {due:.3f}s")

    def _focus_track(self, time, kind):
        hero = self.positions[42]
        if kind == "miss1":
            start, end = 21.10, 21.70
            a, v = hero+[-62, -23], np.array([62/.30, 0.])
        elif kind == "miss2":
            start, end = 22.02, 22.58
            a, v = hero+[-24, 52], np.array([0., -52/.28])
        else:
            start, end = 22.84, self.cfg.final_hit_seconds
            a = hero + [60, -40]
            b = hero + np.array([60, -40])/np.hypot(60, 40)*(2*self.cfg.bead_radius)
            v = (b-a)/(end-start)
        available = [i for i in np.flatnonzero(self.wake <= time) if i not in self.tracks]
        source = min(available, key=lambda i: np.linalg.norm(self.positions[i]-a))
        self.tracks[source] = dict(kind=kind, start=time, end=end,
                                  a=self.positions[source].copy(), va=self.velocity[source]*.3,
                                  b=a, vb=v, line_start=start, target=42)

    def _track_position(self, track, time):
        if "line_start" in track:
            split = track["line_start"]
            if time >= split:
                return track["b"] + track["vb"]*(time-split)
            duration = split-track["start"]
        else:
            duration = track["end"]-track["start"]
        u = np.clip((time-track["start"])/duration, 0, 1)
        return hermite(track["a"], track["va"], track["b"], track["vb"], u, duration)

    def _convert(self, source, target, time):
        normal = self.positions[source]-self.positions[target]
        normal /= np.linalg.norm(normal)
        self.wake[target] = time
        speed = 52 if time < 7 else 112
        tangent = np.array([-normal[1], normal[0]])
        self.velocity[source] = (normal + .35*tangent)*speed
        self.velocity[target] = (-normal + .30*tangent)*speed
        self.events.append({"time_seconds": round(time, 6), "source": int(source), "target": int(target),
                            "position": self.positions[target].tolist(), "cyan_count": int(np.sum(self.wake <= time)),
                            "contact_center_distance": float(np.linalg.norm(self.positions[source]-self.positions[target]))})

    def _simulate(self):
        due_times = event_times(self.cfg)
        planned = set()
        focus_done = set()
        nsteps = round(self.cfg.duration_seconds/self.dt)
        for step in range(nsteps):
            time = step*self.dt
            if time >= self.cfg.reset_seconds:
                self.history.append(self.history[0].copy())
                self.wake_history.append(np.r_[0., np.full(42, np.inf)])
                continue
            for number, due in enumerate(due_times[:-1]):
                lead = .78 if due < 7 else .45
                if number not in planned and time >= due-lead-1e-9:
                    forced = 1 if number == 0 else (40 if number == 39 else 41 if number == 40 else None)
                    self._plan_hit(due, time, forced)
                    planned.add(number)
            for trigger, kind in ((20.85, "miss1"), (21.74, "miss2"), (22.60, "final")):
                if kind not in focus_done and time >= trigger-1e-9:
                    self._focus_track(time, kind)
                    focus_done.add(kind)
            active = np.flatnonzero(self.wake <= time)
            ivory = np.flatnonzero(self.wake > time)
            old = self.positions.copy()
            speed = 48 + 78*np.clip((time-7)/9, 0, 1)
            for index in active:
                if index in self.tracks:
                    continue
                velocity = self.velocity[index]
                # Small steering curves keep waiting ivory clear until an authored
                # approach makes genuine contact. These are directed game paths.
                if len(ivory):
                    delta = self.positions[index]-self.positions[ivory]
                    distance = np.linalg.norm(delta, axis=1)
                    influence = np.clip((49-distance)/23, 0, 1)**2
                    velocity += np.sum(delta/np.maximum(distance[:, None], .01)*influence[:, None], axis=0)*210*self.dt
                if 20.3 < time < self.cfg.final_hit_seconds and 42 in ivory:
                    delta = self.positions[index]-self.positions[42]
                    distance = np.linalg.norm(delta)
                    velocity += delta/max(distance, .01)*max(0, 90-distance)*8*self.dt
                velocity += np.array([np.cos(time*1.7+self.heading[index]), np.sin(time*1.3+self.heading[index])])*6*self.dt
                length = np.linalg.norm(velocity)
                self.velocity[index] = velocity/max(length, .01)*speed
                self.positions[index] += self.velocity[index]*self.dt
            # Kinematic paths are sampled from absolute time and meet their target
            # at the logged event, without moving an ivory bead beforehand.
            for index, track in list(self.tracks.items()):
                self.positions[index] = self._track_position(track, time)
                self.velocity[index] = (self.positions[index]-old[index])/self.dt
                target = track["target"]
                if track["kind"] in ("hit", "final") and time >= track["end"]-1e-9:
                    assert np.linalg.norm(self.positions[index]-self.positions[target]) <= 2*self.cfg.bead_radius+.01
                    self._convert(index, target, time)
                    del self.tracks[index]
                elif track["kind"].startswith("miss") and time >= track["end"]-1e-9:
                    del self.tracks[index]
            # Keep passive cyan visibly separated from stationary ivory. There is
            # no invisible conversion: any actual core contact is checked below.
            for index in active:
                if index in self.tracks:
                    continue
                for target in np.flatnonzero(self.wake > time):
                    delta = self.positions[index]-self.positions[target]
                    distance = np.linalg.norm(delta)
                    clearance = 2*self.cfg.bead_radius+7
                    if distance < clearance:
                        normal = delta/max(distance, .01)
                        self.positions[index] = self.positions[target]+normal*clearance
                        inward = np.dot(self.velocity[index], normal)
                        if inward < 0:
                            self.velocity[index] -= 1.8*inward*normal
            # Arena walls and cyan/cyan impacts have ordinary billiard-like response.
            active = np.flatnonzero(self.wake <= time)
            for index in active:
                if index in self.tracks:
                    continue
                for normal in self.normals:
                    penetration = np.dot(self.positions[index]-self.center, normal)-(self.apothem-self.cfg.bead_radius-2)
                    if penetration > 0:
                        self.positions[index] -= (penetration+.01)*normal
                        self.velocity[index] -= 2*max(0, np.dot(self.velocity[index], normal))*normal
                        if not self.wall_taps or time-self.wall_taps[-1]["time_seconds"] > .10:
                            self.wall_taps.append({"time_seconds": time, "x": float(self.positions[index, 0])})
            for ai, i in enumerate(active):
                for j in active[ai+1:]:
                    delta = self.positions[i]-self.positions[j]
                    distance = np.linalg.norm(delta)
                    if .001 < distance < 2*self.cfg.bead_radius:
                        normal = delta/distance
                        for bead, sign in ((i, 1), (j, -1)):
                            if bead not in self.tracks:
                                self.positions[bead] += sign*normal*(2*self.cfg.bead_radius-distance)*.51
                        relative = np.dot(self.velocity[i]-self.velocity[j], normal)
                        if relative < 0:
                            if i not in self.tracks:
                                self.velocity[i] -= relative*normal
                            if j not in self.tracks:
                                self.velocity[j] += relative*normal
            for kind, when in (("miss1", self.cfg.near_miss_seconds[0]), ("miss2", self.cfg.near_miss_seconds[1])):
                if abs(time-when) < self.dt/2:
                    source = next(i for i, track in self.tracks.items() if track["kind"] == kind)
                    gap = np.linalg.norm(self.positions[source]-self.positions[42])-2*self.cfg.bead_radius
                    self.near_misses.append({"time_seconds": time, "source": int(source), "target": 42,
                                             "edge_gap_pixels": float(gap)})
            stationary = np.flatnonzero(self.wake > time)
            if len(stationary):
                distance = np.linalg.norm(self.positions[active, None]-self.positions[stationary][None], axis=2)
                if np.min(distance) < 2*self.cfg.bead_radius-.1:
                    raise ValueError(f"Unmarked cyan/ivory contact at {time:.3f}s")
            self.history.append(self.positions.copy())
            self.wake_history.append(self.wake.copy())
        self.history = np.array(self.history)
        self.wake_history = np.array(self.wake_history)
        assert len(self.events) == 42
        assert [np.sum(self.wake <= t) for t in (2, 7)] == [2, 4]
        assert all(miss["edge_gap_pixels"] > 0 for miss in self.near_misses)


class GameRenderer:
    """One fixed-camera, graphic treatment; no changes to the assembly renderer."""

    def __init__(self, scene):
        self.scene = scene
        self.cfg = scene.cfg
        self.scale = 2
        root = Path("/usr/share/fonts/truetype/dejavu")
        if not (root/"DejaVuSans-Bold.ttf").exists():
            raise RuntimeError("MS03 requires the DejaVu Sans fonts used by this rough cut")
        self.fonts = {size: ImageFont.truetype(str(root/"DejaVuSans-Bold.ttf"), size*2)
                      for size in (13, 15, 17, 18, 19, 21, 23, 25, 29)}
        self.cyan = "#31e4ed"
        self.ivory = "#ffedbd"
        self.background = Image.new("RGB", (720, 1280), "#101923")
        d = ImageDraw.Draw(self.background)
        polygon = [(int(x*2), int(y*2)) for x, y in scene.vertices]
        d.polygon(polygon, fill="#1b2a36")
        d.line(polygon+[polygon[0]], fill="#c7d6dd", width=6, joint="curve")
        self._centered(d, 180, 26, "EVERY CYAN HIT", 23, self.cyan)
        self._centered(d, 180, 56, "WAKES ANOTHER BEAD.", 23, self.ivory)
        self._centered(d, 180, 95, "WHICH ONE WILL BE LAST?", 18, "#ffffff")

    def _centered(self, draw, x, y, text, size, color):
        draw.text((x*2, y*2), text, font=self.fonts[size], anchor="mt", fill=color,
                  stroke_width=0)

    def render(self, frame):
        time = frame/self.cfg.fps
        step = min(len(self.scene.history)-1, round(time/self.scene.dt))
        positions = self.scene.history[step]
        wakes = self.scene.wake_history[step]
        if time >= self.cfg.reset_seconds:
            time = 0
        canvas = self.background.copy()
        d = ImageDraw.Draw(canvas, "RGBA")
        active = wakes <= time+1e-8
        remaining = int(np.sum(~active))
        # Cyan trails are short direction cues, not bloom or a background effect.
        previous = self.scene.history[max(0, step-6)] if time > 0 else positions
        for i in np.flatnonzero(active):
            x, y = positions[i]*2
            tail = positions[i] + np.clip((previous[i]-positions[i]), -12, 12)
            d.line((*tail*2, x, y), fill=(49, 228, 237, 80), width=8)
        if remaining == 1:
            x, y = positions[42]*2
            r = 14*2
            d.ellipse((x-r, y-r, x+r, y+r), outline=(255, 237, 189, 95), width=2)
        # Contact rings sit behind the bodies, leaving the actual touching edges readable.
        for event in self.scene.events:
            age = time-event["time_seconds"]
            if 0 <= age < .20:
                x, y = np.array(event["position"])*2
                r = (12+age*40)*2
                d.ellipse((x-r, y-r, x+r, y+r), outline=(255, 255, 255, int(230*(1-age/.20))), width=3)
                if event["cyan_count"] <= 4:
                    self._centered(d, x/2, y/2-32-age*22, "+1", 17, "#ffffff")
        for i, (px, py) in enumerate(positions):
            x, y = px*2, py*2
            age = time-wakes[i]
            pop = 1 + (.16*np.sin(np.pi*age/.18) if i != 0 and 0 <= age < .18 else 0)
            r = self.cfg.bead_radius*pop*2
            d.ellipse((x-r, y-r, x+r, y+r), fill=self.cyan if active[i] else self.ivory,
                      outline="#070e16", width=4)
            # A small flat mark helps individual beads stay visible in dense cyan motion.
            d.ellipse((x-5, y-6, x-1, y-2), fill=(255, 255, 255, 140 if active[i] else 100))
        for miss in self.scene.near_misses:
            age = time-miss["time_seconds"]
            if 0 <= age < .32:
                x, y = positions[42]
                self._centered(d, x, y+20, "MISS!", 15, "#ffedbd")
        d.rounded_rectangle((22*2, 547*2, 338*2, 587*2), radius=12, fill="#182733")
        self._centered(d, 103, 557, f"{43-remaining} MOVING", 19, self.cyan)
        self._centered(d, 264, 554, f"{remaining} LEFT", 25, self.ivory)
        caption = ("WATCH THE FIRST HITS" if time < 7 else "IT'S SPREADING" if time < 16 else
                   "PICK YOUR SURVIVOR" if remaining > 1 else "LAST BEAD STANDING" if remaining == 1
                   else "ALL AWAKE. AGAIN?")
        self._centered(d, 180, 605, caption, 17, "#ffffff")
        return canvas.resize((360, 640), Image.Resampling.LANCZOS)


def make_sound(scene, path):
    cfg = scene.cfg
    rate = cfg.audio_sample_rate
    mix = np.zeros((round(cfg.duration_seconds*rate), 2), dtype=float)
    rng = np.random.Generator(np.random.PCG64(cfg.seed+9000))

    def add(time, mono, x):
        start = round(time*rate)
        count = min(len(mono), len(mix)-start)
        pan = np.clip(x/360, .12, .88)
        mix[start:start+count] += mono[:count, None]*np.array([np.sqrt(1-pan), np.sqrt(pan)])

    melody = [0, 4, 7, 9, 7, 4]
    for number, event in enumerate(scene.events):
        final = event["target"] == 42
        length = .42 if final else .135
        t = np.arange(round(length*rate))/rate
        frequency = 523.251*2**(melody[number % len(melody)]/12)
        attack = np.minimum(1, t/.002)
        if final:
            note = sum(np.sin(2*np.pi*f*t)*np.exp(-t/.13) for f in (261.626, 523.251, 659.255, 783.991))*.14
        else:
            note = (.27*np.sin(2*np.pi*frequency*t)*np.exp(-t/.042)
                    + .075*np.sin(2*np.pi*frequency*2.01*t)*np.exp(-t/.018))
        click = rng.normal(0, .06 if final else .045, len(t))*np.exp(-t/.006)
        note = (note+click)*attack
        note[-128:] *= np.linspace(1, 0, 128)
        add(event["time_seconds"], note, event["position"][0])
    for miss in scene.near_misses:
        t = np.arange(round(.20*rate))/rate
        noise = rng.normal(0, 1, len(t))
        noise = np.convolve(noise, np.ones(7)/7, mode="same")
        whoosh = (.10*noise + .022*np.sin(2*np.pi*(1800*t-2600*t*t)))*np.sin(np.pi*t/.2)**2
        add(miss["time_seconds"]-.08, whoosh, 252)
    # Quiet dry wall ticks provide activity, while conversion notes remain foreground.
    # Thin the taps during the final focus so misses and the last hit remain distinct.
    for number, tap in enumerate(scene.wall_taps):
        if tap["time_seconds"] > 20.6 and number % 4:
            continue
        t = np.arange(round(.025*rate))/rate
        tick = .024*np.sin(2*np.pi*1550*t)*np.exp(-t/.004)*np.minimum(1, t/.001)
        add(tap["time_seconds"], tick, tap["x"])
    peak = float(np.abs(mix).max())
    mix *= min(1.5, .88/max(peak, .001))
    mix[-480:] *= np.linspace(1, 0, 480)[:, None]
    with wave.open(str(path), "wb") as file:
        file.setnchannels(2)
        file.setsampwidth(2)
        file.setframerate(rate)
        file.writeframes((mix*32767).astype("<i2").tobytes())
    return {"sample_rate": rate, "channels": 2, "peak": float(np.abs(mix).max()),
            "conversion_notes": len(scene.events), "near_miss_whooshes": len(scene.near_misses)}


def contact_sheet(video, output):
    frames = [15, 183, 414, 570, 642, 696]
    captions = ["0.50 s / PREMISE", "6.10 s / TEACHING", "13.80 s / COMPOUNDING",
                "19.00 s / ESCALATION", "21.40 s / LAST SURVIVOR", "23.20 s / FINAL HIT"]
    expression = "+".join(f"eq(n,{n})" for n in frames)
    result = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"select='{expression}'",
                             "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                            check=True, capture_output=True)
    size = 360*640*3
    assert len(result.stdout) == 6*size
    sheet = Image.new("RGB", (1152, 1450), "#101923")
    d = ImageDraw.Draw(sheet)
    face = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    d.text((24, 20), "MS03 / LAST BEAD STANDING / ROUGH CUT", font=ImageFont.truetype(face, 28), fill="#ffedbd")
    for cell, caption in enumerate(captions):
        im = Image.frombytes("RGB", (360, 640), result.stdout[cell*size:(cell+1)*size])
        x, y = 24+(cell % 3)*372, 75+(cell//3)*684
        sheet.paste(im, (x, y))
        d.text((x, y+647), caption, font=ImageFont.truetype(face, 16), fill="#31e4ed")
    sheet.save(output)


def export(scene, output, overwrite=False):
    names = ["ms03-review.mp4", "ms03-muted.mp4", "ms03-contact-sheet.png", "ms03-audio.wav", "ms03-events.json"]
    if not overwrite and any((output/name).exists() for name in names):
        raise FileExistsError("MS03 review outputs exist; use --overwrite to replace only this rough cut")
    output.mkdir(parents=True, exist_ok=True)
    renderer = GameRenderer(scene)
    cfg = scene.cfg
    # Same streaming RGB24 -> libx264 path used by the existing export pipeline.
    # Audio is muxed afterwards; none of the assembly export code is changed.
    with tempfile.TemporaryDirectory(prefix=".ms03-", dir=output) as staging:
        staging = Path(staging)
        muted = staging/names[1]
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                   "-s:v", "360x640", "-r", "30", "-i", "pipe:0", "-an", "-c:v", "libx264", "-crf", "19",
                   "-preset", "medium", "-threads", "1", "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(muted)]
        with (staging/"encoder.log").open("w+b") as log:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log)
            try:
                for frame in range(round(cfg.duration_seconds*cfg.fps)):
                    process.stdin.write(renderer.render(frame).tobytes())
                    if frame % 120 == 0:
                        print(f"MS03: {frame}/720 frames", flush=True)
                process.stdin.close()
                if process.wait() != 0:
                    raise BrokenPipeError("encoding failed")
            except BrokenPipeError as error:
                process.wait()
                log.seek(0)
                raise RuntimeError(log.read().decode(errors="replace")[-3000:]) from error
            finally:
                if not process.stdin.closed:
                    try:
                        process.stdin.close()
                    except BrokenPipeError:
                        pass
                if process.poll() is None:
                    process.terminate()
                    process.wait()
        audio_info = make_sound(scene, staging/names[3])
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(muted), "-i", str(staging/names[3]),
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "160k", "-t", "24", "-movflags", "+faststart",
                        str(staging/names[0])], check=True)
        contact_sheet(staging/names[0], staging/names[2])
        data = {"scene": "MS03 — Last Bead Standing", "status": "rough cut; owner/wife creative review pending",
                "seed": cfg.seed, "duration_seconds": 24, "fps": 30, "ivory_count": 42,
                "model": "directed collision choreography; passive billiard-like motion, not uncontrolled physics",
                "events": scene.events, "near_misses": scene.near_misses, "audio": audio_info,
                "source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
                "reset_seconds": cfg.reset_seconds}
        (staging/names[4]).write_text(json.dumps(data, indent=2)+"\n")
        for name in names:
            (staging/name).replace(output/name)
    return data


def main():
    parser = argparse.ArgumentParser(description="MS03 review cut only; no final-master export")
    parser.add_argument("--config", type=Path, default=Path("configs/ms03.toml"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/ms03"))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    settings = Settings(**tomllib.loads(args.config.read_text()))
    print("Planning the directed collision sequence…", flush=True)
    scene = LastBeadStanding(settings)
    result = export(scene, args.output_dir, args.overwrite)
    print(f"Saved MS03 review package to {args.output_dir}; {len(result['events'])} conversions, two near misses")


if __name__ == "__main__":
    main()
