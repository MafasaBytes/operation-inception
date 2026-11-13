"""MS03B: one text-free, directed two-color contest, isolated from prior cuts."""

import argparse
from dataclasses import asdict, dataclass
import hashlib
import json
from pathlib import Path
import subprocess
import tempfile
import tomllib
import wave

import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFont

from .ms03 import hermite


@dataclass(frozen=True)
class Settings:
    seed: int = 3032
    width: int = 720
    height: int = 1280
    fps: int = 30
    duration_seconds: float = 24
    neutral_count: int = 40
    bead_radius: float = 10.5
    arena_radius: float = 195
    arena_y_stretch: float = 1.25
    reset_seconds: float = 23.9
    video_bitrate: str = "8M"
    audio_sample_rate: int = 48000

    def __post_init__(self):
        if (self.width, self.height, self.fps) != (720, 1280, 30):
            raise ValueError("MS03B exports only a 720x1280, 30 FPS review cut")
        if self.neutral_count != 40 or self.duration_seconds != 24:
            raise ValueError("This treatment has two movers, 40 neutrals, and a 24-second timeline")
        if self.bead_radius != 10.5 or self.arena_radius != 195 or self.arena_y_stretch != 1.25:
            raise ValueError("Keep the authored review composition fixed")


def story_events():
    # Team 1 = cyan, team 2 = orange. No score or timeline appears in the video.
    result = [(t, team, "recruit") for t, team in
              ((.8, 1), (1.8, 2), (3.1, 1), (4., 2), (5.1, 1), (6., 2), (7., 1), (7.8, 2))]
    for i, u in enumerate(np.linspace(0, 1, 32)):
        result.append((8.2+7.6*u**.78, 1 if i % 4 < 2 else 2, "recruit"))
    result += [(t, 1, "capture") for t in np.linspace(16.12, 17.2, 5)]
    result += [(t, 2, "capture") for t in np.linspace(17.46, 19.02, 12)]
    result += [(t, 1, "capture") for t in np.linspace(19.16, 21.06, 20)]
    result += [(21.23+1.95*u**.70, 2, "cascade") for u in np.linspace(0, 1, 34)]
    return result


