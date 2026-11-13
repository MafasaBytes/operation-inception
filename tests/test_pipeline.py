from dataclasses import replace
import json
import shutil
import subprocess

import numpy as np
import pytest

from inception.config import Config, RenderConfig, SimulationConfig
from inception.pipeline import render_video
from inception.rendering import PillowRenderer
from inception.simulation import ChaosToOrder


def test_renderer_preserves_simulation_and_supports_final_dimensions():
    model = ChaosToOrder(SimulationConfig(rings=2))
    frame = model.sample(2)
    before = frame.positions.copy()
    cfg = RenderConfig(supersample=1)
    renderer = PillowRenderer(cfg, *cfg.dimensions("final"))
    image = renderer.render(frame)
    assert image.size == (1080, 1920)
    assert image.mode == "RGB"
    np.testing.assert_array_equal(frame.positions, before)


@pytest.mark.skipif(not shutil.which("ffmpeg") or not shutil.which("ffprobe"), reason="FFmpeg tools required")
def test_video_pipeline_and_sidecars(tmp_path):
    cfg = Config(SimulationConfig(rings=2, intro_seconds=0.1, convergence_seconds=0.5,
                                 stagger_seconds=0.1, hold_seconds=0.3),
                 RenderConfig(preview_width=90, preview_height=160, fps=10, supersample=1))
    path = tmp_path / "smoke.mp4"
    manifest = render_video(cfg, path)
    probe = json.loads(subprocess.run(["ffprobe", "-v", "error", "-count_frames", "-show_streams",
        "-of", "json", str(path)], check=True, capture_output=True, text=True).stdout)
    stream, = probe["streams"]
    assert (stream["width"], stream["height"]) == (90, 160)
    assert stream["codec_name"] == "h264"
    assert stream["pix_fmt"] == "yuv420p"
    assert int(stream["nb_read_frames"]) == manifest["frame_count"] == 10
    assert float(stream["duration"]) == pytest.approx(1)
    assert manifest["final"]["rms_target_error"] == 0
    assert manifest["final"]["settled_fraction"] == 1
    assert path.with_suffix(".metrics.csv").read_text().count("\n") == 11
    assert json.loads(path.with_suffix(".manifest.json").read_text()) == manifest
    # Decode the complete stream to catch corruption beyond container metadata.
    subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-f", "null", "-"], check=True)
    with pytest.raises(FileExistsError):
        render_video(cfg, path)
    rerun = render_video(cfg, path, overwrite=True)
    assert manifest["video_sha256"] == rerun["video_sha256"]


def test_encoder_failure_cleans_up_and_preserves_existing_output(tmp_path, monkeypatch):
    import inception.pipeline as pipeline
    real_popen = pipeline.subprocess.Popen

    def failing_encoder(command, **kwargs):
        if "rawvideo" in command:
            command = ["ffmpeg", "-invalid-inception-option"]
        return real_popen(command, **kwargs)

    if not shutil.which("ffmpeg"):
        pytest.skip("FFmpeg required")
    monkeypatch.setattr(pipeline.subprocess, "Popen", failing_encoder)
    path = tmp_path / "keep.mp4"
    path.write_bytes(b"existing output")
    cfg = Config(SimulationConfig(rings=1), replace(RenderConfig(), preview_width=90, preview_height=160))
    with pytest.raises(RuntimeError, match="FFmpeg failed"):
        render_video(cfg, path, overwrite=True)
    assert path.read_bytes() == b"existing output"
    assert list(tmp_path.iterdir()) == [path]
