"""Offline MS05 fixture-to-WAV command, with no game or video dependencies."""

import argparse
from dataclasses import asdict
import hashlib
import json
from pathlib import Path
import platform
import sys

import numpy as np

from .events import load_event_log
from .synthesis import synthesize, write_wav


def main(argv=None):
    parser = argparse.ArgumentParser(description="MS05 deterministic event-driven game sound")
    parser.add_argument("--events", type=Path, default=Path("fixtures/ms05/two-team-v1.json"))
    parser.add_argument("--seed", type=int, default=505)
    parser.add_argument("--sample-rate", type=int, default=48000)
    parser.add_argument("--channels", type=int, choices=(1, 2), default=2)
    parser.add_argument("--output", type=Path, default=Path("outputs/ms05/ms05-fixture-v1.wav"))
    args = parser.parse_args(argv)
    try:
        if args.output.suffix.lower() != ".wav":
            raise ValueError("output must end in .wav")
        manifest_path = args.output.with_suffix(".manifest.json")
        if args.output.exists() or manifest_path.exists():
            raise FileExistsError("WAV or manifest already exists; choose a fresh output filename")
        log = load_event_log(args.events)
        render = synthesize(log, args.seed, args.sample_rate, args.channels)
        package_hash = hashlib.sha256()
        for source in sorted(Path(__file__).parent.glob("*.py")):
            package_hash.update(source.name.encode())
            package_hash.update(source.read_bytes())
        write_wav(render, args.output)
        rms = np.sqrt(np.mean((render.samples.astype(float)/32768)**2, axis=0))
        manifest = {
            "format": "ms05-audio-render-v1", "log_id": log.log_id, "synthetic": log.synthetic,
            "schema_version": log.schema_version, "audio_seed": args.seed,
            "fixture_sha256": hashlib.sha256(args.events.read_bytes()).hexdigest(),
            "audio_source_sha256": package_hash.hexdigest(),
            "wav_sha256": hashlib.sha256(args.output.read_bytes()).hexdigest(),
            "pcm_sha256": hashlib.sha256(render.samples.tobytes()).hexdigest(),
            "sample_rate": render.sample_rate, "channels": render.channels,
            "sample_frames": len(render.samples), "duration_seconds": len(render.samples)/render.sample_rate,
            "peak": render.peak, "peak_dbfs": float(20*np.log10(max(render.peak, 1e-12))),
            "rms_by_channel": rms.tolist(), "master_gain": render.master_gain,
            "versions": {"python": platform.python_version(), "numpy": np.__version__},
            "cues": [asdict(cue) for cue in render.cues],
        }
        with manifest_path.open("x") as file:
            file.write(json.dumps(manifest, indent=2)+"\n")
        print(f"Saved {args.output}: {manifest['duration_seconds']:.2f}s, {render.sample_rate} Hz, "
              f"{render.channels} channels, peak {render.peak:.5f} ({manifest['peak_dbfs']:.2f} dBFS)")
        print(f"Manifest: {manifest_path}; {len(render.cues)} cues; synthetic fixture, creative acceptance pending")
        return 0
    except (OSError, ValueError) as error:
        print(f"ms05: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