class ColorWar:
    """An authored contest, with explicit directed contacts and seeded free motion."""

    def __init__(self, cfg):
        self.cfg = cfg
        self.rng = np.random.Generator(np.random.PCG64(cfg.seed))
        self.center = np.array([180., 320.])
        a = np.deg2rad(np.arange(6)*60-90)
        self.vertices = self.center + cfg.arena_radius*np.column_stack((np.cos(a), np.sin(a)*cfg.arena_y_stretch))
        edges = np.roll(self.vertices, -1, axis=0)-self.vertices
        self.normals = np.column_stack((edges[:, 1], -edges[:, 0]))
        self.normals /= np.linalg.norm(self.normals, axis=1)[:, None]
        self.bounds = np.sum((self.vertices-self.center)*self.normals, axis=1)
        self.position = self._initial_positions()
        self.velocity = np.zeros((42, 2))
        self.velocity[0], self.velocity[1] = [42, 0], [-42, 0]
        self.color = np.zeros(42, dtype=np.uint8)
        self.color[:2] = [1, 2]
        self.changed = np.full(42, -100.)
        self.tracks = {}
        self.events = []
        self.wall_taps = []
        self.history, self.colors, self.changes = [], [], []
        self.phase = self.rng.uniform(0, 2*np.pi, 42)
        self.dt = 1/120
        self._simulate()

    def _initial_positions(self):
        points = {0: np.array([90., 205.]), 1: np.array([270., 435.]),
                  2: np.array([140., 205.]), 3: np.array([220., 435.])}
        for i in range(4, 42):
            for _ in range(20000):
                p = self.rng.uniform([30, 103], [330, 537])
                if np.any((p-self.center)@self.normals.T > self.bounds-self.cfg.bead_radius-6):
                    continue
                if min(np.linalg.norm(p-q) for q in points.values()) < 33:
                    continue
                if min(np.linalg.norm(p-q) for q in ([108, 205], [252, 435])) < 50:
                    continue
                points[i] = p
                break
            else:
                raise ValueError("Cannot place the neutral population")
        return np.array([points[i] for i in range(42)])

    def _path(self, track, time):
        duration = track["end"]-track["start"]
        u = np.clip((np.asarray(time)-track["start"])/duration, 0, 1)
        if np.ndim(u):
            return np.array([hermite(track["a"], track["va"], track["b"], track["vb"], v, duration) for v in u])
        return hermite(track["a"], track["va"], track["b"], track["vb"], u, duration)

    def _plan(self, due, team, kind, time, number):
        source_ids = [int(i) for i in np.flatnonzero(self.color == team) if i not in self.tracks]
        target_color = 0 if kind == "recruit" else 3-team
        target_ids = [int(i) for i in np.flatnonzero(self.color == target_color) if i not in self.tracks]
        if number < 2:
            source_ids, target_ids = [number], [number+2]
        candidates = []
        for source in source_ids:
            for target in target_ids:
                distance = np.linalg.norm(self.position[source]-self.position[target])
                # Recent converts near a frontier become attackers in the next beats.
                recent = 12 if kind == "cascade" and time-self.changed[source] < .5 else 0
                candidates.append((distance-recent, source, target))
        for _, source, target in sorted(candidates):
            duration = due-time
            target_a = self.position[target].copy()
            target_va = self.velocity[target]*.30 if target_color else np.zeros(2)
            target_b = target_a + target_va*min(duration, .18)*.45
            victim = dict(a=target_a, va=target_va, b=target_b, vb=np.zeros(2), start=time, end=due,
                          role="victim", other=source)
            a = self.position[source].copy()
            normal = (a-target_b)/np.linalg.norm(a-target_b)
            b = target_b + normal*2*self.cfg.bead_radius
            speed = min(230, max(60, np.linalg.norm(a-b)/duration))
            attacker = dict(a=a, va=self.velocity[source]*.45, b=b, vb=-normal*speed,
                            start=time, end=due, role="attacker", other=target, team=team, kind=kind)
            times = np.linspace(time, due, 41)
            pa, pb = self._path(attacker, times), self._path(victim, times)
            if np.min(np.linalg.norm(pa[:-1]-pb[:-1], axis=1)) < 2*self.cfg.bead_radius-.01:
                continue
            if any(np.any((path-self.center)@self.normals.T > self.bounds-self.cfg.bead_radius-2) for path in (pa, pb)):
                continue
            neutral = [i for i in np.flatnonzero(self.color == 0) if i != target]
            if neutral and any(np.min(np.linalg.norm(path[:, None]-self.position[neutral][None], axis=2)) < 2*self.cfg.bead_radius+3 for path in (pa, pb)):
                continue
            blocked = False
            for other, track in self.tracks.items():
                other_path = self._path(track, np.minimum(times, track["end"]))
                for bead, path in ((source, pa), (target, pb)):
                    if self.color[bead] != self.color[other] and np.min(np.linalg.norm(path-other_path, axis=1)) < 2*self.cfg.bead_radius+2:
                        blocked = True
                        break
                if blocked:
                    break
            if blocked:
                continue
            self.tracks[source], self.tracks[target] = attacker, victim
            return
        raise ValueError(f"No readable contact route at {due:.3f}s, team {team}, kind {kind}; available {len(source_ids)}/{len(target_ids)}")

    def _record_contact(self, source, track, time):
        target, team = track["other"], track["team"]
        distance = np.linalg.norm(self.position[source]-self.position[target])
        assert abs(distance-2*self.cfg.bead_radius) < .05
        before = int(self.color[target])
        assert self.color[source] == team and before != team
        self.color[target] = team
        self.changed[target] = time
        normal = (self.position[source]-self.position[target])/distance
        tangent = np.array([-normal[1], normal[0]])
        speed = 56 if time < 8 else 116
        self.velocity[source] = (normal+.24*tangent)*speed
        self.velocity[target] = (-normal+.25*tangent)*speed
        counts = [int(np.sum(self.color == c)) for c in (0, 1, 2)]
        self.events.append(dict(time_seconds=round(time, 6), source=source, target=target,
                                team=team, previous_color=before, kind=track["kind"],
                                position=self.position[target].tolist(), contact_distance=float(distance),
                                neutral=counts[0], cyan=counts[1], orange=counts[2]))

    def _simulate(self):
        events = story_events()
        planned = set()
        diameter = 2*self.cfg.bead_radius
        for step in range(round(self.cfg.duration_seconds/self.dt)):
            time = step*self.dt
            if time >= self.cfg.reset_seconds:
                self.history.append(self.history[0].copy())
                self.colors.append(self.colors[0].copy())
                self.changes.append(np.full(42, -100.))
                continue
            for number, (due, team, kind) in enumerate(events):
                lead = .68 if due < 8 else .38 if kind == "recruit" else .32 if kind == "capture" else .21
                if number not in planned and time >= due-lead-1e-9:
                    self._plan(due, team, kind, time, number)
                    planned.add(number)
            active = np.flatnonzero(self.color)
            speed = 48+68*np.clip((time-8)/8, 0, 1)
            for i in active:
                if i in self.tracks:
                    continue
                obstacles = np.flatnonzero(self.color != self.color[i])
                if len(obstacles):
                    delta = self.position[i]-self.position[obstacles]
                    distances = np.linalg.norm(delta, axis=1)
                    field = np.clip((51-distances)/24, 0, 1)**2
                    self.velocity[i] += np.sum(delta/np.maximum(distances[:, None], .01)*field[:, None], axis=0)*230*self.dt
                self.velocity[i] += np.array([np.cos(time*1.7+self.phase[i]), np.sin(time*1.3+self.phase[i])])*5*self.dt
                self.velocity[i] *= speed/max(.01, np.linalg.norm(self.velocity[i]))
                self.position[i] += self.velocity[i]*self.dt
            for i, track in self.tracks.items():
                self.position[i] = self._path(track, time)
            for source, track in list(self.tracks.items()):
                if track["role"] == "attacker" and time >= track["end"]-1e-9:
                    self._record_contact(source, track, time)
                    del self.tracks[source]
                    del self.tracks[track["other"]]
            active = np.flatnonzero(self.color)
            # Non-attacking opponents keep a visible gap. Scheduled pairs alone
            # enter contact, so every pictured cross-color hit has one clear result.
            pairs = {tuple(sorted((i, tr["other"]))) for i, tr in self.tracks.items()}
            for _ in range(2):
                for i in range(42):
                    for j in range(i+1, 42):
                        if not (self.color[i] or self.color[j]) or (i, j) in pairs:
                            continue
                        opposite = self.color[i] != self.color[j]
                        required = diameter+5 if opposite else diameter
                        delta = self.position[i]-self.position[j]
                        distance = np.linalg.norm(delta)
                        if .001 < distance < required:
                            movable = [k for k in (i, j) if self.color[k] and k not in self.tracks]
                            if not movable:
                                if opposite and distance < diameter-.1:
                                    raise ValueError(f"Unmarked cross-color contact at {time:.3f}s")
                                continue
                            normal = delta/distance
                            correction = (required-distance+.01)/len(movable)
                            for bead in movable:
                                self.position[bead] += (1 if bead == i else -1)*normal*correction
                            relative = np.dot(self.velocity[i]-self.velocity[j], normal)
                            if relative < 0:
                                for bead in movable:
                                    self.velocity[bead] -= (1 if bead == i else -1)*relative*normal
                for i in active:
                    if i in self.tracks:
                        continue
                    for normal, bound in zip(self.normals, self.bounds):
                        over = np.dot(self.position[i]-self.center, normal)-(bound-self.cfg.bead_radius-2)
                        if over > 0:
                            self.position[i] -= (over+.01)*normal
                            self.velocity[i] -= 2*max(0, np.dot(self.velocity[i], normal))*normal
                            if not self.wall_taps or time-self.wall_taps[-1]["time_seconds"] > .15:
                                self.wall_taps.append(dict(time_seconds=time, x=float(self.position[i, 0]), team=int(self.color[i])))
            self.history.append(self.position.copy())
            self.colors.append(self.color.copy())
            self.changes.append(self.changed.copy())
        self.history, self.colors, self.changes = map(np.array, (self.history, self.colors, self.changes))
        assert len(self.events) == len(events)
        assert all(e["neutral"]+e["cyan"]+e["orange"] == 42 for e in self.events)
        assert self.events[-1]["orange"] == 42 and self.events[-1]["cyan"] == 0


