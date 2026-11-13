import argparse
from pathlib import Path
import subprocess
import sys

from .config import CausalConfig, load_config
from .pipeline import render_video


def main(argv=None):
    parser = argparse.ArgumentParser(description="Render Operation Inception: 001 or 001B")
    parser.add_argument("--config", type=Path, default=Path("configs/experiment001.toml"))
    parser.add_argument("--quality", choices=("preview", "final"), default="preview")
    parser.add_argument("--output", type=Path, help="default: outputs/experiment001-QUALITY.mp4")
    parser.add_argument("--overwrite", action="store_true", help="replace the video and its run sidecars")
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        experiment = "001b" if isinstance(config.simulation, CausalConfig) else "001"
        output = args.output or Path(f"outputs/experiment{experiment}-{args.quality}.mp4")
        result = render_video(config, output, args.quality, args.overwrite)
    except (OSError, ValueError, RuntimeError, subprocess.SubprocessError) as error:
        print(f"inception: {error}", file=sys.stderr)
        return 1
    print(f"Saved {output} ({result['frame_count']} frames, {result['width']}x{result['height']})")
    print(f"Metrics: {output.with_suffix('.metrics.csv')}")
    print(f"Manifest: {output.with_suffix('.manifest.json')}")
    return 0
