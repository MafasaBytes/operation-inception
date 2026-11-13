"""Stream frames to FFmpeg and retain measurements and provenance beside the MP4."""

from dataclasses import asdict
import csv
import hashlib
import json
import math
from pathlib import Path
import platform
import shutil
import subprocess
import tempfile

import numpy as np
from PIL import __version__ as pillow_version

from . import __version__
from .config import Config, CausalConfig
from .causal import CausalAssembly
from .rendering import PillowRenderer
from .simulation import ChaosToOrder, measure


def source_digest():
    digest = hashlib.sha256()
    for path in sorted(Path(__file__).parent.glob("*.py")):
        digest.update(path.name.encode())
        digest.update(path.read_bytes())
    return digest.hexdigest()


def render_video(config: Config, output: Path, quality="preview", overwrite=False):
    output = Path(output)
    if output.suffix.lower() != ".mp4":
        raise ValueError("output must end in .mp4")
    metrics_path = output.with_suffix(".metrics.csv")
    manifest_path = output.with_suffix(".manifest.json")
    for path in (output, metrics_path, manifest_path):
        if path.exists() and not overwrite:
            raise FileExistsError(f"{path} exists; choose another output or use --overwrite")
    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError("FFmpeg is required on PATH, with the libx264 encoder")
    version = subprocess.run([ffmpeg, "-version"], capture_output=True, text=True, check=True).stdout.splitlines()[0]
    width, height = config.render.dimensions(quality)
    causal = isinstance(config.simulation, CausalConfig)
    simulation = CausalAssembly(config.simulation) if causal else ChaosToOrder(config.simulation)
    renderer = PillowRenderer(config.render, width, height)
    count = math.ceil(config.simulation.duration * config.render.fps - 1e-9)
    output.parent.mkdir(parents=True, exist_ok=True)
    rows = []
    # Stage in the destination filesystem so each final rename is atomic.
    # The manifest is published last and acts as the completion record.
    with tempfile.TemporaryDirectory(prefix=".inception-", dir=output.parent) as staging:
        staging = Path(staging)
        temporary_video = staging / "video.mp4"
        command = [ffmpeg, "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
                   "-f", "rawvideo", "-pix_fmt", "rgb24", "-s:v", f"{width}x{height}",
                   "-r", str(config.render.fps), "-i", "pipe:0", "-an",
                   "-c:v", "libx264", "-preset", "medium", "-crf", str(config.render.crf),
                   "-threads", "1", "-pix_fmt", "yuv420p", "-movflags", "+faststart",
                   str(temporary_video)]
        with (staging / "ffmpeg.log").open("w+b") as log:
            process = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.DEVNULL, stderr=log)
            previous = None
            try:
                for index in range(count):
                    time = index / config.render.fps
                    frame = simulation.sample(time)
                    trail = simulation.sample(max(0, time - config.render.trail_seconds))
                    process.stdin.write(renderer.render(frame, trail).tobytes())
                    rows.append(measure(frame, previous))
                    previous = frame
                    if index % config.render.fps == 0:
                        print(f"Rendering {index + 1}/{count} frames", flush=True)
                process.stdin.close()
                if process.wait() != 0:
                    raise BrokenPipeError("encoder failed")
            except BrokenPipeError as error:
                process.wait()
                log.seek(0)
                raise RuntimeError(f"FFmpeg failed: {log.read().decode(errors='replace')[-3000:]}") from error
            finally:
                if process.stdin and not process.stdin.closed:
                    try:
                        process.stdin.close()
                    except BrokenPipeError:
                        pass
                if process.poll() is None:
                    process.terminate()
                    process.wait()
        temporary_metrics = staging / "metrics.csv"
        with temporary_metrics.open("w", newline="") as file:
            writer = csv.DictWriter(file, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)
        with temporary_video.open("rb") as file:
            video_hash = hashlib.file_digest(file, "sha256").hexdigest()
        settings = asdict(config)
        manifest = {
            "experiment": "001b-causal-assembly" if causal else "001-chaos-to-order",
            "model": "stylised-neighbor-lock-v1" if causal else "stylised-guided-convergence-v1",
            "config": settings,
            "config_sha256": hashlib.sha256(json.dumps(settings, sort_keys=True).encode()).hexdigest(),
            "source_sha256": source_digest(),
            "versions": {"inception": __version__, "python": platform.python_version(),
                         "numpy": np.__version__, "pillow": pillow_version, "ffmpeg": version},
            "quality": quality, "width": width, "height": height,
            "fps": config.render.fps, "frame_count": count,
            "encoded_duration_seconds": count / config.render.fps,
            "particle_count": config.simulation.particle_count,
            "video_sha256": video_hash,
            "initial": rows[0], "final": rows[-1],
            "minimum_center_distance": min(row["min_center_distance"] for row in rows),
            "maximum_speed": max(row["max_speed"] for row in rows),
            "metrics_file": metrics_path.name,
        }
        temporary_manifest = staging / "manifest.json"
        temporary_manifest.write_text(json.dumps(manifest, indent=2) + "\n")
        # Remove a previous completion marker before publishing a replacement run.
        # If publication is interrupted, a stale manifest must not mark it complete.
        manifest_path.unlink(missing_ok=True)
        temporary_video.replace(output)
        temporary_metrics.replace(metrics_path)
        temporary_manifest.replace(manifest_path)
    return manifest
