"""MS04.4 event-driven vertical review render for one genuine selected match."""

import argparse
from bisect import bisect_left, bisect_right
from dataclasses import asdict, dataclass, replace
import hashlib
import json
import math
from pathlib import Path
import re
import subprocess
import tempfile
import tomllib

import numpy as np
from PIL import Image, ImageColor, ImageDraw, ImageFont

from .audio.events import AudioEvent, EventLog, Team
from .audio.synthesis import synthesize, write_wav
from .presentation import PresentationClock, PresentationPlan, build_plan, load_selected_candidate


SCHEMA_VERSION = "ms04.4.presentation.v1"
HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
OUTPUT_NAMES = (
    "ms04.4-review.mp4",
    "ms04.4-muted.mp4",
    "ms04.4-contact-sheet.png",
    "ms04.4-audio.wav",
    "ms04.4-timeline.json",
    "ms04.4-manifest.json",
)


@dataclass(frozen=True)
class RenderSettings:
    width: int
    height: int
    fps: int
    supersample: int
    board_left: int
    board_top: int
    cell_size: int
    cell_gap: int
    background_top: str
    background_bottom: str
    cell_fill: str
    grid_line: str
    orb_outline: str
    players: tuple[str, ...]
    team_colors: tuple[str, ...]
    crf: int

    def __post_init__(self) -> None:
        for name in ("width", "height", "fps", "supersample", "board_left", "board_top",
                     "cell_size", "cell_gap", "crf"):
            if type(getattr(self, name)) is not int:
                raise ValueError(f"render.{name} must be an integer")
        if (self.width, self.height, self.fps) != (720, 1280, 30):
            raise ValueError("MS04.4 review is fixed at 720x1280, 30 FPS")
        if not 1 <= self.supersample <= 3 or not 0 <= self.crf <= 30:
            raise ValueError("invalid supersample or CRF")
        if min(self.board_left, self.board_top, self.cell_size) <= 0 or not 0 <= self.cell_gap <= self.cell_size // 8:
            raise ValueError("invalid board geometry")
        if self.board_left + 6 * self.cell_size > self.width - 96:
            raise ValueError("board must retain the approved right-side safe margin")
        if self.board_top + 9 * self.cell_size > self.height - 240:
            raise ValueError("board must retain the approved lower safe margin")
        if type(self.players) is not tuple or not 2 <= len(self.players) <= 8 or len(set(self.players)) != len(self.players):
            raise ValueError("render players must be two to eight unique ids")
        if type(self.team_colors) is not tuple or len(self.team_colors) != len(self.players):
            raise ValueError("every render player requires one color")
        colors = (self.background_top, self.background_bottom, self.cell_fill,
                  self.grid_line, self.orb_outline, *self.team_colors)
        if any(not isinstance(color, str) or not HEX_COLOR.fullmatch(color) for color in colors):
            raise ValueError("render colors must use #RRGGBB")


@dataclass(frozen=True)
class AudioSettings:
    seed: int
    sample_rate: int
    channels: int
    voices: tuple[int, ...]
    charged_ratio_minimum: float

    def __post_init__(self) -> None:
        if type(self.seed) is not int or self.seed < 0:
            raise ValueError("audio seed must be nonnegative")
        if type(self.sample_rate) is not int or not 16000 <= self.sample_rate <= 96000:
            raise ValueError("audio sample rate must be 16000..96000")
        if self.channels not in (1, 2):
            raise ValueError("audio channels must be one or two")
        if type(self.voices) is not tuple or not 2 <= len(self.voices) <= 8 or len(set(self.voices)) != len(self.voices):
            raise ValueError("audio voices must be two to eight unique indices")
        if any(type(voice) is not int or not 0 <= voice < 8 for voice in self.voices):
            raise ValueError("audio voices must lie in 0..7")
        if type(self.charged_ratio_minimum) not in (int, float) or not .5 <= self.charged_ratio_minimum <= 1:
            raise ValueError("charged_ratio_minimum must be in .5..1")