PALETTE = {0: "#fff0c6", 1: "#00efff", 2: "#ff6905"}


class WarRenderer:
    """Draw geometry only. There are deliberately no text, font, or HUD calls here."""

    def __init__(self, scene):
        self.scene = scene
        self.scale = 4  # 1440x2560 working canvas -> antialiased 720x1280 output.
        self.background = Image.new("RGB", (1440, 2560), "#0c1420")
        self.polygon = [tuple(p*self.scale) for p in scene.vertices]
        self.rgb = {c: ImageColor.getrgb(color) for c, color in PALETTE.items()}
        d = ImageDraw.Draw(self.background)
        d.polygon(self.polygon, fill="#142330")

    def render(self, frame):
        time = frame/self.scene.cfg.fps
        step = round(time/self.scene.dt)
        p = self.scene.history[step]
        colors = self.scene.colors[step]
        changed = self.scene.changes[step]
        reset = time >= self.scene.cfg.reset_seconds
        if reset:
            time = 0
        canvas = self.background.copy()
        d = ImageDraw.Draw(canvas, "RGBA")
        unique = set(map(int, colors))
        border = PALETTE[next(iter(unique))] if len(unique) == 1 and 0 not in unique else "#d6e0e7"
        d.line(self.polygon+[self.polygon[0]], fill=border, width=18, joint="curve")
        previous = self.scene.history[max(0, step-5)] if not reset and frame else p
        for i in np.flatnonzero(colors):
            tail = p[i]+np.clip(previous[i]-p[i], -10, 10)
            d.line((*tail*self.scale, *p[i]*self.scale), fill=(*self.rgb[int(colors[i])], 120), width=18)
        # A local outline at each contact reinforces the color flip, without
        # whitening the bodies or replacing the cascade with decorative light.
        for event in self.scene.events:
            age = time-event["time_seconds"]
            if 0 <= age < .12:
                x, y = np.array(event["position"])*self.scale
                r = (12+age*22)*self.scale
                d.ellipse((x-r, y-r, x+r, y+r), outline=(*self.rgb[event["team"]], int(190*(1-age/.12))), width=5)
        for i, pos in enumerate(p):
            age = time-changed[i]
            pop = 1 + (.10*np.sin(np.pi*age/.12) if 0 <= age < .12 else 0)
            r = self.scene.cfg.bead_radius*self.scale*pop
            x, y = pos*self.scale
            d.ellipse((x-r, y-r, x+r, y+r), fill=PALETTE[int(colors[i])], outline="#02070d", width=12)
        return canvas.resize((720, 1280), Image.Resampling.LANCZOS)