@dataclass(frozen=True)
class MS04Settings:
    config_path: Path
    search_output: Path
    match_id: str
    clock: PresentationClock
    render: RenderSettings
    audio: AudioSettings


def load_settings(path: str | Path) -> MS04Settings:
    with Path(path).open("rb") as file:
        data = tomllib.load(file)
    if set(data) != {"schema_version", "source", "clock", "render", "audio"}:
        raise ValueError("MS04.4 configuration sections do not match the contract")
    if data["schema_version"] != SCHEMA_VERSION or set(data["source"]) != {"search_output", "match_id"}:
        raise ValueError("unsupported MS04.4 configuration")
    render = dict(data["render"])
    audio = dict(data["audio"])
    render["players"] = tuple(render["players"])
    render["team_colors"] = tuple(render["team_colors"])
    audio["voices"] = tuple(audio["voices"])
    return MS04Settings(
        config_path=Path(path),
        search_output=Path(data["source"]["search_output"]),
        match_id=data["source"]["match_id"],
        clock=PresentationClock(**data["clock"]),
        render=RenderSettings(**render),
        audio=AudioSettings(**audio),
    )


def build_audio_log(plan: PresentationPlan, settings: AudioSettings) -> EventLog:
    if len(settings.voices) != len(plan.players):
        raise ValueError("audio voice assignments must match presentation players")
    teams = tuple(Team(player, voice) for player, voice in zip(plan.players, settings.voices))
    audio_events = []
    supported = {
        "orb_placed", "cell_charged", "cell_became_critical", "cell_exploded",
        "neighbor_captured", "cascade_depth_increased", "player_eliminated", "winner_declared",
    }
    for item in plan.events:
        event = item.event
        if event.kind not in supported:
            continue
        if event.kind == "neighbor_captured" and event.previous_owner is None:
            continue
        if event.kind == "cell_charged":
            ratio = event.orb_count / event.critical_mass
            if ratio < settings.charged_ratio_minimum:
                continue
        audio_events.append(AudioEvent(
            id=f"ms04.4.audio.{event.id}",
            sequence=len(audio_events),
            time_seconds=item.time_seconds,
            kind=event.kind,
            team_id=event.player_id,
            cell=event.cell,
            orb_count=event.orb_count,
            critical_mass=event.critical_mass,
            cascade_depth=event.cascade_depth,
            previous_team_id=event.previous_owner,
        ))
    return EventLog(
        schema_version="ms05.audio-events.v1",
        log_id=f"{plan.match_id}.ms04.4",
        synthetic=False,
        duration_seconds=plan.duration_seconds,
        teams=teams,
        events=tuple(audio_events),
    )


def _mix(a, b, amount):
    return tuple(round(x + (y - x) * amount) for x, y in zip(a, b))


class GameRenderer:
    """Draws snapshots from the shared presentation clock; never resolves rules."""

    def __init__(self, plan: PresentationPlan, settings: RenderSettings):
        if settings.players != plan.players:
            raise ValueError("render players must match the selected match")
        self.plan = plan
        self.cfg = settings
        self.scale = settings.supersample
        self.size = (settings.width * self.scale, settings.height * self.scale)
        self.times = tuple(item.time_seconds for item in plan.events)
        self.palette = {
            player: ImageColor.getrgb(color)
            for player, color in zip(settings.players, settings.team_colors)
        }
        self.background = self._background()
        self.receipts = tuple(item for item in plan.events if item.event.kind == "orb_received")

    def _background(self):
        top = ImageColor.getrgb(self.cfg.background_top)
        bottom = ImageColor.getrgb(self.cfg.background_bottom)
        image = Image.new("RGB", self.size, top)
        draw = ImageDraw.Draw(image)
        for y in range(self.size[1]):
            draw.line((0, y, self.size[0], y), fill=_mix(top, bottom, y / (self.size[1] - 1)))
        return image

    def _box(self, values):
        return tuple(round(value * self.scale) for value in values)

    def _center(self, coordinate):
        row, column = coordinate
        return (
            self.cfg.board_left + (column + .5) * self.cfg.cell_size,
            self.cfg.board_top + (row + .5) * self.cfg.cell_size,
        )

    def _cell_box(self, coordinate):
        row, column = coordinate
        left = self.cfg.board_left + column * self.cfg.cell_size + self.cfg.cell_gap / 2
        top = self.cfg.board_top + row * self.cfg.cell_size + self.cfg.cell_gap / 2
        right = self.cfg.board_left + (column + 1) * self.cfg.cell_size - self.cfg.cell_gap / 2
        bottom = self.cfg.board_top + (row + 1) * self.cfg.cell_size - self.cfg.cell_gap / 2
        return left, top, right, bottom

    def _layout(self, count):
        layouts = {
            1: ((0., 0.),),
            2: ((-.19, 0.), (.19, 0.)),
            3: ((0., -.20), (-.18, .15), (.18, .15)),
            4: ((-.16, -.16), (.16, -.16), (-.16, .16), (.16, .16)),
        }
        if count not in layouts:
            raise ValueError(f"MS04.4 cannot display transient orb count {count}")
        return layouts[count]

    def render(self, time_seconds: float) -> Image.Image:
        canvas = self.background.copy().convert("RGBA")
        draw = ImageDraw.Draw(canvas, "RGBA")
        state_index = bisect_right(self.times, time_seconds) - 1
        state = (
            tuple() if state_index < 0
            else self.plan.snapshots[state_index]
        )
        if state_index < 0:
            from .rules import OrbCell
            state = tuple(OrbCell() for _ in self.plan.grid.cells)
        recent_start = bisect_left(self.times, time_seconds - .28)
        recent_end = bisect_right(self.times, time_seconds)
        recent = self.plan.events[recent_start:recent_end]
        recent_capture = {}
        recent_pop = {}
        for item in recent:
            if item.event.cell is not None:
                if item.event.kind == "neighbor_captured":
                    recent_capture[item.event.cell] = item
                if item.event.kind in {"orb_placed", "orb_received", "neighbor_captured"}:
                    recent_pop[item.event.cell] = item

        winner_age = time_seconds - self.plan.winner_time
        winner_amount = 0 if winner_age < 0 else min(1, winner_age / .28)
        neutral_line = ImageColor.getrgb(self.cfg.grid_line)
        border = _mix(neutral_line, self.palette[self.plan.winner], winner_amount)
        left = self.cfg.board_left
        top = self.cfg.board_top
        right = left + 6 * self.cfg.cell_size
        bottom = top + 9 * self.cfg.cell_size
        draw.rounded_rectangle(self._box((left - 9, top + 12, right + 9, bottom + 18)),
                               radius=18 * self.scale, fill=(0, 0, 0, 105))
        draw.rounded_rectangle(self._box((left - 5, top - 5, right + 5, bottom + 5)),
                               radius=16 * self.scale, fill=(*border, 255))

        base_fill = ImageColor.getrgb(self.cfg.cell_fill)
        for topology, cell in zip(self.plan.grid.cells, state):
            color = base_fill if cell.owner is None else _mix(base_fill, self.palette[cell.owner], .16 + .08 * winner_amount)
            effect = recent_capture.get(topology.coordinate)
            if effect:
                age = time_seconds - effect.time_seconds
                color = _mix(color, self.palette[effect.event.player_id], max(0, 1 - age / .20) * .42)
            draw.rounded_rectangle(self._box(self._cell_box(topology.coordinate)),
                                   radius=8 * self.scale, fill=(*color, 255))

        for receipt in self.receipts:
            travel = receipt.source_time_seconds
            if (receipt.source_cell is not None and travel is not None
                    and travel <= time_seconds < receipt.time_seconds):
                u = (time_seconds - travel) / (receipt.time_seconds - travel)
                u = u * u * (3 - 2 * u)
                ax, ay = self._center(receipt.source_cell)
                bx, by = self._center(receipt.event.cell)
                x, y = ax + (bx - ax) * u, ay + (by - ay) * u
                color = self.palette[receipt.event.player_id]
                draw.line(self._box((ax, ay, bx, by)), fill=(*color, 42), width=3 * self.scale)
                radius = 7
                draw.ellipse(self._box((x - radius * 1.8, y - radius * 1.8,
                                        x + radius * 1.8, y + radius * 1.8)), fill=(*color, 42))
                draw.ellipse(self._box((x - radius, y - radius, x + radius, y + radius)),
                             fill=(*color, 255), outline=ImageColor.getrgb(self.cfg.orb_outline),
                             width=max(1, 2 * self.scale))

        for topology, cell in zip(self.plan.grid.cells, state):
            if cell.owner is None:
                continue
            recent_effect = recent_pop.get(topology.coordinate)
            pop = 1.
            if recent_effect:
                age = time_seconds - recent_effect.time_seconds
                if 0 <= age < .14:
                    pop = .72 + .36 * math.sin(min(1, age / .14) * math.pi / 2)
            if winner_age >= 0 and winner_age < .38:
                pop *= 1 + .08 * math.sin(math.pi * winner_age / .38)
            x0, y0 = self._center(topology.coordinate)
            offsets = self._layout(cell.orb_count)
            radius = self.cfg.cell_size * ({1: .185, 2: .15, 3: .14, 4: .12}[cell.orb_count]) * pop
            color = self.palette[cell.owner]
            for dx, dy in offsets:
                x = x0 + dx * self.cfg.cell_size
                y = y0 + dy * self.cfg.cell_size
                draw.ellipse(self._box((x - radius * 1.22, y - radius * 1.22,
                                        x + radius * 1.22, y + radius * 1.22)), fill=(*color, 28))
                draw.ellipse(self._box((x - radius, y - radius, x + radius, y + radius)),
                             fill=(*color, 255), outline=ImageColor.getrgb(self.cfg.orb_outline),
                             width=max(1, 3 * self.scale))
                hr = radius * .20
                hx, hy = x - radius * .36, y - radius * .38
                draw.ellipse(self._box((hx - hr, hy - hr, hx + hr, hy + hr)),
                             fill=(*_mix(color, (255, 255, 255), .62), 255))

        for item in recent:
            age = time_seconds - item.time_seconds
            if item.event.kind == "cell_exploded" and 0 <= age < .24:
                x, y = self._center(item.event.cell)
                radius = self.cfg.cell_size * (.18 + .70 * age / .24)
                alpha = round(210 * (1 - age / .24))
                draw.ellipse(self._box((x - radius, y - radius, x + radius, y + radius)),
                             outline=(*self.palette[item.event.player_id], alpha), width=4 * self.scale)
            elif item.event.kind == "neighbor_captured" and 0 <= age < .20:
                alpha = round(190 * (1 - age / .20))
                draw.rounded_rectangle(self._box(self._cell_box(item.event.cell)), radius=8 * self.scale,
                                       outline=(*self.palette[item.event.player_id], alpha), width=4 * self.scale)

        output = canvas.convert("RGB")
        if self.scale > 1:
            output = output.resize((self.cfg.width, self.cfg.height), Image.Resampling.LANCZOS)
        return output


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _timeline_record(plan: PresentationPlan, clock: PresentationClock) -> dict:
    return {
        "schema_version": "ms04.4.timeline.v1",
        "match_id": plan.match_id,
        "winner": plan.winner,
        "duration_seconds": plan.duration_seconds,
        "clock": asdict(clock),
        "events": [
            {
                "id": item.event.id,
                "sequence": item.event.sequence,
                "kind": item.event.kind,
                "player_id": item.event.player_id,
                "cell": list(item.event.cell) if item.event.cell is not None else None,
                "source_cell": list(item.source_cell) if item.source_cell is not None else None,
                "source_time_seconds": item.source_time_seconds,
                "time_seconds": item.time_seconds,
                "cascade_depth": item.event.cascade_depth,
            }
            for item in plan.events
        ],
    }