def make_sound(scene, path):
    rate = scene.cfg.audio_sample_rate
    rng = np.random.Generator(np.random.PCG64(scene.cfg.seed+9000))
    mix = np.zeros((24*rate, 2))

    def add(time, mono, x):
        start = round(time*rate)
        n = min(len(mono), len(mix)-start)
        pan = np.clip(x/360, .15, .85)
        mix[start:start+n] += mono[:n, None]*np.sqrt([1-pan, pan])

    melody = [0, 4, 7, 9, 7, 4, 2, 0]
    team_hits = {1: 0, 2: 0}
    for index, event in enumerate(scene.events):
        team = event["team"]
        capture = event["previous_color"] != 0
        final = index == len(scene.events)-1
        length = .46 if final else .10 if event["kind"] == "cascade" else .15
        t = np.arange(round(length*rate))/rate
        base = 523.251 if team == 1 else 261.626
        freq = base*2**(melody[team_hits[team] % len(melody)]/12)
        team_hits[team] += 1
        attack = np.minimum(1, t/.0015)
        if final:
            tone = sum(np.sin(2*np.pi*base*ratio*t)*np.exp(-t/.14) for ratio in (1, 1.25, 1.5, 2))*.12
        elif team == 1:
            tone = (.25*np.sin(2*np.pi*freq*t)*np.exp(-t/.036)
                    + .07*np.sin(2*np.pi*3.01*freq*t)*np.exp(-t/.014))
        else:
            tone = (.29*np.sin(2*np.pi*freq*t)*np.exp(-t/.048)
                    + .08*np.sin(2*np.pi*2.0*freq*t)*np.exp(-t/.024))
        transient = rng.normal(0, .095 if capture else .035, len(t))*np.exp(-t/.004)
        note = (tone+transient)*attack*(1.15 if capture else 1)
        note[-128:] *= np.linspace(1, 0, 128)
        add(event["time_seconds"], note, event["position"][0])
    # Soft wall taps are supporting punctuation, never a substitute for captures.
    for tap in scene.wall_taps:
        t = np.arange(round(.018*rate))/rate
        tick = .014*np.sin(2*np.pi*(1700 if tap["team"] == 1 else 900)*t)*np.exp(-t/.003)
        add(tap["time_seconds"], tick, tap["x"])
    mix *= min(1.5, .88/max(.001, np.abs(mix).max()))
    mix[-480:] *= np.linspace(1, 0, 480)[:, None]
    with wave.open(str(path), "wb") as file:
        file.setnchannels(2)
        file.setsampwidth(2)
        file.setframerate(rate)
        file.writeframes((mix*32767).astype("<i2").tobytes())
    return dict(sample_rate=rate, channels=2, peak=float(np.abs(mix).max()), team_notes=team_hits)