def _contact_sheet(renderer: GameRenderer, plan: PresentationPlan, path: Path) -> list[float]:
    indices = (2, 20, 46, 69, 80, 86)
    times = [plan.turn_start_times[index] + .12 for index in indices[:-1]] + [plan.winner_time + .55]
    captions = [f"TURN {index + 1} / {time:.2f}s" for index, time in zip(indices, times)]
    sheet = Image.new("RGB", (1152, 1390), "#071019")
    draw = ImageDraw.Draw(sheet)
    try:
        title_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 27)
        caption_font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 16)
    except OSError:
        title_font = ImageFont.load_default()
        caption_font = ImageFont.load_default()
    draw.text((24, 20), "MS04.4 / SEED 4304 / REVIEW SPOILERS", font=title_font, fill="#E8F1F5")
    for cell, (time, caption) in enumerate(zip(times, captions)):
        image = renderer.render(time).resize((360, 640), Image.Resampling.LANCZOS)
        x, y = 24 + (cell % 3) * 372, 72 + (cell // 3) * 660
        sheet.paste(image, (x, y))
        draw.text((x, y + 642), caption, font=caption_font, fill="#B9CAD5")
    sheet.save(path, format="PNG", optimize=True)
    return times


def _encode_muted(renderer: GameRenderer, frame_count: int, output: Path) -> None:
    cfg = renderer.cfg
    command = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-f", "rawvideo", "-pix_fmt", "rgb24", "-s:v", f"{cfg.width}x{cfg.height}",
        "-r", str(cfg.fps), "-i", "pipe:0", "-an", "-c:v", "libx264",
        "-vf", "scale=in_range=pc:out_range=tv:out_color_matrix=bt709",
        "-color_primaries", "bt709", "-color_trc", "bt709", "-colorspace", "bt709",
        "-color_range", "tv", "-preset", "slow", "-profile:v", "high",
        "-threads", "2", "-pix_fmt", "yuv420p", "-crf", str(cfg.crf),
        "-g", str(cfg.fps), "-movflags", "+faststart", str(output),
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
    try:
        for frame in range(frame_count):
            process.stdin.write(renderer.render(frame / cfg.fps).tobytes())
            if frame % (cfg.fps * 5) == 0:
                print(f"MS04.4: {frame}/{frame_count} frames", flush=True)
        process.stdin.close()
        error = process.stderr.read()
        if process.wait() != 0:
            raise RuntimeError(error.decode(errors="replace")[-4000:])
    except BrokenPipeError as error:
        details = process.stderr.read().decode(errors="replace")[-4000:]
        process.wait()
        raise RuntimeError(details) from error
    finally:
        if process.stdin and not process.stdin.closed:
            try:
                process.stdin.close()
            except BrokenPipeError:
                pass
        if process.poll() is None:
            process.terminate()
            process.wait()


def export_review(settings: MS04Settings, output_dir: str | Path, overwrite: bool = False) -> dict:
    output_dir = Path(output_dir)
    existing = [output_dir / name for name in OUTPUT_NAMES if (output_dir / name).exists()]
    if existing and not overwrite:
        raise FileExistsError("MS04.4 outputs exist; use --overwrite for this slice only")
    search, candidate = load_selected_candidate(settings.search_output, settings.match_id)
    plan = build_plan(candidate, settings.clock)
    if plan.players != settings.render.players:
        raise ValueError("configured render players do not match the selected match")
    frame_count = math.ceil(plan.duration_seconds * settings.render.fps)
    video_duration = frame_count / settings.render.fps
    plan = replace(plan, duration_seconds=video_duration)
    renderer = GameRenderer(plan, settings.render)
    audio_log = build_audio_log(plan, settings.audio)
    audio_render = synthesize(
        audio_log,
        seed=settings.audio.seed,
        sample_rate=settings.audio.sample_rate,
        channels=settings.audio.channels,
    )
    output_dir.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=".ms04.4-", dir=output_dir) as temporary:
        staging = Path(temporary)
        review = staging / OUTPUT_NAMES[0]
        muted = staging / OUTPUT_NAMES[1]
        sheet = staging / OUTPUT_NAMES[2]
        wav = staging / OUTPUT_NAMES[3]
        timeline = staging / OUTPUT_NAMES[4]
        _encode_muted(renderer, frame_count, muted)
        write_wav(audio_render, wav)
        subprocess.run([
            "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
            "-i", str(muted), "-i", str(wav), "-c:v", "copy", "-c:a", "aac",
            "-b:a", "192k", "-t", f"{video_duration:.9f}", "-movflags", "+faststart", str(review),
        ], check=True)
        contact_times = _contact_sheet(renderer, plan, sheet)
        timeline.write_text(json.dumps(_timeline_record(plan, settings.clock), indent=2) + "\n", encoding="utf-8")
        probes = {}
        for path in (review, muted):
            probe = subprocess.run([
                "ffprobe", "-v", "error", "-show_entries",
                "format=duration:stream=index,codec_type,codec_name,width,height,r_frame_rate,pix_fmt,color_space,color_transfer,color_primaries,sample_rate,channels",
                "-of", "json", str(path),
            ], check=True, capture_output=True, text=True)
            probes[path.name] = json.loads(probe.stdout)
            subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"], check=True)
        rms = np.sqrt(np.mean((audio_render.samples.astype(float) / 32768) ** 2, axis=0))
        manifest = {
            "schema_version": "ms04.4.review-manifest.v1",
            "status": "normal-speed owner-and-wife phone review pending",
            "match_id": plan.match_id,
            "genuine_rule_outcome": True,
            "winner": plan.winner,
            "scripted_winner": False,
            "configuration": {
                "clock": asdict(settings.clock),
                "render": asdict(settings.render),
                "audio": asdict(settings.audio),
            },
            "timeline": {
                "duration_seconds": video_duration,
                "frame_count": frame_count,
                "logical_event_count": len(plan.events),
                "turn_count": len(plan.turn_start_times),
                "winner_time_seconds": plan.winner_time,
                "contact_sheet_times": contact_times,
            },
            "audio": {
                "log_id": audio_log.log_id,
                "synthetic": audio_log.synthetic,
                "cue_count": len(audio_log.events),
                "sample_rate": audio_render.sample_rate,
                "channels": audio_render.channels,
                "peak": audio_render.peak,
                "peak_dbfs": 20 * math.log10(max(audio_render.peak, 1e-12)),
                "rms_by_channel": rms.tolist(),
                "master_gain": audio_render.master_gain,
            },
            "probes": probes,
            "source_sha256": {
                "search_output": _sha256(settings.search_output),
                "config": _sha256(settings.config_path),
                "presentation": _sha256(Path(__file__).with_name("presentation.py")),
                "renderer": _sha256(Path(__file__)),
                "audio_events": _sha256(Path(__file__).parent / "audio" / "events.py"),
                "audio_synthesis": _sha256(Path(__file__).parent / "audio" / "synthesis.py"),
            },
            "files": {
                name: {"sha256": _sha256(staging / name), "bytes": (staging / name).stat().st_size}
                for name in OUTPUT_NAMES[:-1]
            },
        }
        manifest_path = staging / OUTPUT_NAMES[5]
        manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
        for name in OUTPUT_NAMES:
            (staging / name).replace(output_dir / name)
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description="Render the genuine MS04.4 vertical review cut")
    parser.add_argument("--config", type=Path, default=Path("configs/ms04.4.toml"))
    parser.add_argument("--output-dir", type=Path, default=Path("outputs/ms04.4"))
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()
    manifest = export_review(load_settings(args.config), args.output_dir, args.overwrite)
    print(
        f"Saved MS04.4: {manifest['timeline']['duration_seconds']:.2f}s, "
        f"{manifest['timeline']['frame_count']} frames, {manifest['audio']['cue_count']} cues"
    )


if __name__ == "__main__":
    main()