def contact_sheet(video, path):
    # This annotated artifact is outside the video and contains outcome spoilers.
    indices = [60, 210, 519, 573, 633, 699]
    captions = ["2.00 s / OPENING", "7.00 s / RECRUITMENT", "17.30 s / CONTROL",
                "19.10 s / REVERSAL", "21.10 s / THREAT", "23.30 s / RESOLUTION"]
    expression = "+".join(f"eq(n,{n})" for n in indices)
    result = subprocess.run(["ffmpeg", "-v", "error", "-i", str(video), "-vf", f"select='{expression}',scale=360:640",
                             "-fps_mode", "passthrough", "-f", "rawvideo", "-pix_fmt", "rgb24", "pipe:1"],
                            check=True, capture_output=True)
    stride = 360*640*3
    assert len(result.stdout) == 6*stride
    sheet = Image.new("RGB", (1152, 1450), "#0c1420")
    d = ImageDraw.Draw(sheet)
    face = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
    d.text((24, 20), "MS03B / COLOR WAR / REVIEW SPOILERS", font=ImageFont.truetype(face, 28), fill="#fff0c6")
    for cell, caption in enumerate(captions):
        im = Image.frombytes("RGB", (360, 640), result.stdout[cell*stride:(cell+1)*stride])
        x, y = 24+(cell % 3)*372, 75+(cell//3)*684
        sheet.paste(im, (x, y))
        d.text((x, y+647), caption, font=ImageFont.truetype(face, 16), fill="#d6e0e7")
    sheet.save(path)


def export(scene, output, overwrite=False):
    names = ["ms03b-review.mp4", "ms03b-muted.mp4", "ms03b-contact-sheet.png", "ms03b-audio.wav", "ms03b-events.json"]
    if not overwrite and any((output/name).exists() for name in names):
        raise FileExistsError("MS03B outputs exist; use --overwrite to replace only this cut")
    output.mkdir(parents=True, exist_ok=True)
    renderer = WarRenderer(scene)
    cfg = scene.cfg
    smallest_opposing_gap = float("inf")
    for positions, colors in zip(scene.history, scene.colors):
        different = colors[:, None] != colors[None, :]
        if different.any():
            distances = np.linalg.norm(positions[:, None]-positions[None, :], axis=2)
            smallest_opposing_gap = min(smallest_opposing_gap, float(distances[different].min()-2*cfg.bead_radius))
    if smallest_opposing_gap < -.1:
        raise ValueError(f"An unmarked cross-color body overlap remains: {smallest_opposing_gap:.3f}px")
    assert renderer.render(0).tobytes() == renderer.render(719).tobytes()
    with tempfile.TemporaryDirectory(prefix=".ms03b-", dir=output) as staging:
        staging = Path(staging)
        muted = staging/names[1]
        # Deliberate high-bitrate CBR, including HRD filler when flat graphics are
        # cheap to compress. The requested review delivery is not a low-rate proxy.
        command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
                   "-s:v", "720x1280", "-r", "30", "-i", "pipe:0", "-an", "-c:v", "libx264",
                   "-vf", "scale=in_range=pc:out_range=tv:out_color_matrix=bt709",
                   "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709", "-color_range", "tv",
                   "-preset", "slow", "-profile:v", "high", "-threads", "2", "-pix_fmt", "yuv420p",
                   "-b:v", cfg.video_bitrate, "-minrate", cfg.video_bitrate, "-maxrate", cfg.video_bitrate,
                   "-bufsize", "16M", "-g", "30", "-x264-params", "nal-hrd=cbr:force-cfr=1",
                   "-movflags", "+faststart", str(muted)]
        with (staging/"encoder.log").open("w+b") as log:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log)
            try:
                for frame in range(720):
                    process.stdin.write(renderer.render(frame).tobytes())
                    if frame % 90 == 0:
                        print(f"MS03B: {frame}/720 frames", flush=True)
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
        audio = make_sound(scene, staging/names[3])
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(muted), "-i", str(staging/names[3]),
                        "-c:v", "copy", "-c:a", "aac", "-b:a", "192k", "-t", "24", "-movflags", "+faststart",
                        str(staging/names[0])], check=True)
        contact_sheet(staging/names[0], staging/names[2])
        data = dict(scene="MS03B — Color War", status="phone creative review pending",
                    configuration=asdict(cfg), model="authored directed contacts with seeded free motion",
                    events=scene.events, audio=audio, palette=PALETTE,
                    checks=dict(minimum_unmarked_opposing_edge_gap_logical_pixels=smallest_opposing_gap,
                                raw_loop_endpoints_identical=True, contact_count=len(scene.events)),
                    source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
        (staging/names[4]).write_text(json.dumps(data, indent=2)+"\n")
        for name in names:
            (staging/name).replace(output/name)
    return data


def main():
    parser = argparse.ArgumentParser(description="MS03B Color War: 720p review only, no master export")
    parser.add_argument("--config", type=Path, default=Path("configs/ms03b.toml"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/ms03b"))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    cfg = Settings(**tomllib.loads(args.config.read_text()))
    print("Planning both teams' directed contacts…", flush=True)
    scene = ColorWar(cfg)
    export(scene, args.output_dir, args.overwrite)
    print(f"Saved 720p Color War review package to {args.output_dir}")


if __name__ == "__main__":
    main()
